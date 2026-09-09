# Pretty URLs

User-friendly URLs via Odoo's `path` field on `ir.actions.act_window`.

## Technical Requirements

- Pattern: `[a-z][a-z0-9_-]*`
- Cannot start with `m-` or `action-`
- Cannot be `new`
- Must be unique across all actions

## Naming Conventions

| Type | Pattern | Examples |
|------|---------|----------|
| Primary entities | Plural nouns | `individuals`, `groups`, `programs`, `cases` |
| Filtered views | Suffix with filter | `my-cases`, `pending-change-requests` |
| Specialized groups | `group-{type}` | `group-households`, `group-departments` |
| Config items | `{domain}-{item}` | `sale-order-types`, `inventory-categories`, `hr-departments` |
| Domain entities | Prefix domain | `sale-orders`, `inventory-items` |

## Implementation

```xml
<record id="action_case" model="ir.actions.act_window">
    <field name="name">Cases</field>
    <field name="path">cases</field>
    <field name="res_model">trn.case</field>
    ...
</record>
```

## Guidelines

1. **Add paths to menu-linked actions** - user-facing navigation points
2. **Skip wizard actions** - `target="new"` modals don't need paths
3. **Skip contextual actions** - button-triggered actions don't need paths
4. **Use domain prefixes** for config items to avoid conflicts

## Enforcement

**REQUIRED**: Every `ir.actions.act_window` linked to a menu item MUST have a `path` field.

When adding new menu-linked actions, always include:
```xml
<field name="path">your-entity-name</field>
```

### Checklist for New Actions

- [ ] Action has `<field name="path">...</field>` defined
- [ ] Path follows naming conventions (plural nouns, domain prefixes)
- [ ] Path is unique (check existing paths in codebase)
- [ ] Path is lowercase with hyphens (not underscores)

## Quick Reference

```
# Sales
orders, my-orders, sale-order-types, sale-teams

# Inventory
products, inventory-items, inventory-categories, warehouses

# HR
employees, departments, job-positions

# Configuration
settings, approval-rules, notification-templates
```
