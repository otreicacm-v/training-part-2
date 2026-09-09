# UI Performance at Scale

Performance patterns for handling millions of records in Training Sample.

---

## List Views

### List Limit

**Default**: Odoo automatically limits list views to **80 records** (40 for embedded O2M lists)

**Rule**: Only set `limit` explicitly if you need a different value (higher or lower)

```xml
<!-- Not needed - 80 is already the default -->
<list default_order="create_date desc">

<!-- Only if you need more/fewer records -->
<list limit="40" default_order="create_date desc">  <!-- Smaller page size -->
<list limit="200" default_order="create_date desc">  <!-- Larger page size for small datasets -->
```

**Why**: Odoo's default of 80 is optimized for performance. Only override when you have specific requirements.

---

### Avoid Non-Stored Computed Fields

**Rule**: Never show computed fields without `store=True` in lists

```python
# ❌ BAD - runs compute per row
field_name = fields.Char(compute='_compute_field')

# ✅ GOOD - stored, indexed
field_name = fields.Char(compute='_compute_field', store=True)
```

**Why**: Non-stored computes run N queries (one per row)

---

### Use Optional Fields

**Rule**: Hide expensive/advanced fields by default

```xml
<field name="core_field"/>  <!-- Always visible -->
<field name="optional_field" optional="show"/>  <!-- Shown by default, hideable -->
<field name="advanced_field" optional="hide"/>  <!-- Hidden by default -->
```

**Why**: Reduces initial load, users can enable if needed

---

### Index Default Order

**Rule**: Order by indexed fields (create_date, write_date, state), not computed

```xml
<!-- ✅ GOOD - indexed -->
<list default_order="create_date desc">

<!-- ❌ BAD - computed field, slow -->
<list default_order="computed_score desc">
```

---

### Results Truncated UI

**When results exceed the list limit, users need to know results are truncated.**

**Pattern**: Show info banner above list when count exceeds limit (80 by default, or custom limit)

```xml
<search>
    <field name="name"/>
    <!-- ... search filters ... -->
</search>

<!-- Info banner for truncated results -->
<div class="alert alert-info mb-0" invisible="not context.get('truncated_results')">
    <i class="fa fa-info-circle me-2"/>
    <strong>Showing first 80 of <t t-esc="context.get('total_count')"/> results.</strong>
    Use filters to narrow your search.
</div>

<list>
    <!-- ... -->
</list>
```

**Python**: Set context in action or search method

```python
@api.model
def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
    # Get total count for context
    total_count = self.search_count(domain or [])
    limit = limit or 80

    # Call super
    result = super().search_read(domain, fields, offset, limit, order)

    # Add context for UI
    if total_count > limit:
        self.env.context = dict(self.env.context, truncated_results=True, total_count=total_count)

    return result
```

**Alternative (Simpler)**: Use Odoo's built-in pager, which automatically shows "1-80 of 12,543"

---

## Search Panels

### Decision Thresholds

| Record Count | Search Panel | Counters | Fields to Include | Rationale |
|--------------|--------------|----------|-------------------|-----------|
| <1k | ✅ Enable | ✅ Yes | All relevant fields | Fast, all counts instant |
| 1k-100k | ✅ Enable | ✅ Yes | All relevant fields | Acceptable latency (<2s) |
| 100k-1M | ⚠️ Enable | ❌ No | All relevant fields | Facets useful, counts expensive |
| >1M | ⚠️ Enable | ❌ No | **Indexed fields only** | Field officers need faceted search; limit to state, area, program |

**Critical for >1M records**: Do not disable search panels entirely. Users searching for specific records among millions still need faceted filtering. Instead:
- Limit to indexed fields only (state, area_id, program_id)
- Disable all counters
- Show warning: "Results may be incomplete - use Area filter to narrow search"
- Consider two-step flow: require Area selection before showing full list

---

### Runtime Check Pattern

```python
def _get_search_panel_config(self):
    """Universal search panel decision logic"""
    record_count = self.search_count([])

    # For >1M: Enable but limit to indexed fields only
    if record_count > 1_000_000:
        return {
            'enabled': True,
            'counters': False,
            'indexed_only': True,  # Only state, area_id, program_id
            'show_warning': True
        }

    # For 100k-1M: Enable all fields but no counters
    if record_count > 100_000:
        return {'enabled': True, 'counters': False}

    # Check feature flag
    enable = self.env['ir.config_parameter'].sudo().get_param(
        'trn.ui.enable_search_panels', 'True'
    ) == 'True'

    return {'enabled': enable, 'counters': True}
```

---

### XML Implementation

```xml
<searchpanel t-if="record_count &lt; 100000">
    <!-- Parent entity - enable counters if <100 options -->
    <field name="parent_id" select="multi" icon="fa-folder"
           enable_counters="1"/>

    <!-- State - cheap to count (indexed) -->
    <field name="state" select="multi" icon="fa-tasks"
           enable_counters="1"/>
</searchpanel>
```

**Reference**: Search panels may need to be disabled for models with >1M records

---

## Large O2M Fields

### Decision Tree

| Expected Count | Pattern | UI Elements | Notes |
|----------------|---------|-------------|-------|
| <200 | Inline editable | `<list editable="bottom">` | Safe for simple fields |
| <50 (with computed) | Inline editable | `<list editable="bottom">` | Lower if fields trigger computes |
| 200-10k | Readonly + Wizard | Stat button + wizard for add/remove | Browser-friendly pagination |
| >10k | Import/Export | CSV import + bulk operations | Browser crashes at >10k inline |

**Caveat**: If inline edits involve computed fields or related lookups, reduce threshold to 50 records.

---

### Medium O2M (200-10k)

```xml
<!-- Button box shows count -->
<div class="oe_button_box">
    <button class="oe_stat_button" type="object"
            name="action_view_items" icon="fa-cubes">
        <field name="item_count" widget="statinfo"
               string="Items"/>
    </button>
</div>

<!-- Tab shows readonly list with limit -->
<page name="items" string="Items">
    <button name="action_add_items" string="Add"
            type="object" class="btn-primary"/>

    <field name="item_ids" readonly="1" nolabel="1">
        <list limit="80" decoration-success="state == 'active'">
            <field name="product_id"/>
            <field name="state" widget="badge"/>
        </list>
    </field>
</page>

<!-- Separate action for full view with search -->
<record id="action_view_items" model="ir.actions.act_window">
    <field name="res_model">trn.order.line</field>
    <field name="view_mode">list,form</field>
    <field name="domain">[('order_id', '=', active_id)]</field>
</record>
```

**Why**: Readonly lists paginate automatically, editable lists load all records

**Reference**: `trn_order/views/order_view.xml` (planned)

---

### Large O2M (>10k)

```xml
<page name="items" string="Items">
    <group>
        <field name="item_count" readonly="1"/>
        <field name="last_import_date" readonly="1"/>
    </group>

    <div class="row mt-3">
        <div class="col-6">
            <button name="action_import_items"
                    string="Import CSV" icon="fa-upload"
                    type="object" class="btn-primary"/>
        </div>
        <div class="col-6">
            <button name="action_export_items"
                    string="Export CSV" icon="fa-download"
                    type="object" class="btn-secondary"/>
        </div>
    </div>
</page>
```

**Why**: Browser crashes loading >10k rows, import is more efficient

**Import pattern**: See `trn_area/wizards/area_import_wizard.py`

---

## Analytics at Scale

### Decision Tree

| Record Count | Strategy | Implementation |
|--------------|----------|----------------|
| <1k | Real-time | Include graph,pivot in `view_mode` |
| 1k-100k | Separate action | Bounded domain (last 30 days) |
| >100k | Pre-aggregated | Dashboard with cron job |

---

### Real-Time Analytics (<1k)

```python
{
    'view_mode': 'list,kanban,form,graph,pivot',
    'context': {
        'graph_measure': 'patient_count',
        'graph_groupby': 'state',
        'search_default_this_month': 1  # Default filter
    }
}
```

---

### Separate Analytics (1k-100k)

```python
# Main action
{
    'name': 'Programs',
    'view_mode': 'list,kanban,form',
}

# Analytics action (separate menu item)
{
    'name': 'Program Analytics',
    'view_mode': 'graph,pivot',
    'domain': [
        ('create_date', '>=', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    ],
    'context': {'search_default_last_30_days': 1}
}
```

---

### Pre-Aggregated Dashboard (>100k) — planned

**Use a pre-aggregation pattern**:

1. Define a dashboard metric model to store aggregated values:
```python
class DashboardMetric(models.Model):
    _name = "trn.dashboard.metric"
    _description = "Pre-aggregated dashboard metric"

    name = fields.Char(required=True)
    value = fields.Float()
    period = fields.Date()
    computed_date = fields.Datetime()
```

2. Cron job aggregates (1st of month at 2am):
```xml
<record id="cron_compute_metrics" model="ir.cron">
    <field name="name">Compute Dashboard Metrics</field>
    <field name="model_id" ref="model_trn_dashboard_metric"/>
    <field name="state">code</field>
    <field name="code">model._cron_compute_monthly_metrics()</field>
    <field name="interval_number">1</field>
    <field name="interval_type">months</field>
</record>
```

3. Display in spreadsheet dashboard

**Reference**: `trn_dashboard/` (planned)

---

## Stat Button Counts

### Always Store Counts

**Rule**: Count fields MUST use `store=True`

```python
# ✅ GOOD - stored, updated on trigger
item_count = fields.Integer(
    compute='_compute_item_count',
    store=True
)

@api.depends('item_ids')
def _compute_item_count(self):
    for rec in self:
        rec.item_count = len(rec.item_ids)
```

```python
# ❌ BAD - runs search_count on every form load
item_count = fields.Integer(compute='_compute_item_count')

def _compute_item_count(self):
    for rec in self:
        rec.item_count = self.env['trn.order.line'].search_count([
            ('order_id', '=', rec.id)
        ])
```

**Why**: `search_count` runs expensive queries, stored fields use cached values

**Reference**: `trn_order/models/order.py` (planned)

---

## Progressive Enhancement

For deployment-specific performance tuning:

```python
# models/res_config_settings.py
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_search_panels = fields.Boolean(
        string='Enable Search Panels',
        config_parameter='trn.ui.enable_search_panels',
        help='Disable on large deployments for performance'
    )

    search_panel_max_records = fields.Integer(
        string='Search Panel Threshold',
        config_parameter='trn.ui.search_panel_max_records',
        default=100000,
        help='Disable search panels if records exceed this count'
    )
```

**Reference**: See `res_config_settings.py` patterns (SLA settings pattern)

---

## Reference Files

| Pattern | File | Lines |
|---------|------|-------|
| Readonly O2M + wizard | `trn_order/views/order_view.xml` (planned) | — |
| Stat button counts | `trn_order/models/order.py` (planned) | — |
| Import wizard | `trn_area/wizards/area_import_wizard.py` | Full file |
| Dashboard pattern | `trn_dashboard/` (planned) | — |
| Settings UI | See `res_config_settings.py` patterns | Full file |

---

**See also**: [ui-entity-classification.md](ui-entity-classification.md), [ui-design.md](ui-design.md), [performance-scalability.md](performance-scalability.md)
