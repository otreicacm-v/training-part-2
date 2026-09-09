# Security Audit Guide

How to audit, understand, and fix access rights issues in project modules.

## The Two Audit Commands

| Command | What it does |
|---------|-------------|
| `./odoo-project audit-security` | Mechanical checks: ACL naming, record rule patterns, Odoo 19 API compliance |
| `./odoo-project audit-modules` | AI-assisted deep audit: naming, logging, tests, PII, error handling |

Run `audit-security` regularly (it's fast). Run `audit-modules` before a PR on modules you have substantially changed (it requires `cursor-agent` or `claude`).

## Running `audit-security`

```bash
# Audit all modules
./odoo-project audit-security

# Audit a single module
./odoo-project audit-security trn_inventory

# Generate markdown report
./odoo-project audit-security --report

# Output as JSON (for scripting)
./odoo-project audit-security --json
```

### Understanding the output

```
[trn_inventory] Auditing...
  [ERROR] GROUPS-CATEGORY: Group 'group_inventory_officer' uses category_id (Odoo 19 violation - use privilege_id instead)
         File: trn_inventory/security/security_groups.xml
  [WARN] ACL-NAMING: Entry 'inventory_officer_access' doesn't follow 'access_{model}_{group}' pattern
         File: trn_inventory/security/ir.model.access.csv
[trn_inventory] Errors: 1, Warnings: 1

========================================
AUDIT SUMMARY
========================================
Total modules: 1
Total errors:   1
Total warnings: 1

Modules with issues:
  trn_inventory: 1 errors, 1 warnings

Detailed report saved to: reports/security/audit-report.md
```

Errors block the CI pipeline. Warnings should be fixed but do not block. The full report is saved to `reports/security/audit-report.md`.

### What each check covers

| Check code | What it detects |
|------------|----------------|
| `ACL` | Module defines models but has no `ir.model.access.csv` |
| `ACL-NAMING` | ACL entry ID does not start with `access_` |
| `RULES-NOUPDATE` | `ir.rule` records not wrapped in `<data noupdate="1">` |
| `RULES-EMPTY-DOMAIN` | `domain_force=[]` with write/create/unlink permissions |
| `RULES-NO-GROUP` | `ir.rule` has no `groups` field and is not `global="True"` |
| `GROUPS-CATEGORY` | `res.groups` record uses `category_id` (Odoo 19 violation) |
| `GROUPS-USERS-FIELD` | Uses `users` field instead of `user_ids` |
| `GROUPS-TUPLE-SYNTAX` | Uses `(4, ref())` instead of `Command.link()` |
| `MENU-GROUPS-FIELD` | Uses `groups_id` instead of `group_ids` on menu items |
| `GROUPS-PRIVILEGE` | User-facing group may be missing `privilege_id` |
| `LEGACY-BASE-GROUP` | Module modifies `base.group_erp_manager` |
| `ODOO19-TUPLE` | Uses `(6, 0, [])` instead of `Command.set()` |

## Running `audit-modules`

```bash
# Audit all modules (AI-assisted, requires cursor-agent or claude)
./odoo-project audit-modules

# Audit a single module
./odoo-project audit-modules trn_inventory

# Auto-fix simple issues
./odoo-project audit-modules --fix trn_inventory

# Auto-fix and commit each module
./odoo-project audit-modules --fix --commit trn_inventory
```

Results are saved as JSON files in `reports/compliance/`. A summary is written to `reports/compliance/summary.json`.

The AI audit checks: naming conventions, ACL completeness, `print()` usage, bare `except:` clauses, `cr.commit()` in loops, PII in logs, lazy logging format, and test existence.

## Auto-Fixing with `fix-security`

```bash
# Fix a single module (mechanical fixes + AI if cursor-agent/claude available)
./odoo-project fix-security trn_inventory

# Preview what would change without writing files
./odoo-project fix-security --dry-run trn_inventory

# Only apply mechanical fixes (no AI)
./odoo-project fix-security --mechanical-only trn_inventory

# Fix all modules that have issues
./odoo-project fix-security --all
```

Mechanical fixes applied automatically:
- `(4, ref('...'))` → `Command.link(ref('...'))`
- `(6, 0, [...])` → `Command.set([...])`
- `users` → `user_ids` on `res.groups`
- `groups_id` → `group_ids` on menu records

Always review the diff after auto-fix. Auto-fixers handle syntax patterns — they do not verify business logic.

## The Three-Tier Security Model

This project uses a three-tier hierarchy for access control. See `docs/principles/access-rights.md` for the full specification.

```
Tier 1: ROLES (composite, cross-domain)
    role_trn_field_officer, role_trn_supervisor

Tier 2: FUNCTIONAL PRIVILEGES (user-facing, per domain)
    group_inventory_viewer, group_inventory_officer, group_inventory_manager

Tier 3: BASE PERMISSIONS (technical, granular)
    group_inventory_read, group_inventory_write, group_inventory_create
```

Permission levels flow upward: `viewer` → `officer` → `manager` → `admin`. Higher levels inherit lower levels through `implied_ids`.

## ACL File Format

File: `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_trn_stock_move_viewer,trn.stock.move viewer,model_trn_stock_move,group_inventory_viewer,1,0,0,0
access_trn_stock_move_officer,trn.stock.move officer,model_trn_stock_move,group_inventory_officer,1,1,1,0
access_trn_stock_move_manager,trn.stock.move manager,model_trn_stock_move,group_inventory_manager,1,1,1,1
```

### ACL entry ID naming

IDs must follow `access_{model}_{group}`:

- `{model}` — model name with underscores, no dots (`trn_stock_move`, `res_partner`)
- `{group}` — short group identifier (`viewer`, `officer`, `manager`, `admin`)

```
# Correct
access_trn_stock_move_officer
access_res_partner_registry_viewer

# Wrong — don't prefix with user/manager/module name
user_access_trn_stock_move
trn_inventory_officer_access
stock_move_manager
```

### Reference data models

Models that hold lookup values (vocabulary codes, terminology, configuration) must be readable by all internal users:

```csv
access_trn_stock_type_user,trn.stock.type user,model_trn_stock_type,base.group_user,1,0,0,0
```

Write access for reference data stays restricted to managers and admins.

## Security Groups XML

### Odoo 19 requirements for `res.groups`

```xml
<!-- Correct: privilege_id, user_ids, Command.link() -->
<record id="group_inventory_officer" model="res.groups">
    <field name="name">Officer</field>
    <field name="privilege_id" ref="privilege_inventory_officer"/>
    <field name="implied_ids" eval="[
        Command.link(ref('group_inventory_read')),
        Command.link(ref('group_inventory_write')),
    ]"/>
    <field name="user_ids" eval="[]"/>
</record>

<!-- Wrong: category_id, users, tuple syntax -->
<record id="group_inventory_officer" model="res.groups">
    <field name="category_id" ref="..."/>        <!-- Odoo 19 violation -->
    <field name="implied_ids" eval="[(4, ref('group_inventory_read'))]"/>  <!-- Old syntax -->
    <field name="users" eval="[]"/>              <!-- Wrong field name -->
</record>
```

User-facing groups (officer, manager) must have `privilege_id`. Technical groups (`_read`, `_write`, `_create`) do not need it.

### Privilege records

Create a `res.groups.privilege` record before using it on a group:

```xml
<record id="privilege_inventory_officer" model="res.groups.privilege">
    <field name="name">Inventory Officer</field>
    <field name="category_id" ref="trn_security.module_category_trn_operations"/>
</record>
```

The privilege must appear before the group that references it in the same XML file.

## Record Rule Patterns

### Required: Wrap rules in `noupdate`

```xml
<data noupdate="1">
    <record id="rule_stock_move_company" model="ir.rule">
        ...
    </record>
</data>
```

### Multi-company isolation (required for models with `company_id`)

```xml
<record id="rule_stock_move_company" model="ir.rule">
    <field name="name">Stock Move: Multi-Company</field>
    <field name="model_id" ref="model_trn_stock_move"/>
    <field name="domain_force">[
        '|', ('company_id', '=', False), ('company_id', 'in', company_ids)
    ]</field>
    <field name="global" eval="True"/>
</record>
```

### Role-based scoping

```xml
<!-- Officer sees own records -->
<record id="rule_stock_move_officer_scope" model="ir.rule">
    <field name="name">Stock Move: Officer Scope</field>
    <field name="model_id" ref="model_trn_stock_move"/>
    <field name="domain_force">[('create_uid', '=', user.id)]</field>
    <field name="groups" eval="[(4, ref('group_inventory_officer'))]"/>
</record>

<!-- Manager sees all records -->
<record id="rule_stock_move_manager_all" model="ir.rule">
    <field name="name">Stock Move: Manager All Access</field>
    <field name="model_id" ref="model_trn_stock_move"/>
    <field name="domain_force">[(1, '=', 1)]</field>
    <field name="groups" eval="[(4, ref('group_inventory_manager'))]"/>
</record>
```

### Anti-patterns — never do these

```xml
<!-- BAD: Empty domain with write — any user can write any record -->
<field name="domain_force">[]</field>
<field name="perm_write">1</field>

<!-- BAD: global=True with write — grants write to EVERY user -->
<record id="rule_something" model="ir.rule">
    <field name="global">True</field>
    <field name="perm_write">1</field>
</record>

<!-- BAD: No groups field and not global — Odoo applies to all users by default -->
<record id="rule_something" model="ir.rule">
    <field name="domain_force">[('create_uid', '=', user.id)]</field>
    <!-- Missing: groups field or global="True" -->
</record>

<!-- BAD: Modifying base Odoo groups — causes permission cascades system-wide -->
<record id="base.group_user" model="res.groups">
    <field name="implied_ids" eval="[...]"/>
</record>
```

## Common Issues and Fixes

### "Module defines models but has no ir.model.access.csv"

Create the file at `security/ir.model.access.csv` with a header row and one entry per model per group. Add the file to `__manifest__.py` under `data`:

```python
"data": [
    "security/ir.model.access.csv",
    ...
],
```

### "Entry 'xyz' doesn't follow 'access_{model}_{group}' pattern"

Rename the entry ID in the CSV. ACL IDs are rarely referenced elsewhere, but search before renaming:

```bash
grep -r "xyz" --include="*.xml" --include="*.csv" --include="*.py" .
```

If references exist in other modules, update them too.

### "Group 'group_xyz' uses category_id (Odoo 19 violation)"

Replace `category_id` with `privilege_id`. Create the `res.groups.privilege` record first:

```xml
<!-- Add this BEFORE the group record -->
<record id="privilege_xyz" model="res.groups.privilege">
    <field name="name">XYZ Officer</field>
    <field name="category_id" ref="trn_security.module_category_tpl"/>
</record>

<!-- Then update the group -->
<record id="group_xyz" model="res.groups">
    <field name="privilege_id" ref="privilege_xyz"/>
    <!-- Remove the old category_id line -->
</record>
```

### "Record rules should be wrapped in `<data noupdate="1">`"

Wrap the `ir.rule` records (not the entire file) in a noupdate block:

```xml
<!-- Before the first ir.rule record -->
<data noupdate="1">

    <record id="rule_..." model="ir.rule">
        ...
    </record>

</data>
```

### Test fails with `AccessError`

The correct fix is always in `ir.model.access.csv` — not in the test. Adding `sudo()` to tests defeats the purpose of access control testing.

1. Check which model the error names.
2. Open `security/ir.model.access.csv`.
3. Confirm there is an entry for that model and the group the test user belongs to.
4. If missing, add the entry.
5. Re-run the test.

## Verification After Fixes

After running `fix-security` or making manual security changes:

1. Re-run the audit to confirm the error count dropped to zero:

```bash
./odoo-project audit-security trn_inventory
```

2. Run module tests — security changes can break existing tests:

```bash
./odoo-project test trn_inventory
```

3. Search for broken cross-module references if you renamed any group IDs or ACL entry IDs:

```bash
grep -r "OLD_ID" --include="*.xml" --include="*.csv" --include="*.py" .
```

## Deep Dives

- `docs/principles/access-rights.md` — full three-tier architecture, group hierarchy patterns, record rule requirements, demo environment checklist
- `docs/principles/naming-conventions.md` — Security Groups section (category, privilege, group, technical group naming)
- `.claude/rules/security.md` — auto-loaded rule summary (loaded when editing `security/*`)
