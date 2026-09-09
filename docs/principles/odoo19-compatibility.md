# Odoo 19 Compatibility Guidelines

Common issues found during code review. Check these before submitting PRs.

## Automated Enforcement

Many of these issues are now detected automatically by pre-commit hooks:

| Issue | Linter | Auto-Fix |
|-------|--------|----------|
| Command API tuples | `check-odoo19-python` | Yes (`--fix`) |
| Search view `<group>` attrs | `check-odoo19-xml` | No |
| XPath `@title` selector | `check-ui` | No |
| XPath `@class` (use `hasclass()`) | `check-ui` | No |
| `group_expand` 3-param signature | `check-odoo19-python` | No |

**Auto-fix Command API tuples:**
```bash
# Preview changes
python scripts/lint/check_odoo19.py --fix --dry-run trn_vocabulary/models/*.py

# Apply fixes
python scripts/lint/check_odoo19.py --fix trn_vocabulary/models/*.py

# Bulk fix all modules
./scripts/fix-odoo19.sh
```

## SQL Constraints

`_sql_constraints` still works in Odoo 19 and is preferred for pure database constraints (uniqueness, foreign keys) due to performance benefits. Use Python constraints when business logic requires record context.

**Use SQL constraints for**:
```python
# Performance-critical uniqueness checks
_sql_constraints = [
    ("unique_code", "UNIQUE(code)", "Code must be unique"),
    ("unique_name_per_program", "UNIQUE(name, program_id)", "Name must be unique per program"),
]
```

**Use Python constraints when**:
```python
# Business logic requires context or related records
@api.constrains("start_date", "end_date")
def _check_dates(self):
    for rec in self:
        if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
            raise ValidationError(_("Start date must be before end date."))
```

## Command API (Odoo 19 Pattern)

> **Linter**: `check-odoo19-python` (Warning severity, test files excluded)
> **Auto-fix**: `python scripts/lint/check_odoo19.py --fix <files>`

Use `Command` instead of tuples for One2many/Many2many operations:

```python
from odoo import Command

# Creating related records
partner.write({
    'child_ids': [
        Command.create({'name': 'New Child'}),      # (0, 0, vals)
        Command.update(id, {'name': 'Updated'}),    # (1, id, vals)
        Command.delete(id),                          # (2, id, 0)
        Command.unlink(id),                          # (3, id, 0)
        Command.link(id),                            # (4, id, 0)
        Command.clear(),                             # (5, 0, 0)
        Command.set([id1, id2]),                     # (6, 0, [ids])
    ]
})

# In security XML (implied_ids)
<field name="implied_ids" eval="[Command.link(ref('base.group_user'))]"/>
```

**Migration from tuples**:
| Old Tuple | Command Equivalent |
|-----------|-------------------|
| `(0, 0, vals)` | `Command.create(vals)` |
| `(1, id, vals)` | `Command.update(id, vals)` |
| `(2, id, 0)` | `Command.delete(id)` |
| `(3, id, 0)` | `Command.unlink(id)` |
| `(4, id, 0)` | `Command.link(id)` |
| `(6, 0, ids)` | `Command.set(ids)` |

## View Inheritance Selectors

> **Linter**: `check-ui` (Error severity)

**Don't**: Use `@title` as xpath selector
```xml
<xpath expr="//widget[@title='Applied']" position="after">  <!-- Invalid -->
```

**Do**: Use class, name, or other valid attributes
```xml
<xpath expr="//div[@class='oe_title']" position="before">
```

## Search View Groups

> **Linter**: `check-odoo19-xml` (Error severity)

**Don't**: Add attributes to `<group>` in search views
```xml
<group string="Group By" expand="1">  <!-- Invalid in Odoo 19 -->
```

**Do**: Use plain group element
```xml
<group>
    <filter name="group_by_x" string="By X" context="{'group_by': 'x'}"/>
</group>
```

## Translation After Unlink

**Don't**: Call `_()` after database operations that may invalidate cursor
```python
cr.unlink()
return {"title": _("Deleted")}  # May fail with cursor assertion error
```

**Do**: Prepare translations before destructive operations
```python
title = _("Deleted")  # Or use plain string for notifications
cr.unlink()
return {"title": title}
```

## Test Approval Definitions

**Don't**: Create approval definitions without required fields
```python
cls.env["trn.approval.definition"].create({
    "name": "Test",
    "model_id": model_id,
})  # Fails: approval_group_id required
```

**Do**: Include approval group when using default type
```python
cls.test_group = cls.env["res.groups"].create({"name": "Test Group"})
cls.env["trn.approval.definition"].create({
    "name": "Test",
    "model_id": model_id,
    "approval_type": "group",
    "approval_group_id": cls.test_group.id,
})
```

## Detail Model Field Names

Check actual field names in detail models before writing tests:
- `address_line1`, `address_line2` (not `street`, `street2`)
- `postal_code` (not `zip`)

Use `grep` or read the model file to verify field names exist.

## Group Expand Method Signature

> **Linter**: `check-odoo19-python` (Error severity)

In Odoo 19, the `group_expand` callback signature changed - the `order` parameter is no longer passed.

**Don't**: Use the old 3-parameter signature
```python
@api.model
def _read_group_stage_ids(self, stages, domain, order):
    return stages.search([], order=order)  # Will fail in Odoo 19
```

**Do**: Use the new 2-parameter signature
```python
@api.model
def _read_group_stage_ids(self, stages, domain):
    return stages.search([])
```
