---
paths:
  - "*/views/*.xml"
  - "*/data/*.xml"
---

# Odoo XML Rules

## Odoo 19 Syntax

- **XPath class matching** — use `hasclass('classname')`, never `@class='classname'`.
- **Search view `<group>`** — no attributes allowed (`expand`, `string` are invalid in Odoo 19).
- **Don't use `@title`** as XPath selector — use `@class`, `@name`, or other valid attributes.
- **Command API in XML** — use `Command.link(ref('...'))` not tuple syntax in `eval=`.

## Form Layout

- **Minimal header** — only status bar and action buttons in `<header>`.
- **Content in tabs** — all editable fields in `<notebook>` tabs, not header.
- **Multi-column** — use nested `<group>` pattern: `<group col="2"><group>...</group><group>...</group></group>`.
- **Named groups** — all sections must have `name=` for extensibility.
- **Extension points** — add `<div name="..." invisible="1"/>` or `<group name="..." invisible="1"/>`.

## State Colors & Accessibility

- States must use both **icon AND color** (8% of males are colorblind).
- State colors: draft=`secondary`, pending=`warning`, approved=`success`, rejected=`danger`.
- Icons: draft=`fa-pencil`, pending=`fa-clock-o`, approved=`fa-check`, rejected=`fa-times`.

## Lists

- Use `optional="show"` / `optional="hide"` for optional columns.
- Odoo defaults to `limit="80"` — only set explicitly if you need a different value.

## Widgets

- `statusbar` in form header, `badge` in lists/forms, `web_ribbon` for terminal states.
- `boolean_toggle`, `many2many_tags`, `monetary`, `many2one_avatar_user` — prefer these over defaults.

## Comments

- **Section headers** — use `<!-- Section: Name -->` comments to separate logical groups in view files (e.g., header,
  tabs, chatter).
- **Data files** — comment groups of records in data XML. Helps implementers understand what seed data exists without
  reading every record.
- **Non-obvious attributes** — comment `attrs`, `domain`, or `context` expressions that encode business rules not
  evident from the field names.
- **Do not comment self-evident XML** — `<!-- Name field -->` above `<field name="name"/>` adds noise.

## Menu Structure

- **Configuration is app-level** — the Configuration menu is a direct child of the app root menu, not nested inside any
  domain menu.
- **Domain modules add config children** — when a domain module needs a configuration menu item, it adds a child of the
  shared configuration menu, not a separate Configuration menu.
- **No parallel Configuration menus** — never create a second Configuration menu nested inside a domain menu. There is
  one shared Configuration menu at the app root.
- **Sequence convention** — domain menus use sequences 10–80; Configuration is always sequence 90 (renders last).
- **Admin-only gate** — the Configuration menu requires `groups="base.group_system"`.
- **No abbreviations in XML IDs** — use `menu_trn_configuration`, not `menu_trn_config`. See
  `docs/principles/naming-conventions.md`.

## Deep-Dive References

- `docs/principles/odoo19-compatibility.md`
- `docs/principles/ui-design.md`
- `docs/principles/ui-entity-classification.md`
