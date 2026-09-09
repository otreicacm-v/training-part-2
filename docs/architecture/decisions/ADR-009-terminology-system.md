# ADR-009: Vocabulary System for Multi-Domain Registries

**Status:** **IMPLEMENTED** - Production ready
**Date:** 2025-11-28
**Implementation Date:** 2025-12-04
**Deciders:** Architecture Team

> **Scope note:** This ADR was written for a prior vocabulary system. The current
> `trn_vocabulary` module (v19.0.1.0.0) implements a simplified subset: `trn.vocabulary` and
> `trn.vocabulary.code` with URI computation, system protection, and cached lookups. Hierarchy,
> mappings, concept groups, and deployment profiles described here are deferred features. Module
> references updated to current names below.

### Implementation Summary

| Component | Status | Notes |
|-----------|--------|-------|
| trn.vocabulary | ✅ Complete | With namespace_uri, is_system |
| trn.vocabulary.code | ✅ Complete | With URI field (`namespace#code`) |
| trn.vocabulary.mapping | ⏭️ Deferred | Not in v1 |
| trn.vocabulary.concept.group | ⏭️ Deferred | Not in v1 |
| trn.deployment.profile | ⏭️ Deferred | Not in v1 |
| trn.vocabulary.selection | ⏭️ Deferred | Not in v1 |
| Standard vocabularies | ✅ Complete | Gender (ISO 5218), civil status, blood type, identifier types |
| Cached lookups | ✅ Complete | O(1) by namespace+code and URI |

**Code Location:** `trn_vocabulary/` module (v19.0.1.0.0)

## Context

The system aims to support multiple domains:

| Domain | Examples |
|--------|----------|
| Core | Gender, relationship types, marital status |
| Classification | Categories, priorities, severity levels |
| Administration | Departments, roles, facilities |
| Operations | Order types, status codes, action types |
| Finance | Payment methods, currencies, account types |
| Compliance | Document types, approval statuses |

**Current approach:** Coded values are scattered across modules as:
1. `fields.Selection` with hardcoded choices in Python
2. Some `Many2one` to configurable models (e.g., `trn.gender.type`)
3. No standardization or mapping to international standards

**Problems:**
1. Adding new codes requires code changes and module updates
2. No interoperability between deployments using different codes
3. No way to map local codes to international standards (WHO ICF, ILO ISCO, FAO)
4. Inconsistent patterns across modules
5. Reporting across deployments requires manual mapping

**Industry alignment:** This design is inspired by FHIR CodeSystem/ValueSet patterns but uses generic naming suitable for any domain.

## Decision

Implement a unified vocabulary system with:
1. **Vocabularies** - Collections of codes with global namespace URIs
2. **Codes** - Individual values with optional hierarchy
3. **Mappings** - Translations between vocabularies
4. Replace `Selection` fields with `Many2one` to codes for extensible values

### Namespace Principle

**Use international standards where they exist.** Only create project-specific vocabularies (`urn:tpl:vocab:*`) when no well-accepted standard is available.

| Domain | Standard | Namespace |
|--------|----------|-----------|
| Gender | ISO 5218 | `urn:iso:std:iso:5218` |
| Disability | WHO ICF | `urn:who:icf:b` (body functions), `urn:who:icf:d` (activities) |
| Occupation | ILO ISCO-08 | `urn:ilo:isco-08` |
| Country | ISO 3166-1 | `urn:iso:std:iso:3166-1` |
| Currency | ISO 4217 | `urn:iso:std:iso:4217` |
| Language | ISO 639 | `urn:iso:std:iso:639` |
| Diagnoses | ICD-10/11 | `urn:who:icd:10`, `urn:who:icd:11` |
| Education Level | UNESCO ISCED 2011 | `urn:unesco:isced:2011` |
| Relationship types | (no standard) | `urn:tpl:vocab:relationship` |
| Marital status | UN Pop Census Principles | `urn:un:unsd:pop-census:marital-status` |

## Implementation

### Module Structure

```
trn_vocabulary/
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── vocabulary.py
│   └── vocabulary_code.py
├── data/
│   ├── vocabulary_gender.xml
│   ├── vocabulary_relationship.xml
│   ├── vocabulary_marital_status.xml
│   └── vocabulary_id_document_type.xml
├── views/
│   ├── vocabulary_views.xml
│   └── vocabulary_code_views.xml
├── security/
│   └── ir.model.access.csv
└── static/description/
    └── icon.png
```

### 1. Vocabulary Model

**File:** `trn_vocabulary/models/vocabulary.py`

```python
from odoo import api, fields, models


class Vocabulary(models.Model):
    """A collection of codes with a namespace"""
    _name = "trn.vocabulary"
    _description = "Vocabulary"
    _order = "name"

    name = fields.Char(
        required=True,
        translate=True,
        help="Human-readable name: 'Gender', 'Relationship Type'",
    )
    namespace_uri = fields.Char(
        required=True,
        index=True,
        help="Globally unique URI. Examples:\n"
             "- urn:iso:std:iso:5218 (ISO Gender)\n"
             "- urn:who:icf (WHO ICF Disability)\n"
             "- urn:tpl:vocab:{name} (project-defined)",
    )
    version = fields.Char(
        help="Version of the vocabulary (e.g., '2024')",
    )
    description = fields.Text(translate=True)
    reference_url = fields.Char(
        string="Reference URL",
        help="Link to official documentation",
    )

    # Characteristics
    is_system = fields.Boolean(
        default=False,
        help="System vocabularies cannot be edited by users",
    )
    is_hierarchical = fields.Boolean(
        default=False,
        help="Codes can have parent/child relationships",
    )
    domain = fields.Selection([
        ("core", "Core"),
        ("operations", "Operations"),
        ("administrative", "Administrative"),
        ("identity", "Identity"),
        ("regulatory", "Regulatory"),
        ("health", "Health"),
        ("education", "Education"),
    ], default="core", required=True, index=True)

    code_ids = fields.One2many("trn.vocabulary.code", "vocabulary_id", string="Codes")
    code_count = fields.Integer(compute="_compute_code_count")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("unique_namespace", "UNIQUE(namespace_uri)", "Namespace URI must be unique"),
    ]

    @api.depends("code_ids")
    def _compute_code_count(self):
        for rec in self:
            rec.code_count = len(rec.code_ids)

    def action_view_codes(self):
        """Open codes for this vocabulary"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Codes: {self.name}",
            "res_model": "trn.vocabulary.code",
            "view_mode": "list,form",
            "domain": [("vocabulary_id", "=", self.id)],
            "context": {"default_vocabulary_id": self.id},
        }
```

### 2. Vocabulary Code Model

**File:** `trn_vocabulary/models/vocabulary_code.py`

```python
from odoo import api, fields, models, tools
from odoo.exceptions import UserError


class VocabularyCode(models.Model):
    """A single code within a vocabulary"""
    _name = "trn.vocabulary.code"
    _description = "Vocabulary Code"
    _order = "sequence, code"
    _rec_name = "display"

    vocabulary_id = fields.Many2one(
        "trn.vocabulary",
        required=True,
        ondelete="cascade",
        index=True,
    )
    namespace_uri = fields.Char(
        related="vocabulary_id.namespace_uri",
        store=True,
        index=True,
    )

    code = fields.Char(
        required=True,
        index=True,
        help="Machine-readable code (e.g., 'M', 'head', 'crop')",
    )
    display = fields.Char(
        required=True,
        translate=True,
        help="Human-readable label",
    )
    definition = fields.Text(
        translate=True,
        help="Formal definition of what this code means",
    )
    sequence = fields.Integer(default=10)

    # Hierarchy (optional)
    parent_id = fields.Many2one(
        "trn.vocabulary.code",
        string="Parent",
        ondelete="cascade",
        domain="[('vocabulary_id', '=', vocabulary_id)]",
    )
    child_ids = fields.One2many("trn.vocabulary.code", "parent_id", string="Children")
    level = fields.Integer(compute="_compute_level", store=True)

    # Lifecycle
    active = fields.Boolean(default=True)
    deprecated = fields.Boolean(default=False)
    deprecated_date = fields.Date()
    replaced_by_id = fields.Many2one(
        "trn.vocabulary.code",
        string="Replaced By",
        help="If deprecated, the code that supersedes this one",
    )

    # Mapping to other vocabularies
    mapping_ids = fields.One2many(
        "trn.vocabulary.mapping",
        "source_id",
        string="Mappings",
    )

    _sql_constraints = [
        ("unique_code", "UNIQUE(vocabulary_id, code)", "Code must be unique within vocabulary"),
    ]

    @api.depends("parent_id", "parent_id.level")
    def _compute_level(self):
        for rec in self:
            rec.level = (rec.parent_id.level + 1) if rec.parent_id else 0

    def name_get(self):
        return [(rec.id, f"{rec.display} ({rec.code})") for rec in self]

    @api.model
    @tools.ormcache("namespace_uri", "code")
    def _get_code_id(self, namespace_uri, code):
        """Cached lookup by namespace + code"""
        rec = self.search([
            ("namespace_uri", "=", namespace_uri),
            ("code", "=", code),
            ("active", "=", True),
        ], limit=1)
        return rec.id if rec else False

    @api.model
    def get_code(self, namespace_uri, code):
        """Get code record by namespace URI and code value"""
        code_id = self._get_code_id(namespace_uri, code)
        return self.browse(code_id) if code_id else self.browse()

    @api.model
    def get_or_create(self, namespace_uri, code, display=None):
        """Get existing code or create if vocabulary allows"""
        # Search for both active and inactive to avoid unique constraint violation
        existing = self.with_context(active_test=False).search([
            ("namespace_uri", "=", namespace_uri),
            ("code", "=", code),
        ], limit=1)

        if existing:
            if not existing.active:
                raise UserError(
                    f"Code '{code}' exists but is inactive in vocabulary "
                    f"'{namespace_uri}'. Reactivate it if needed."
                )
            return existing

        vocab = self.env["trn.vocabulary"].search([
            ("namespace_uri", "=", namespace_uri)
        ], limit=1)
        if not vocab:
            raise UserError(f"Vocabulary not found: {namespace_uri}")
        if vocab.is_system:
            raise UserError(f"Cannot add codes to system vocabulary: {vocab.name}")

        self.clear_caches()  # Clear ormcache
        return self.create({
            "vocabulary_id": vocab.id,
            "code": code,
            "display": display or code,
        })

    @api.model_create_multi
    def create(self, vals_list):
        self.clear_caches()
        return super().create(vals_list)

    def write(self, vals):
        if "code" in vals or "active" in vals:
            self.clear_caches()
        return super().write(vals)

    def unlink(self):
        self.clear_caches()
        return super().unlink()
```

### 3. Vocabulary Mapping Model

**File:** `trn_vocabulary/models/vocabulary_mapping.py`

```python
from odoo import api, fields, models


class VocabularyMapping(models.Model):
    """Maps codes between different vocabularies"""
    _name = "trn.vocabulary.mapping"
    _description = "Vocabulary Code Mapping"
    _rec_name = "display_name"

    source_id = fields.Many2one(
        "trn.vocabulary.code",
        required=True,
        ondelete="cascade",
        index=True,
    )
    target_id = fields.Many2one(
        "trn.vocabulary.code",
        required=True,
        ondelete="cascade",
        index=True,
    )
    equivalence = fields.Selection([
        ("equivalent", "Equivalent"),
        ("wider", "Wider (target more general)"),
        ("narrower", "Narrower (target more specific)"),
        ("inexact", "Inexact"),
    ], required=True, default="equivalent")
    comment = fields.Text()

    display_name = fields.Char(compute="_compute_display_name", store=True)

    _sql_constraints = [
        ("unique_mapping", "UNIQUE(source_id, target_id)", "Mapping already exists"),
    ]

    @api.depends("source_id", "target_id")
    def _compute_display_name(self):
        for rec in self:
            src = rec.source_id
            tgt = rec.target_id
            rec.display_name = f"{src.code} → {tgt.code} ({rec.equivalence})"

    @api.model
    def map_code(self, source_namespace, source_code, target_namespace):
        """Find equivalent code in target vocabulary"""
        mapping = self.search([
            ("source_id.namespace_uri", "=", source_namespace),
            ("source_id.code", "=", source_code),
            ("target_id.namespace_uri", "=", target_namespace),
        ], limit=1)
        return mapping.target_id if mapping else False
```

### 4. Core Vocabularies (Seed Data)

**File:** `trn_vocabulary/data/vocabulary_gender.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="vocab_gender" model="trn.vocabulary">
        <field name="name">Gender</field>
        <field name="namespace_uri">urn:iso:std:iso:5218</field>
        <field name="version">2004</field>
        <field name="is_system">True</field>
        <field name="domain">core</field>
        <field name="reference_url">https://www.iso.org/standard/36266.html</field>
    </record>

    <record id="code_gender_unknown" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_gender"/>
        <field name="code">0</field>
        <field name="display">Not Known</field>
        <field name="sequence">1</field>
    </record>
    <record id="code_gender_male" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_gender"/>
        <field name="code">1</field>
        <field name="display">Male</field>
        <field name="sequence">2</field>
    </record>
    <record id="code_gender_female" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_gender"/>
        <field name="code">2</field>
        <field name="display">Female</field>
        <field name="sequence">3</field>
    </record>
    <record id="code_gender_na" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_gender"/>
        <field name="code">9</field>
        <field name="display">Not Applicable</field>
        <field name="sequence">4</field>
    </record>
</odoo>
```

**File:** `trn_vocabulary/data/vocabulary_relationship.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="vocab_relationship" model="trn.vocabulary">
        <field name="name">Relationship Type</field>
        <field name="namespace_uri">urn:tpl:vocab:relationship</field>
        <field name="is_system">True</field>
        <field name="domain">core</field>
    </record>

    <record id="code_rel_head" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">head</field>
        <field name="display">Head of Household</field>
        <field name="sequence">1</field>
    </record>
    <record id="code_rel_spouse" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">spouse</field>
        <field name="display">Spouse/Partner</field>
        <field name="sequence">2</field>
    </record>
    <record id="code_rel_child" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">child</field>
        <field name="display">Child</field>
        <field name="sequence">3</field>
    </record>
    <record id="code_rel_parent" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">parent</field>
        <field name="display">Parent</field>
        <field name="sequence">4</field>
    </record>
    <record id="code_rel_sibling" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">sibling</field>
        <field name="display">Sibling</field>
        <field name="sequence">5</field>
    </record>
    <record id="code_rel_grandparent" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">grandparent</field>
        <field name="display">Grandparent</field>
        <field name="sequence">6</field>
    </record>
    <record id="code_rel_grandchild" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">grandchild</field>
        <field name="display">Grandchild</field>
        <field name="sequence">7</field>
    </record>
    <record id="code_rel_other" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">other_relative</field>
        <field name="display">Other Relative</field>
        <field name="sequence">8</field>
    </record>
    <record id="code_rel_non_relative" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_relationship"/>
        <field name="code">non_relative</field>
        <field name="display">Non-Relative</field>
        <field name="sequence">9</field>
    </record>
</odoo>
```

**File:** `trn_vocabulary/data/vocabulary_marital_status.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="vocab_marital" model="trn.vocabulary">
        <field name="name">Marital Status</field>
        <field name="namespace_uri">urn:un:unsd:pop-census:marital-status</field>
        <field name="is_system">True</field>
        <field name="domain">core</field>
    </record>

    <record id="code_marital_single" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_marital"/>
        <field name="code">S</field>
        <field name="display">Single</field>
    </record>
    <record id="code_marital_married" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_marital"/>
        <field name="code">M</field>
        <field name="display">Married</field>
    </record>
    <record id="code_marital_widowed" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_marital"/>
        <field name="code">W</field>
        <field name="display">Widowed</field>
    </record>
    <record id="code_marital_divorced" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_marital"/>
        <field name="code">D</field>
        <field name="display">Divorced</field>
    </record>
    <record id="code_marital_separated" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_marital"/>
        <field name="code">L</field>
        <field name="display">Separated</field>
    </record>
    <record id="code_marital_civil_union" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_marital"/>
        <field name="code">C</field>
        <field name="display">Civil Union</field>
    </record>
</odoo>
```

### 5. Usage in Models

**Before (hardcoded Selection):**
```python
class ResPartner(models.Model):
    _inherit = "res.partner"

    gender = fields.Selection([
        ("male", "Male"),
        ("female", "Female"),
    ])
```

**After (vocabulary-based):**
```python
class ResPartner(models.Model):
    _inherit = "res.partner"

    gender_id = fields.Many2one(
        "trn.vocabulary.code",
        string="Gender",
        domain="[('namespace_uri', '=', 'urn:iso:std:iso:5218')]",
        tracking=True,
    )
```

### 6. Domain-Specific Vocabularies (Other Modules)

**File:** `trn_disability/data/vocabulary_disability.xml` (planned)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <!-- WHO ICF Body Functions (b codes) -->
    <record id="vocab_icf_body_functions" model="trn.vocabulary">
        <field name="name">WHO ICF - Body Functions</field>
        <field name="namespace_uri">urn:who:icf:b</field>
        <field name="is_system">True</field>
        <field name="is_hierarchical">True</field>
        <field name="domain">disability</field>
        <field name="reference_url">https://icd.who.int/dev11/l-icf/en</field>
        <field name="description">WHO International Classification of Functioning - Body Functions component</field>
    </record>

    <record id="code_icf_b2" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_icf_body_functions"/>
        <field name="code">b2</field>
        <field name="display">Sensory functions and pain</field>
    </record>
    <record id="code_icf_b210" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_icf_body_functions"/>
        <field name="code">b210</field>
        <field name="display">Seeing functions</field>
        <field name="parent_id" ref="code_icf_b2"/>
    </record>
    <record id="code_icf_b230" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_icf_body_functions"/>
        <field name="code">b230</field>
        <field name="display">Hearing functions</field>
        <field name="parent_id" ref="code_icf_b2"/>
    </record>
    <record id="code_icf_b7" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_icf_body_functions"/>
        <field name="code">b7</field>
        <field name="display">Neuromusculoskeletal and movement-related functions</field>
    </record>
</odoo>
```

**File:** `trn_clinical/data/vocabulary_encounter_type.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <!-- Order types (project-defined) -->
    <record id="vocab_order_type" model="trn.vocabulary">
        <field name="name">Order Type</field>
        <field name="namespace_uri">urn:tpl:vocab:order-type</field>
        <field name="domain">operations</field>
    </record>

    <record id="code_order_standard" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_order_type"/>
        <field name="code">standard</field>
        <field name="display">Standard Order</field>
    </record>
    <record id="code_order_express" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_order_type"/>
        <field name="code">express</field>
        <field name="display">Express Order</field>
    </record>
    <record id="code_order_bulk" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_order_type"/>
        <field name="code">bulk</field>
        <field name="display">Bulk Order</field>
    </record>

    <!-- Priority levels vocabulary -->
    <record id="vocab_priority" model="trn.vocabulary">
        <field name="name">Priority Level</field>
        <field name="namespace_uri">urn:tpl:vocab:priority</field>
        <field name="is_system">True</field>
        <field name="domain">operations</field>
        <field name="description">Priority classification for work items</field>
    </record>

    <!-- Example ICD-10 codes (subset) -->
    <record id="code_icd10_j06" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_icd10"/>
        <field name="code">J06.9</field>
        <field name="display">Acute upper respiratory infection, unspecified</field>
    </record>
    <record id="code_icd10_e11" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_icd10"/>
        <field name="code">E11</field>
        <field name="display">Type 2 diabetes mellitus</field>
    </record>
    <record id="code_icd10_i10" model="trn.vocabulary.code">
        <field name="vocabulary_id" ref="vocab_icd10"/>
        <field name="code">I10</field>
        <field name="display">Essential (primary) hypertension</field>
    </record>
</odoo>
```

---

## Code Migration Strategy

For V2, existing modules need to migrate from Selection fields to vocabulary-based fields. Here's the approach:

### Phase 1: Identify Fields to Migrate

| Module | Current Field | New Field | Vocabulary | Standard |
|--------|---------------|-----------|------------|----------|
| `trn_contact` | `gender` (Selection) | `gender_id` | `urn:iso:std:iso:5218` | ISO 5218 |
| `trn_contact` | `civil_status` (Selection) | `civil_status_id` | `urn:un:unsd:pop-census:marital-status` | UN Pop Census |
| `trn_contact` | `blood_type` (Selection) | `blood_type_id` | `urn:tpl:vocab:blood-type` | (none) |
| `trn_clinical` | `encounter_type` (Selection) | `encounter_type_id` | `urn:tpl:vocab:encounter-type` | (none) |
| `trn_clinical` | `diagnosis` (Selection) | `diagnosis_ids` | `urn:who:icd:10` | WHO ICD-10 |
| `trn_disability` (planned) | `disability_type` (Selection) | `disability_ids` | `urn:who:icf:b` | WHO ICF |

### Phase 2: Update Model Definitions

```python
# trn_contact/models/contact.py

class ResPartner(models.Model):
    _inherit = "res.partner"

    # Remove Selection fields
    # gender = fields.Selection([...])  # REMOVED

    # Add vocabulary-based fields
    gender_id = fields.Many2one(
        "trn.vocabulary.code",
        string="Gender",
        domain="[('namespace_uri', '=', 'urn:iso:std:iso:5218')]",
    )

    marital_status_id = fields.Many2one(
        "trn.vocabulary.code",
        string="Marital Status",
        domain="[('vocabulary_id.namespace_uri', '=', 'urn:un:unsd:pop-census:marital-status')]",
    )
```

### Phase 3: Update Views

```xml
<!-- Replace selection widget with Many2one -->
<field name="gender" position="replace">
    <field name="gender_id"/>
</field>
```

### Phase 4: Update Search/Filters

```xml
<!-- Old -->
<filter name="male" domain="[('gender', '=', 'male')]"/>

<!-- New -->
<filter name="male" domain="[('gender_id.code', '=', '1')]"/>
```

### Phase 5: Update Business Logic

```python
# Old
if partner.gender == 'female':
    ...

# New
if partner.gender_id.code == '2':
    ...

# Or with helper constant
GENDER_FEMALE = 'urn:iso:std:iso:5218', '2'
if partner.gender_id == self.env['trn.vocabulary.code'].get_code(*GENDER_FEMALE):
    ...
```

---

## Consequences

### Positive
- Extensible without code changes (add codes via UI/XML)
- International standard compliance (ISO, WHO, ILO)
- Interoperability via namespace URIs
- Hierarchical codes for complex classifications
- Translation support via Odoo i18n
- Mappings enable cross-vocabulary reporting

### Negative
- Slightly more complex than Selection fields
- Requires vocabulary seed data
- Domain filters on fields are verbose

### Scale Considerations (50M Records)

| Aspect | Impact | Mitigation |
|--------|--------|------------|
| Vocabulary table | Small (~5K codes) | Fully cached |
| Many2one storage | Integer FK | Same as Selection |
| Lookups | Frequent | `@ormcache` on `get_code()` |
| Joins | For display | `related` stored fields |

---

## Implementation Checklist

- [x] Create `trn_vocabulary` module
- [x] Implement `trn.vocabulary` model
- [x] Implement `trn.vocabulary.code` model with caching
- [x] Implement `trn.vocabulary.mapping` model
- [x] Create core vocabulary data (gender, relationship, marital)
- [x] Update `trn_contact` to use `gender_id`, `civil_status_id`, `blood_type_id`
- [x] Update vocabulary seed data (gender, civil status, blood type, identifier types)
- [ ] Create disability vocabulary in `trn_disability` (planned)
- [ ] Create domain-specific vocabularies in appropriate modules
- [x] Update views and search filters
- [x] Add tests for vocabulary lookups and mappings

## References

- [FHIR Terminology](https://www.hl7.org/fhir/terminologies.html)
- [ISO 5218 Gender Codes](https://www.iso.org/standard/36266.html)
- [WHO ICF Classification](https://www.who.int/standards/classifications/icf)
- [ILO ISCO-08](https://www.ilo.org/public/english/bureau/stat/isco/)
