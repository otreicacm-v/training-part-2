# Odoo Module Integration Patterns

How custom project modules map to and extend Odoo 19's built-in capabilities.

## Integration Strategy

Extend Odoo modules rather than replacing them. Custom modules add domain-specific fields, workflows, and
validations on top of Odoo's proven ERP foundation.

## Module Mapping

| Domain                   | Odoo Module        | Extension Approach                                                               |
| ------------------------ | ------------------ | -------------------------------------------------------------------------------- |
| **Contacts/Entities**    | `res.partner` (base) | `_inherit` — add domain-specific fields (registration codes, categories, tags) |
| **Inventory**            | `stock`            | `_inherit` — add custom lot tracking, expiry management, specialized workflows   |
| **Billing**              | `account`          | `_inherit` — add custom charge capture, rate tables, statement generation        |
| **Staff**                | `hr`               | `_inherit` — add license numbers, specialties, roles, scheduling                 |
| **Scheduling**           | `calendar`         | `_inherit` — add custom event types, resource slots, queue management            |
| **Documents**            | `documents`        | `_inherit` — add custom document types, approval forms, scanned records          |

## Custom Models

These have no Odoo base equivalent and are purely `trn.*`:

| Model                       | Purpose                                      |
| --------------------------- | -------------------------------------------- |
| `trn.project`          | Core project/record tracking, workflows      |
| `trn.task`             | Task management with assignments             |
| `trn.note`             | Documentation with signing/approval          |
| `trn.observation`      | Measurements, readings, data points          |
| `trn.request`          | Requests and order management                |
| `trn.review`           | Review and approval records                  |

## Odoo Module Dependencies

```
trn_vocabulary → base (res.partner)
trn_project → trn_vocabulary
trn_note → trn_project
trn_warehouse → trn_project, stock
trn_service → trn_project
trn_billing → trn_project, account
trn_api → trn_vocabulary, trn_project (+ all domain modules)
```

## Security Integration

Custom access control layers on top of Odoo's group-based security:

- `group_trn_viewer` — read records
- `group_trn_officer` — create/edit records (operators, staff)
- `group_trn_manager` — full access including configuration
- `group_trn_admin` — manage system configuration
- Emergency override with audit trail (when applicable)

Record rules ensure users only see records in their assigned scope (company, department, team).

## Upgrade Safety

Principles for maintaining Odoo upgrade compatibility:

- Never modify Odoo core files — only extend via `_inherit`
- Use `hook` methods for customization points
- Store custom fields in `trn_*` modules, not in Odoo module data
- Test against Odoo nightlies periodically

## Related Documents

- [Project Architecture Vision](vision.md)
- [Module Architecture](../principles/module-architecture.md) (principle)
- [Access Rights](../principles/access-rights.md) (principle)
