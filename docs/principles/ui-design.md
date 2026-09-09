# UI Design Principles

Guidelines for consistent, space-efficient, and extensible user interfaces in Training Sample.

**See also:**
- [ui-entity-classification.md](ui-entity-classification.md) - Choose patterns based on entity type
- [ui-performance.md](ui-performance.md) - Scalability patterns for millions of records
- [odoo19-compatibility.md](odoo19-compatibility.md) - View syntax requirements

---

## Design Personality

Training Sample is an **Odoo 19 application** designed for dense, professional workflows.

### Core Values

| Value | Description |
|-------|-------------|
| **Trust** | Professional-grade reliability, no flashy effects |
| **Clarity** | Dense information, but organized and scannable |
| **Accessibility** | Works for all staff on varying devices |
| **Efficiency** | Power users need speed, not hand-holding |

### Visual Language

**Color Foundation**: Use Odoo's built-in Bootstrap 5 classes, not custom hex values.

**State Colors** (semantic, not decorative):

| State | List Decoration | Badge Class | Icon (Required) | Use For |
|-------|-----------------|-------------|-----------------|---------|
| Draft | `decoration-muted` | `text-bg-secondary` | `fa-pencil` | Editable, not submitted |
| Pending | `decoration-warning` | `text-bg-warning` | `fa-clock-o` | Awaiting action |
| Approved | `decoration-success` | `text-bg-success` | `fa-check` | Completed successfully |
| Rejected | `decoration-danger` | `text-bg-danger` | `fa-times` | Failed, needs attention |
| Cancelled | `decoration-muted` | `text-bg-secondary` | `fa-ban` | No longer active |

**⚠️ Accessibility Requirement**: Icons are MANDATORY alongside colors. 8% of males are colorblind and cannot distinguish yellow/green or red/green. Always pair state colors with icons:

```xml
<!-- ✅ GOOD: Icon + color -->
<field name="state" widget="badge">
    <t t-if="state == 'pending'">
        <i class="fa fa-clock-o me-1"/>Pending
    </t>
</field>

<!-- ❌ BAD: Color only -->
<field name="state" widget="badge" decoration-warning="state == 'pending'"/>
```

**Icons**: Font Awesome, functional not decorative. Consistent icon per concept:
- `fa-users` (contacts), `fa-cube` (products), `fa-clipboard` (requests)

---

## Core Principles

1. **Minimal Header** - Headers show only status bar and action buttons
2. **Content in Tabs** - All editable fields belong in organized tabs, not the header
3. **Multi-Column Layouts** - Use screen width efficiently with 2-3 column layouts
4. **Extensible Structure** - Named groups and sections for module injection
5. **Consistent Patterns** - Same layout patterns across entity classes

---

## Menu Hierarchy

Training Sample uses two menu locations: **Settings** for foundational configuration (vocabularies, system-wide settings) and a shared **Configuration** menu under the app root for domain-specific config items.

### Structure

```
Settings (base.menu_administration, Odoo built-in)
├── Users & Companies                 (Odoo built-in)
├── General Settings                  (Odoo built-in)
├── Vocabularies                      sequence 50, admin only
│   ├── Vocabularies
│   └── Codes
└── Technical                         (Odoo built-in)

base.menu_custom (Odoo built-in)
├── {Domain}                          sequence 10
│   └── All {Items}
├── {future domain menus}             sequence 20–80
└── Configuration                     sequence 90, admin only
    └── {future config items from domain modules}
```

### Rules

1. **Foundational config goes in Settings** — System-wide configuration (vocabularies, global settings) lives under `base.menu_administration`. Use `groups="base.group_system"` to restrict to administrators.
2. **Domain config goes in Configuration** — `menu_trn_configuration` is defined by `trn_vocabulary` under `base.menu_custom`. Domain modules add their config items as children of this menu.
3. **Sequence 90** — Configuration always renders last under the app root. Domain menus use sequences 10–80.
4. **Admin-only gate** — both Settings items and the Configuration menu require `groups="base.group_system"`. Individual config items can add additional group restrictions if needed.
5. **Adding domain config items** — use `parent="trn_vocabulary.menu_trn_configuration"` with the module-qualified XML ID.
6. **Adding Settings items** — use `parent="base.menu_administration"` with an appropriate sequence (avoid conflicts with Odoo built-in items).

### XML ID Naming

| Menu level | Pattern | Example |
|---|---|---|
| App root | `menu_{app}_root` | `menu_trn_root` |
| Domain menu | `menu_{domain}` | `menu_order` |
| Domain item | `menu_{domain}_{action}` | `menu_order_all` |
| App configuration | `menu_{app}_configuration` | `menu_trn_configuration` |
| Config child | `menu_{app}_configuration_{feature}` | `menu_trn_configuration_vocabularies` |

---

## Universal Form Templates

**First**: Classify your entity using [ui-entity-classification.md](ui-entity-classification.md), then use the appropriate template.

### Master Data Form (Simple)

For categories, tags, settings, areas (<1k records, rarely change)

```xml
<form>
    <sheet>
        <div class="oe_title">
            <h1><field name="name"/></h1>
        </div>
        <group col="2">
            <group name="main_info">
                <!-- 5-10 core fields -->
            </group>
            <group name="additional_info">
                <!-- Optional fields -->
            </group>
        </group>
        <group name="extension_section" invisible="1"/>
    </sheet>
</form>
```

**Rules**: No header, no tabs, no button box

---

### Workflow Entity Form (4-Tab Standard)

For orders, requests, approvals, workflows (<10k records, state-based workflow)

```xml
<form>
    <header>
        <button name="action_{transition}" type="object" string="{Label}"
                invisible="state != '{from_state}'" class="btn-primary"/>
        <field name="state" widget="statusbar"
               statusbar_visible="draft,pending,approved"/>
    </header>

    <sheet>
        <widget name="web_ribbon" title="{State}"
                invisible="state != '{terminal_state}'" bg_color="text-bg-success"/>

        <div class="oe_button_box" name="button_box">
            <button class="oe_stat_button" type="object"
                    name="action_view_{related}" icon="fa-{icon}">
                <field name="{related}_count" widget="statinfo" string="{Related}"/>
            </button>
        </div>

        <div class="oe_title">
            <h1><field name="name" placeholder="Name..."/></h1>
        </div>

        <!-- Alert banner for actionable states -->
        <div class="alert alert-warning mb-3" invisible="state != 'pending'">
            <i class="fa fa-exclamation-triangle me-2"/>
            <strong>Action Required</strong>
            <p class="mb-0">{Action message}</p>
        </div>

        <notebook>
            <!-- Tab 1: Overview -->
            <page name="overview" string="Overview">
                <group col="2">
                    <group name="main_info"><!-- Key fields --></group>
                    <group name="status_info"><!-- Dates, state --></group>
                </group>
                <group name="additional_overview" invisible="1"/>
            </page>

            <!-- Tab 2: Relationships (entity-specific name: Line Items, Participants, etc.) -->
            <page name="relationships" string="{Relationships}">
                <field name="{related}_ids" readonly="1" nolabel="1">
                    <list limit="80" decoration-success="state == 'active'">
                        <field name="name"/>
                        <field name="state" widget="badge"/>
                    </list>
                </field>
            </page>

            <!-- Tab 3: Details (entity-specific name: Notes, Attachments, etc.) -->
            <page name="details" string="{Details}">
                <field name="{detail}_ids" nolabel="1">
                    <list limit="80" editable="bottom">
                        <!-- Use editable only if <100 line items expected -->
                    </list>
                </field>
            </page>

            <!-- Tab 4: Configuration (admin-only) -->
            <page name="configuration" string="Configuration"
                  groups="{module}.group_{entity}_validator">
                <div name="config_section"><!-- Config cards go here --></div>
                <group name="additional_config" invisible="1"/>
            </page>

            <!-- Tab 5: History (audit trail) -->
            <page name="history" string="History" groups="base.group_no_one">
                <group name="metadata">
                    <field name="create_uid" readonly="1"/>
                    <field name="create_date" readonly="1"/>
                    <field name="write_uid" readonly="1"/>
                    <field name="write_date" readonly="1"/>
                </group>
                <div name="audit_log" invisible="1"/>
            </page>
        </notebook>
    </sheet>
    <chatter/>
</form>
```

**Reference**: `trn_order/views/order_view.xml` (planned)

---

### Configuration Card Pattern

For complex multi-step configuration (3+ areas, each "configured" or "not configured")

```xml
<div class="card mb-3 shadow-sm">
    <div class="card-header d-flex justify-content-between align-items-center py-2 bg-{semantic}-subtle">
        <div class="d-flex align-items-center">
            <i class="fa fa-{icon} fa-lg me-3 text-{semantic}"/>
            <div>
                <h5 class="mb-0">{Plain Language Question}</h5>
                <small class="text-muted">{What This Configures}</small>
            </div>
        </div>
        <div class="d-flex align-items-center gap-2">
            <span class="badge rounded-pill bg-success"
                  invisible="not {config_field}">
                <i class="fa fa-check me-1"/>Configured
            </span>
            <button name="{action_method}" type="object" class="btn btn-sm btn-primary">
                Edit
            </button>
        </div>
    </div>
    <div class="card-body py-3">
        <div invisible="not {config_field}">
            <field name="{summary_field}" readonly="1"/>
        </div>
        <div invisible="{config_field}" class="text-center py-3 text-muted">
            <i class="fa fa-{icon} fa-2x mb-2"/>
            <p class="mb-0">Not configured. Click Edit to set up.</p>
        </div>
    </div>
</div>
```

**Semantic Colors**:
- `primary` + `filter`: Filtering/criteria (selection)
- `success` + `money`: Financial (invoicing)
- `info` + `calendar`: Scheduling (events)
- `warning` + `check-circle`: Validation (approval)

**Model pattern**:
```python
{config}_configured = fields.Boolean(compute='_compute_config_status', store=True)

@api.depends('{config_field}')
def _compute_config_status(self):
    for rec in self:
        rec.{config}_configured = bool(rec.{config_field})
```

**Reference**: `trn_order/views/order_config_cards_view.xml` (planned)

---

## Multi-Column Layout Patterns

### Nested Groups (Correct)

```xml
<!-- 3-column layout -->
<group name="demographics_section" col="3">
    <group><field name="birthdate"/></group>
    <group><field name="gender"/></group>
    <group><field name="age"/></group>
</group>
```

### Two-Column Split Lists

```xml
<group name="relationships_section" col="2">
    <group string="Related To">
        <field name="related_1_ids" nolabel="1">
            <list editable="bottom">...</list>
        </field>
    </group>
    <group string="Related From">
        <field name="related_2_ids" nolabel="1">
            <list editable="bottom">...</list>
        </field>
    </group>
</group>
```

---

## Extension Points

### Named Placeholders

Use invisible `<div>` or `<group>` with `name` attribute:

```xml
<!-- Base module -->
<div name="events_section" invisible="1"/>

<!-- Extending module makes visible and adds content -->
<xpath expr="//div[@name='events_section']" position="attributes">
    <attribute name="invisible">0</attribute>
</xpath>
<xpath expr="//div[@name='events_section']" position="inside">
    <separator string="Events"/>
    <field name="event_data_ids" readonly="1" nolabel="1">
        <list>...</list>
    </field>
</xpath>
```

### Standard Extension Targets

| Section | XPath Target | Used By |
|---------|--------------|---------|
| Identifiers | `//group[@name='identifier_section']` | domain module (planned) |
| Area | `//group[@name='contact_section']` | trn_area |
| Orders | `//div[@name='orders_section']` | trn_order (planned) |
| Custom | `//div[@name='custom_section']` | trn_extension (planned) |

---

## Empty States

**When to use**: Any list, tab, or section that can be empty

### Empty List Pattern

```xml
<field name="item_ids" nolabel="1">
    <list limit="80">
        <field name="name"/>
        <field name="state" widget="badge"/>
    </list>
</field>

<!-- Empty state message -->
<div class="text-center text-muted py-5" invisible="item_ids">
    <i class="fa fa-cubes fa-3x mb-3 opacity-50"/>
    <h5>No Items Found</h5>
    <p>Click "Add Items" to begin.</p>
</div>
```

### Empty Tab Pattern

```xml
<page name="documents" string="Documents">
    <field name="document_ids" invisible="1"/>

    <!-- Content when documents exist -->
    <field name="document_ids" nolabel="1" invisible="not document_ids">
        <list editable="bottom">
            <field name="name"/>
            <field name="type"/>
        </list>
    </field>

    <!-- Empty state -->
    <div class="text-center text-muted py-5" invisible="document_ids">
        <i class="fa fa-file-text-o fa-3x mb-3 opacity-50"/>
        <h5>No Documents Attached</h5>
        <p>Upload documents to track supporting evidence.</p>
        <button name="action_upload_document" string="Upload Document"
                type="object" class="btn-primary mt-2"/>
    </div>
</page>
```

### Empty State Guidelines

- **Icon**: Use relevant FontAwesome icon at `fa-3x` size with `opacity-50`
- **Heading**: Clear statement of what's missing (e.g., "No X Found")
- **Helper text**: Explain next action or why this is empty
- **Call to action**: Include action button when appropriate
- **Alignment**: `text-center` with generous padding (`py-5`)

**Reference**: Standard Odoo empty-state pattern

---

## Custom Component Loading States

**When to use**: Custom Owl components that fetch data asynchronously

**Note**: Odoo automatically handles loading states for standard forms, lists, and actions. Only implement custom loading indicators when you have async data fetching in custom components.

### Pattern

**JavaScript**:
```javascript
import { useState } from "@odoo/owl";

class MyCustomComponent extends Component {
    setup() {
        this.state = useState({
            loading: true,
            data: null,
        });

        this.loadData();
    }

    async loadData() {
        this.state.loading = true;
        try {
            const result = await this.orm.call('model.name', 'method_name', []);
            this.state.data = result;
        } finally {
            this.state.loading = false;
        }
    }
}
```

**XML Template**:
```xml
<div class="my_custom_component">
    <!-- Loading state -->
    <div t-if="state.loading" class="text-center py-5"
         role="status" aria-live="polite">
        <i class="fa fa-spinner fa-spin fa-3x text-primary" aria-hidden="true"/>
        <p class="mt-3 text-muted">Loading {context-specific message}...</p>
    </div>

    <!-- Loaded content -->
    <div t-else="">
        <t t-if="state.data">
            <!-- Your content here -->
        </t>
        <t t-else="">
            <!-- Empty state -->
        </t>
    </div>
</div>
```

### Guidelines

- **Spinner**: Use `fa-spinner fa-spin` at appropriate size (`fa-2x` for small areas, `fa-3x` for full sections)
- **Message**: Provide context-specific loading message (e.g., "Loading computed values...", "Searching records...")
- **Accessibility**: Always include `role="status" aria-live="polite"` on loading container, `aria-hidden="true"` on icon
- **Placement**: Center with `text-center` and padding (`py-5` for full sections, `py-3` for compact areas)

**Reference**: Standard Owl component loading pattern

---

## XPath Best Practices

### Use hasclass() for Class Matching

```xml
<!-- ✅ Correct: Odoo 19+ compatible -->
<xpath expr="//div[hasclass('oe_title')]" position="attributes">

<!-- ❌ Avoid: Generates warnings -->
<xpath expr="//div[@class='oe_title']" position="attributes">
```

### Target Named Elements

```xml
<!-- ✅ Preferred: Stable target -->
<xpath expr="//group[@name='contact_section']//field[@name='address']" position="before">

<!-- ❌ Avoid: Fragile -->
<xpath expr="//page[1]/group[2]/field[3]" position="after">
```

---

## List View Patterns

```xml
<list
    default_order="create_date desc"
    decoration-muted="state in ('draft', 'cancelled')"
    decoration-warning="state == 'pending'"
    decoration-success="state == 'approved'"
    decoration-danger="state == 'rejected'">

    <field name="name"/>
    <field name="state" widget="badge"
           decoration-success="state == 'approved'"
           decoration-warning="state == 'pending'"/>
    <field name="optional_field" optional="show"/>
    <field name="advanced_field" optional="hide"/>
    <field name="amount" sum="Total" widget="monetary"/>
</list>
```

**Note**: Odoo defaults to `limit="80"` - only set explicitly if you need a different value.

**Performance**: See [ui-performance.md](ui-performance.md) for limit rules, optional fields strategy

---

## Search View Patterns

```xml
<search>
    <!-- Quick search fields -->
    <field name="name"/>
    <field name="reference"/>

    <separator/>

    <!-- Ownership filters -->
    <filter name="my_records" string="My Records"
            domain="[('user_id', '=', uid)]"/>

    <separator/>

    <!-- State filters -->
    <filter name="state_pending" string="Pending"
            domain="[('state', '=', 'pending')]"/>

    <separator/>

    <!-- Date filters -->
    <filter name="today" string="Today"
            domain="[('date', '=', context_today())]"/>

    <!-- Group by -->
    <group>
        <filter name="group_state" string="State"
                context="{'group_by': 'state'}"/>
    </group>

    <!-- Conditional search panel (see ui-performance.md for thresholds) -->
    <searchpanel t-if="record_count &lt; 100000">
        <field name="parent_id" select="multi" icon="fa-folder" enable_counters="1"/>
        <field name="state" select="multi" icon="fa-tasks" enable_counters="1"/>
    </searchpanel>
</search>
```

**Performance**: See [ui-performance.md](ui-performance.md) for search panel decision logic

---

## Widget Selection Guide

### Status & State Widgets

| Widget | Use In | Purpose |
|--------|--------|---------|
| `statusbar` | Form header | Show workflow progression |
| `web_ribbon` | Sheet top | Highlight terminal states |
| `badge` | List/Form | Categorical field values |

### Field Widgets

| Widget | Use For | Notes |
|--------|---------|-------|
| `boolean_toggle` | Boolean fields | Cleaner than checkbox |
| `priority` | Star-based ranking | 0-3 star display |
| `monetary` | Currency amounts | Respects currency formatting |
| `many2one_avatar_user` | User references | Shows avatar in lists |
| `many2many_tags` | Tag fields | Colorful, compact display |
| `image` | Photos/avatars | Use `options="{'size': [80, 80]}"` |
| `statinfo` | Button box | Stats with icon and count |
| `handle` | Sequence fields | Drag-to-reorder in lists |
| `timeago` | Timestamps | Shows "2 hours ago" style |

---

## Dashboard & KPI Patterns

### KPI Card Structure

```xml
<kanban class="o_kanban_dashboard">
    <templates>
        <t t-name="card">
            <div class="row g-2">
                <div class="col-6">
                    <div class="border rounded p-2 h-100">
                        <a type="object" name="action_view_donations">
                            <div class="d-flex align-items-center">
                                <i class="fa fa-gift fa-lg text-success me-2"/>
                                <div>
                                    <div class="fw-bold">
                                        <field name="donation_count"/> Donations
                                    </div>
                                    <div class="text-muted small">
                                        <field name="donation_value" widget="monetary"/>
                                    </div>
                                </div>
                            </div>
                        </a>
                    </div>
                </div>
            </div>
        </t>
    </templates>
</kanban>
```

### Bootstrap Classes Reference

| Class | Purpose |
|-------|---------|
| `row g-2` | Grid row with small gutters |
| `col-6`, `col-4` | Column widths (6=half, 4=third) |
| `d-flex align-items-center` | Horizontal alignment |
| `border rounded p-2` | Card appearance |
| `h-100` | Full height |
| `fw-bold` | Bold text |
| `text-muted small` | Secondary text |

---

## Analytics Views

### View Mode by Entity Class

See [ui-entity-classification.md](ui-entity-classification.md) for which view types to include.

**Workflow entities** should include `list,kanban,form,graph,pivot` in `view_mode`.

### Kanban with Progressbar

```xml
<kanban default_group_by="state" quick_create="false">
    <progressbar field="state"
                 colors='{"draft": "secondary", "pending": "warning",
                         "approved": "success", "rejected": "danger"}'/>
    <templates>
        <t t-name="card">...</t>
    </templates>
</kanban>
```

**Performance**: See [ui-performance.md](ui-performance.md) for analytics at scale (>100k records)

---

## Calendar Views

For time-based records (cycles, appointments, events):

```xml
<calendar date_start="start_date" date_stop="end_date"
          color="state" mode="month" quick_create="0">
    <field name="name"/>
    <field name="user_id" widget="many2one_avatar_user"/>
</calendar>
```

**Performance**: Calendar views work best with <1k events in typical view

---

## Help Text Guidelines

```xml
<field name="source_type" help="Where does this variable get its data from?"/>
<field name="unit" help="e.g., PHP, USD, years, kg"/>
```

**Best practices**:
- Keep concise (one sentence)
- Explain purpose, not just field name
- Prioritize workflow-affecting fields, computed fields
- Skip self-explanatory fields

---

## Reference Implementations

| Pattern | File | Lines |
|---------|------|-------|
| Workflow Entity Form | `trn_order/views/order_view.xml` (planned) | — |
| Configuration Cards | `trn_order/views/order_config_cards_view.xml` (planned) | — |
| Master Data Form | `trn_area/views/area.xml` | Full file |
| Master Data Form (Vocabulary) | `trn_vocabulary/views/vocabulary_views.xml` | Full file |

---

## Checklist

### For All Forms

- [ ] Header contains only buttons and statusbar
- [ ] All sections have named groups for extensibility
- [ ] Multi-column sections use nested group pattern
- [ ] XPath uses `hasclass()` not `@class`
- [ ] List views use optional columns (Odoo defaults to limit="80")

### For Workflow Entities

- [ ] 4-5 tab structure (Overview, Relationships, Details, Configuration, History)
- [ ] Button box with stat buttons
- [ ] Alert banners for actionable states
- [ ] Configuration tab permission-gated

### For Large O2M Fields

- [ ] Readonly lists (Odoo defaults to limit="40" for O2M)
- [ ] Stat button shows count
- [ ] Wizard or import pattern (not inline editable)

### Accessibility

- [ ] State indicated by icon AND color (not color alone)
- [ ] All icon-only buttons have `aria-label`
- [ ] Loading states use `role="status" aria-live="polite"`
- [ ] Icons in loading spinners have `aria-hidden="true"`
- [ ] Empty states provide clear guidance on next action
- [ ] Focus order follows visual order
- [ ] All interactive elements meet WCAG AA contrast ratio (4.5:1)

---

**See also**: [error-handling.md](error-handling.md) for user-facing error messages
