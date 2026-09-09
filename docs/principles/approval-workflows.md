# Approval Workflow Principles

Standardized patterns for approval workflows.

## Core Principles

1. **Mixin-Based** - Use `trn.approval.mixin` for approvable models
2. **Consistent States** - Same state names across all modules
3. **Audit Trail** - Every approval tracked with who/when/why
4. **Activity Integration** - Use Odoo's `mail.activity` for notifications

## Standard States

The `approval_state` field (not `state`) is used by the mixin:

| State | Description |
|-------|-------------|
| `draft` | Initial, editable |
| `pending` | Awaiting approval |
| `approved` | Approved |
| `rejected` | Rejected (can reset to draft) |
| `revision` | Revision requested (submitter must update) |

## Standard Methods

| Action | Method |
|--------|--------|
| Submit | `action_submit_for_approval()` |
| Approve | `action_approve()` |
| Reject | `action_reject()` |
| Reset | `action_reset_to_draft()` |
| Request Revision | `action_request_revision()` |

> **Note:** Revision requests include notes explaining what needs to change.
> The submitter can then update and resubmit.

## Approval Mixin Pattern

```python
class MyModel(models.Model):
    _name = "my.model"
    _inherit = "trn.approval.mixin"

    def _on_submit(self):
        """Custom validation before submission"""
        if not self.required_field:
            raise ValidationError("Required field missing")

    def _on_approve(self):
        """Custom logic after approval"""
        self.message_post(body="Approved!")
```

## Audit Fields (Provided by Mixin)

These fields are automatically added by `trn.approval.mixin`:

```python
# Submission tracking
submitted_by_id = fields.Many2one("res.users", readonly=True)
submitted_date = fields.Datetime(readonly=True)

# Approval tracking
approved_by_id = fields.Many2one("res.users", readonly=True)
approved_date = fields.Datetime(readonly=True)

# Rejection tracking
rejected_by_id = fields.Many2one("res.users", readonly=True)
rejected_date = fields.Datetime(readonly=True)
rejection_reason = fields.Text(readonly=True)
```

## Rejection with Reason

Always capture rejection reason via wizard:

```python
def action_reject(self):
    return {
        'type': 'ir.actions.act_window',
        'name': 'Reject',
        'res_model': 'trn.rejection.wizard',
        'view_mode': 'form',
        'target': 'new',
    }
```

## Batch Approval

For large volumes, use async:

| Records | Approach |
|---------|----------|
| < 100 | Synchronous |
| 100 - 1000 | Batch with progress |
| > 1000 | Background job |

## Multi-Stage Approval

Use `trn.approval.definition` for configurable approval sequences:

```
Stage 1: Local validator →
Stage 2: Regional validator →
Stage 3: Final approver
```

---

**See also:** [Access Rights](access-rights.md), [Performance & Scalability](performance-scalability.md)
