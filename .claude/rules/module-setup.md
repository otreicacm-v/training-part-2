---
paths:
  - "*/__manifest__.py"
  - "*/readme/*"
---

# Module Setup Rules

## Manifest (`__manifest__.py`)

### Required metadata fields

Every `trn_*` manifest must include:

```python
"license": "LGPL-3",
"development_status": "Alpha",
"maintainers": [],
```

Only include `"external_dependencies": {"python": [...]}` when the module has external Python deps.

### `application` and `auto_install`

- **`application=False`** for all `trn_*` modules. Only starter modules (`trn_starter_{country}`) are
  `application=True`.
- **`auto_install`**: list syntax `["dep1", "dep2"]` for bridges (both deps required). `True` only for single-dependency
  extensions. **Country-specific modules (`trn_*_{country}`) must never use `auto_install`** — they are installed via
  starter modules only.
- **Starter modules** (`trn_starter_{country}`) should include a `data/res_company_data.xml` (`noupdate="1"`) that
  activates the country's currency, sets the main company country and currency, and configures the admin timezone.
- **Category**: use `Training Sample/{Domain}` hierarchy (e.g., Core, Sales, Identity, Inventory, Integration).

### `excludes` (country-specific modules)

Country-specific modules (`trn_{domain}_{country}`) **must** declare `excludes` listing all other country variants of
the same domain. This prevents conflicting country implementations from being installed together.

```python
# trn_contact_us/__manifest__.py
"excludes": ["trn_contact_ke", "trn_contact_ng"],
```

When adding a new country, update all existing country modules to exclude the new one.

## Module Naming

- Pattern: `trn_{domain}` or `trn_{domain}_{feature}`
- Model prefix: `trn.*`
- XML ID prefix: `trn_*`

## Module Structure

```
trn_example/
├── __init__.py
├── __manifest__.py
├── models/
├── views/
├── security/
│   └── ir.model.access.csv
├── data/
├── demo/
├── tests/
└── readme/
    └── DESCRIPTION.md
```

## DESCRIPTION.md

- 25-60 lines max. If longer, the module may be doing too much.
- Required sections: overview paragraph, Key Capabilities, Key Models, Configuration, UI Location, Security,
  Dependencies.
- Name models by `_name` (e.g., `trn.alert.rule`), not prose.
- Name menu paths from actual `<menuitem>` XML — trace `parent=` to root.
- Name security groups by XML ID — don't say "authorized users".
- No marketing language ("robust", "comprehensive", "seamless").
- Verify all claims against source code. See `docs/principles/module-descriptions.md` for anti-patterns.

## Dependencies

- Flow downward: Layer 3 (extensions) → Layer 2 (capabilities) → Layer 1 (foundation) → Layer 0 (Odoo).
- Minimize peer dependencies. No circular dependencies.

## Deep-Dive References

- `docs/principles/module-visibility.md`
- `docs/principles/module-architecture.md`
- `docs/principles/module-descriptions.md`
