# Naming Conventions

Consistent naming across all Training Sample development.

## Modules

| Pattern | Example |
|---------|---------|
| `trn_{domain}` | `trn_vocabulary` |
| `trn_{domain}_{feature}` | `trn_inventory` |

All modules use the `trn_*` prefix.

## Models

| Pattern | Example |
|---------|---------|
| `trn.{domain}` | `trn.inventory` |
| `trn.{domain}.{entity}` | `trn.vocabulary.code` |

All models use the `trn.*` prefix.

## Fields

| Type | Pattern | Example |
|------|---------|---------|
| Boolean | `is_*` / `has_*` | `is_active` |
| Many2one | `{model}_id` | `partner_id` |
| One2many/Many2many | `{model}_ids` | `cycle_ids` |
| Date | `{event}_date` | `birth_date` |

## Abbreviations

**Avoid abbreviations** in model names, field names, and XML IDs. Use full, descriptive words for clarity and maintainability.

| Avoid | Use Instead |
|-------|-------------|
| `qty` | `quantity` |
| `amt` | `amount` |
| `num_*` | `number_of_*` |
| `org_*` | `organization_*` |
| `grp_*` | `group_*` |
| `hh_*` | `household_*` |
| `ind_*` | `individual_*` |
| `prev_*` | `previous_*` |
| `curr_*` | `current_*` |
| `tot_*` | `total_*` |
| `pct_*` | `percentage_*` |
| `info` | `information` |
| `config` | `configuration` |
| `msg` | `message` |
| `err` | `error` |
| `tmp` | `temporary` |
| `src` | `source` |
| `dst` | `destination` |
| `inv` | `inventory` |
| `trans` | `transactions` |
| `que` | `queue` |
| `reg` | `registration` |
| `rel` | `relationship` |

**Acceptable domain acronyms** (widely recognized in the industry):

| Acronym | Meaning |
|---------|---------|
| `api` | Application Programming Interface |
| `gis` | Geographic Information System |
| `dms` | Document Management System |
| `crm` | Customer Relationship Management |
| `sla` | Service Level Agreement |
| `mis` | Management Information System |

**Also acceptable:** `id`, `auth`, `ref`, `geo`, `lat`, `lon` (standard technical terms)

## State Values

Use consistently across modules:

- `draft` - Initial, editable
- `pending` - Awaiting action
- `approved` / `validated` - Approved
- `rejected` - Rejected
- `applied` - Changes applied
- `cancelled` - Cancelled

## Security Groups

| Type | Pattern | Example |
|------|---------|---------|
| Category | `category_trn_{domain}` | `category_trn_inventory` |
| Privilege | `privilege_{domain}_{level}` | `privilege_inventory_officer` |
| User Group | `group_{domain}_{level}` | `group_inventory_officer` |
| Technical Group | `group_{domain}_{action}` | `group_inventory_read` |

**Permission Levels:** `viewer` → `officer` → `manager` → `admin`

**Action Codes:** `read`, `write`, `create`, `delete`, `approve`

## Access Control

```
# ir.model.access.csv IDs
access_{model}_{group}          → access_res_partner_inventory_officer

# Record Rule IDs
rule_{model}_{purpose}          → rule_partner_company
```

## Views & Actions

| Type | Pattern |
|------|---------|
| Form view | `view_{model}_form` |
| List view | `view_{model}_list` |
| Action | `action_{model}` |
| Menu | `menu_{model}` |

### Menu XML IDs

Menu items follow a hierarchical naming convention that reflects their position in the app:

| Menu level | Pattern | Example |
|---|---|---|
| App root | `menu_{app}_root` | `menu_trn_root` |
| Domain menu | `menu_{domain}` | `menu_inventory` |
| Domain item | `menu_{domain}_{action}` | `menu_inventory_all` |
| App configuration | `menu_{app}_configuration` | `menu_trn_configuration` |
| Config child | `menu_{app}_configuration_{feature}` | `menu_trn_configuration_vocabularies` |

Use `configuration` not `config` — no abbreviations.

## Studio-Generated Models

Models created dynamically by Studio use the `x_` prefix per Odoo convention:

| Type | Pattern | Example |
|------|---------|---------|
| Custom fields | `x_{field_name}` | `x_custom_phone` |

### Guidelines for Studio Models

- Technical names auto-generated from user-provided name
- Code/technical identifier must be unique and lowercase
- When cloning, suggest `{original}_custom` or `{original}_v2`
- Studio models stored in `ir.model`, not Python code

### Non-Studio Dynamic Models

Some modules create models programmatically (not via Studio). These follow standard `trn.*` naming, not `x_*` prefix. The `x_` prefix is reserved exclusively for user-created content via Studio UI.

## API Endpoints

```
/api/v{version}/trn/{resource}
/api/v{version}/trn/{resource}/{id}
```

## Identifier URIs

Government-issued identifier types use URIs following this pattern:

```
urn:gov:{country_code}:{agency}:{id_type}
```

| Part | Description | Example |
|------|-------------|---------|
| `urn:gov` | Fixed prefix for government identifiers | |
| `{country_code}` | ISO 3166-1 alpha-2, lowercase | `us`, `ke` |
| `{agency}` | Issuing government agency, lowercase | `ssa`, `irs` |
| `{id_type}` | Identifier type slug, lowercase with hyphens | `ssn`, `tin` |

Examples:

| URI | Identifier |
|-----|------------|
| `urn:gov:us:ssa:ssn` | Social Security Number |
| `urn:gov:us:irs:tin` | Tax Identification Number |
| `urn:gov:us:dos:passport` | Passport Number |
| `urn:gov:ke:ntsa:dl` | Driver's License |

For non-government identifiers (e.g., international standards), use the standard's own URI
scheme (e.g., `urn:iso:std:iso:5218` for ISO 5218 gender codes).

## Data Record XML IDs

XML IDs for data records (vocabulary codes, identifier types) follow predictable patterns
to enable cross-module references:

| Record type | Pattern | Example |
|-------------|---------|---------|
| Identifier type | `id_type_{slug}` | `id_type_tax_id` |
| Vocabulary | `vocab_{domain}` | `vocab_membership_type` |
| Vocabulary code | `code_{domain}_{value}` | `code_membership_active` |

These XML IDs are scoped to the module that defines them. To reference a record from
another module, use the fully qualified form: `{module}.{xml_id}`
(e.g., `trn_vocabulary.code_gender_male`).

---

**Authoritative Sources:**
- [ADR-004: Access Rights](../architecture/decisions/ADR-004-access-rights-management.md) - Security group naming

**See also:** [Access Rights](access-rights.md), [Module Architecture](module-architecture.md)
