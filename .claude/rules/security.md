---
paths:
  - "*/security/*"
---

# Security Rules

## Three-Tier Architecture

```
Tier 1: ROLES (composite, cross-domain)     — role_trn_field_officer
Tier 2: FUNCTIONAL PRIVILEGES (per domain)  — group_{domain}_officer
Tier 3: BASE PERMISSIONS (technical)        — group_{domain}_read
```

Permission levels: `viewer` → `officer` → `manager` → `admin`

## ACL File (`ir.model.access.csv`)

- Entry IDs: `access_{model}_{group}` (e.g., `access_res_partner_{domain}_officer`)
- Every model MUST have ACL entries. Related models need ACLs too.
- **Every custom `trn.*` model MUST include a `base.group_system` row with full CRUD** (1,1,1,1). This ensures the
  superuser/admin can always access all models. Place it as the first data row.
- Reference data (vocabularies, codes) must be readable by `base.group_user`.
- When tests fail with `AccessError`, fix the ACL — don't bypass with `sudo()`.

## Groups XML

- User-facing groups use `privilege_id` ref, not `category_id`.
- Use `Command.link()` in `implied_ids`, not tuple syntax.
- Use `user_ids` not `users` field. Use `group_ids` not `groups_id` on menus.
- Never modify base Odoo groups (`base.group_user`, `base.group_erp_manager`). These groups are globally inherited by
  all modules; modifying them causes unexpected permission cascades across the entire system.

## Record Rules

- **Never use empty domains** — `domain_force=[]` is forbidden with write/create/unlink.
- **"See all" pattern** — use `[(1, '=', 1)]`, not `[]`.
- Always specify `groups` OR set `global="True"`.
- Wrap in `<data noupdate="1">`.
- Multi-company models MUST have company isolation rule:
  `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`

## Anti-Patterns

- Empty domain with write permissions
- Global rule with write (allows ANY user to write)
- No group specification (applies to everyone)
- Modifying base Odoo groups

## Deep-Dive References

- `docs/principles/access-rights.md`
- `docs/principles/naming-conventions.md` (Security Groups section)
