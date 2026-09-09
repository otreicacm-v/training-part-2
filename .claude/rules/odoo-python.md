---
paths:
  - "*/models/*.py"
  - "*/wizard/*.py"
  - "*/wizards/*.py"
---

# Odoo Python Rules

## Naming

- Modules: `trn_{domain}` / `trn_{domain}_{feature}`
- Models: `trn.{domain}` / `trn.{domain}.{entity}`
- Fields: `is_*`/`has_*` (bool), `{model}_id` (M2O), `{model}_ids` (O2M/M2M), `{event}_date`
- No abbreviations (`quantity` not `qty`, `encounter` not `enc`). See `docs/principles/naming-conventions.md` for full
  list.
- States: `draft` → `pending` → `approved`/`rejected` → `cancelled`
- Views: `view_{model}_form`, `view_{model}_list`, `action_{model}`, `menu_{model}`

## Odoo 19 Compatibility

- **Command API** — use `Command.create(vals)`, `Command.link(id)`, etc. Never use tuple syntax `(0, 0, vals)`.
- **`group_expand`** — 2-param signature `(self, stages, domain)`. No `order` param.
- **SQL constraints** — still work; preferred for uniqueness. Use Python constraints for business logic.
- **Translation after unlink** — call `_()` before destructive operations, not after.

## Error Handling

- Use `ValidationError` for data validation, `UserError` for business rules.
- Error messages: state what happened, why, and how to fix.
- Logging: `_logger = logging.getLogger(__name__)`. Use lazy formatting, not f-strings.
- **Never log PII** — use `partner.id`, not `partner.name` or national IDs.
- No bare `except:` — catch specific exceptions.
- No `print()` — use `_logger`.

## Documentation

- **`_description`** — required on every model. Use a human-readable name (e.g., `"Inventory Item"`, not
  `"trn.inventory.item"`).
- **Class docstring** — add on models whose purpose is not obvious from `_name` and `_description` alone. Explain what
  the model represents in the domain, not what fields it has.
- **Method docstrings** — required on public methods, overrides of Odoo methods (`create`, `write`, `unlink`,
  `action_*`), constraint methods (`_check_*`), and complex private methods. One-liner is fine for simple methods.
- **Inline comments** — explain _why_, not _what_. Do not restate what the code already says (`# increment counter`
  above `counter += 1`). Do comment non-obvious business rules, regulatory requirements, and workarounds for Odoo
  quirks.
- **No PII in comments** — do not use real names, IDs, or sensitive data in examples within comments or docstrings.
- **Field `help=` attribute** — use on fields where the label alone is ambiguous. This text appears as a tooltip in the
  UI and helps implementers understand the field without reading source code.

## Patterns

- Inherit and extend: `_inherit = "res.partner"` + add fields.
- Hook methods: `_pre_*_hook()` / `_post_*_hook()` for extension points.
- Never expose DB IDs in APIs — use external identifiers.
- No `cr.commit()` in loops — use `queue_job` for batch processing.

## Country-Specific Code

- **No country-specific fields in base modules.** Country-specific validations and fields go in `trn_*_{country}`
  modules, never in base domain modules.
- Country modules use `_inherit` to extend base models with country fields and logic.

## Identifiers

- External identifiers are stored in the **identifier model** (`trn.identifier`), linked via `identifier_ids` One2many
  on `res.partner`.
- Do not add ID fields directly on `res.partner` — use the identifier model so new ID types can be added via data files.

## Vocabulary Over Static Selections

- **Avoid `fields.Selection`** for values like gender, civil status, or any classification that follows an external
  standard or varies by deployment.
- Use `fields.Many2one("trn.vocabulary.code", domain="[('namespace_uri', '=', '...')]")` instead.
- **Static selections are acceptable** only for internal workflow states (`draft`, `confirmed`, `cancelled`) or
  boolean-like choices that are truly fixed.
- See `docs/principles/module-architecture.md` for the full vocabulary pattern.

## Deep-Dive References

- `docs/principles/naming-conventions.md`
- `docs/principles/odoo19-compatibility.md`
- `docs/principles/error-handling.md`
- `docs/principles/api-design.md`
- `docs/principles/module-architecture.md`
