# Audit & Compliance Principles

> **Note:** The `trn_audit` module is planned but not yet implemented. The principles below describe the target architecture.

Requirements for audit trails, data integrity, and regulatory compliance in Training Sample.

## Core Principles

1. **Immutable History** - Audit logs cannot be modified or deleted
2. **Complete Trail** - Track who did what, when, and why
3. **Configurable Scope** - Enable auditing per model and field
4. **Non-Blocking** - Audit logging must not impact performance

## Audit Log Module

Training Sample uses `trn_audit` for comprehensive audit tracking.

### Enabling Audit for a Model

Configure via UI: Settings → Audit Rules → Create

```python
# Or programmatically
self.env['trn.audit.rule'].create({
    'name': 'Partner Audit',
    'model_id': self.env.ref('base.model_res_partner').id,
    'log_create': True,
    'log_write': True,
    'log_unlink': True,
    'field_to_log_ids': [(6, 0, field_ids)],  # Specific fields
})
```

### What Gets Logged

| Event | Tracked Data |
|-------|--------------|
| Create | New record values, user, timestamp |
| Write | Old values, new values, changed fields |
| Delete | Deleted record values, user, timestamp |

### Audit Log Structure

```python
trn.audit.log:
    audit_rule_id   # Link to rule configuration
    user_id         # Who made the change
    create_date     # When
    model_id        # Which model
    res_id          # Which record
    method          # create/write/unlink
    data            # JSON of old/new values
```

## Required Audit Points

### Always Audit

| Model/Action | Reason |
|--------------|--------|
| `res.partner` | Contact data integrity |
| `trn.order` | Order history |
| `trn.document` | Document integrity |
| Approval state changes | Decision trail |
| Access right changes | Security |

### Approval Audit Fields

Models using `trn.approval.mixin` automatically get these fields:

```python
# Provided by trn.approval.mixin (no need to add manually)
submitted_by_id = fields.Many2one("res.users", readonly=True)
submitted_date = fields.Datetime(readonly=True)
approved_by_id = fields.Many2one("res.users", readonly=True)
approved_date = fields.Datetime(readonly=True)
rejected_by_id = fields.Many2one("res.users", readonly=True)
rejected_date = fields.Datetime(readonly=True)
rejection_reason = fields.Text(readonly=True)
```

To use: inherit `trn.approval.mixin` in your model (see [Approval Workflows](approval-workflows.md)).

## Data Integrity

### Prevent Unauthorized Deletion

```python
class Order(models.Model):
    _name = "trn.order"

    def unlink(self):
        if any(rec.state == 'completed' for rec in self):
            raise UserError(_("Cannot delete completed orders."))
        return super().unlink()
```

### Soft Delete Pattern (Optional)

For critical data where you need to track who archived and why, extend Odoo's built-in `active` pattern:

```python
class ResPartner(models.Model):
    _inherit = "res.partner"

    archived_date = fields.Datetime(readonly=True)
    archived_by_id = fields.Many2one("res.users", readonly=True)
    archive_reason = fields.Text()

    def action_archive(self):
        self.write({
            'active': False,
            'archived_date': fields.Datetime.now(),
            'archived_by_id': self.env.uid,
        })
```

> **Note:** This extended pattern is optional. For most models, Odoo's standard
> `active` field with `mail.thread` tracking is sufficient.

## Mail Thread Integration

Inherit `mail.thread` for automatic change tracking:

```python
class Order(models.Model):
    _name = "trn.order"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(tracking=True)
    state = fields.Selection([...], tracking=True)
    assigned_user_id = fields.Many2one("res.users", tracking=True)
```

This automatically logs:
- Field value changes
- State transitions
- User assignments

## Compliance Reports

### Standard Reports

| Report | Purpose | Frequency |
|--------|---------|-----------|
| User activity log | Who accessed what | On-demand |
| Data modification report | Changes to sensitive data | Weekly |
| Approval history | All approvals/rejections | Monthly |
| Access rights changes | Security audit | Quarterly |

### Report Generation

```python
def generate_audit_report(self, date_from, date_to):
    return self.env['trn.audit.log'].search([
        ('create_date', '>=', date_from),
        ('create_date', '<=', date_to),
        ('model_id.model', '=', 'res.partner'),
    ])
```

## Retention Policy

| Data Type | Retention Period | Action After |
|-----------|-----------------|--------------|
| Audit logs | 7 years | Archive to cold storage |
| Approval history | Permanent | Never delete |
| Session logs | 1 year | Anonymize and aggregate |
| Error logs | 90 days | Delete |

> **Implementation Status:** Retention policy cleanup is not yet automated.
> Manual archival processes should be used until `trn_audit` includes scheduled cleanup jobs.

## Checklist

- [ ] Critical models have audit rules configured
- [ ] Approval models include audit fields
- [ ] Sensitive models use soft delete
- [ ] No PII in log messages
- [ ] Retention policies documented
- [ ] Regular audit report generation

---

**Authoritative Sources:**
- `trn_audit` module (planned) — Audit implementation and configuration

**See also:** [Access Rights](access-rights.md), [Error Handling](error-handling.md), [Approval Workflows](approval-workflows.md)
