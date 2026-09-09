# ADR-011: Data Classification System

## Status

**Implemented** - Production ready

**Date:** 2025-11-28
**Accepted Date:** 2025-12-04
**Implementation Date:** 2025-12-04

> **Post-refactor:** Code examples updated to current model names. `trn.identifier` (was `trn.registry.id`).
> The identifier model is defined in the domain module that implements identifiers.

### Implementation Summary

The `trn_data_classification` module (v19.0.1.0.0) implements this ADR with **2,523 lines of model code**.

| Component | Status | Notes |
|-----------|--------|-------|
| Classification Levels | ✅ Complete | 4 default levels (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED) |
| Field Classification Registry | ✅ Complete | All 10 PII categories, 22 ACL rules |
| Auto-Detection Patterns | ✅ Complete | 15 built-in patterns, runs at model load |
| Policy Enforcement (Masking) | ✅ Complete | Pattern-based masking via `trn.pii.aware` mixin |
| Policy Enforcement (Access Control) | ✅ Complete | Group-based via `min_group_id` field |
| Policy Enforcement (Audit) | ✅ Complete | Dedicated `trn.pii.access.log` model |
| DSAR Management | ✅ Complete | All request types and workflows |
| Data Retention | ✅ Complete | Exceeds proposal with scheduler and policies |
| Consent Integration | ✅ Delegated | Uses external `trn_consent` module |
| UI Wizards | ⏭️ Skipped | Auto-classification at model load instead |

### Implementation Differences from Proposal

1. **Model Naming**: DSAR model is `trn.dsar.request` (not `trn.data.subject.request` as proposed)
2. **Policy Enforcer**: Uses `trn.pii.aware` mixin pattern instead of abstract service model
3. **Auto-Detection**: Runs programmatically at model load, not via wizard UI
4. **Consent Models**: Delegated to `trn_consent` module (correct separation of concerns)
5. **Bonus Features**: Data retention scheduler and PII access logging exceed original proposal

## Context

The system manages sensitive personal information including:

- **Direct identifiers**: National IDs, passports, tax IDs, birth certificates
- **Contact information**: Phone numbers, addresses, email
- **Financial data**: Bank account numbers, payment amounts
- **Quasi-identifiers**: Date of birth, gender, location (combinable for re-identification)
- **Sensitive categories**: Health status, disability, family relationships

### Current State

Analysis of the codebase reveals:

| Model | PII Fields | Current Protection |
|-------|------------|-------------------|
| `trn.identifier` | National ID, passport, tax ID | None (plaintext) |
| `trn.payment` | Bank account number | None (plaintext) |
| `trn.phone.number` | Phone numbers | None (plaintext) |
| `res.partner` | Names, addresses, DOB, email | None (plaintext) |
| `trn.registry.relationship` | Family/personal ties | None (plaintext) |

### Problems

1. **No visibility**: No systematic inventory of PII across the system
2. **No classification**: Fields aren't marked by sensitivity level
3. **Inconsistent handling**: Each module handles sensitive data differently
4. **Compliance gaps**: GDPR, local regulations require knowing what data exists
5. **No foundation**: Can't implement encryption, masking, or retention policies without classification

### Drivers

- **Regulatory compliance**: GDPR Article 30 (Records of Processing), data protection laws
- **Donor requirements**: Many funders require data protection frameworks
- **Security foundation**: Classification must precede encryption and access controls
- **Operational need**: Staff need to know what data requires special handling

## Decision

We will implement a **Data Classification System** as a foundational module (`trn_data_classification`) that provides:

1. Classification levels with configurable policies
2. Field-level classification registry
3. Auto-detection of likely PII fields
4. Policy enforcement hooks
5. Compliance reporting
6. Data subject rights support (GDPR)
7. Consent management

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Data Classification Architecture                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                 │
│  │  Classification │  │    Field       │  │   Compliance   │                 │
│  │     Levels     │  │   Registry     │  │   Reporting    │                 │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘                 │
│          │                   │                   │                           │
│          ▼                   ▼                   ▼                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    trn_data_classification                           │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │    │
│  │  │   Policy    │  │  Auto-      │  │   Consent   │  │   DSAR     │ │    │
│  │  │  Enforcer   │  │  Detection  │  │  Management │  │  Handler   │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│         ┌────────────────────┼────────────────────┐                         │
│         ▼                    ▼                    ▼                         │
│  ┌──────────────────┐ ┌─────────────┐      ┌─────────────┐                 │
│  │trn_pii_encryption│ │  trn_audit  │      │trn_security │                 │
│  │ (planned)        │ │ (planned)   │      │ (consumer)  │                 │
│  └──────────────────┘ └─────────────┘      └─────────────┘                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Classification Levels (`trn.data.classification.level`)

Predefined sensitivity levels with associated policies:

```python
class DataClassificationLevel(models.Model):
    _name = "trn.data.classification.level"
    _description = "Data sensitivity classification level"
    _order = "sequence"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)  # PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED
    sequence = fields.Integer()  # Higher = more sensitive
    color = fields.Integer()
    description = fields.Text(translate=True)

    # Policy flags
    requires_encryption = fields.Boolean(
        help="Fields at this level must be encrypted at rest"
    )
    requires_masking = fields.Boolean(
        help="Fields displayed with masking by default"
    )
    requires_audit = fields.Boolean(
        help="All access to fields at this level is logged"
    )
    requires_consent = fields.Boolean(
        help="Explicit consent required before collection"
    )
    requires_purpose_limitation = fields.Boolean(
        help="Data can only be used for stated purposes"
    )

    # Retention
    retention_days = fields.Integer(
        help="Auto-archive/delete after N days. 0 = indefinite"
    )
    retention_action = fields.Selection([
        ('none', 'No Action'),
        ('anonymize', 'Anonymize'),
        ('archive', 'Archive'),
        ('delete', 'Delete'),
    ], default='none')

    # Access control
    min_group_id = fields.Many2one(
        'res.groups',
        help="Minimum security group required to view unmasked data"
    )
```

**Default Levels:**

| Level | Code | Encryption | Masking | Audit | Example Fields |
|-------|------|------------|---------|-------|----------------|
| Public | `PUBLIC` | No | No | No | Program names, public stats |
| Internal | `INTERNAL` | No | No | Yes | Gender, registration status |
| Confidential | `CONFIDENTIAL` | Recommended | Yes | Yes | Names, DOB, addresses |
| Restricted | `RESTRICTED` | Required | Yes | Yes | National IDs, bank accounts |

#### 2. Field Classification Registry (`trn.field.classification`)

Maps model fields to classification levels:

```python
class FieldClassification(models.Model):
    _name = "trn.field.classification"
    _description = "PII classification for model fields"
    _rec_name = "display_name"

    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    field_id = fields.Many2one(
        'ir.model.fields',
        required=True,
        ondelete='cascade',
        domain="[('model_id', '=', model_id)]"
    )
    classification_id = fields.Many2one(
        'trn.data.classification.level',
        required=True
    )

    # PII categorization
    pii_category = fields.Selection([
        ('direct_id', 'Direct Identifier'),
        ('quasi_id', 'Quasi-Identifier'),
        ('sensitive', 'Sensitive Personal Data'),
        ('financial', 'Financial Information'),
        ('contact', 'Contact Information'),
        ('biometric', 'Biometric Data'),
        ('health', 'Health Information'),
        ('political', 'Political/Religious/Union'),
        ('genetic', 'Genetic Data'),
        ('location', 'Location Data'),
    ])

    # Compliance flags
    gdpr_special_category = fields.Boolean(
        help="GDPR Article 9 special category data"
    )
    cross_border_restricted = fields.Boolean(
        help="Cannot be transferred outside jurisdiction"
    )
    child_data = fields.Boolean(
        help="May contain data about minors"
    )

    # Handling configuration
    mask_pattern = fields.Char(
        help="Display mask pattern, e.g., '****-****-####'"
    )
    search_strategy = fields.Selection([
        ('none', 'No Search Allowed'),
        ('blind_index', 'Blind Index (Exact Match)'),
        ('partial_index', 'Partial Index (Last N chars)'),
        ('phonetic', 'Phonetic Search (Names)'),
        ('range', 'Range Search (Dates)'),
        ('full', 'Full Search (Decrypted)'),
    ], default='blind_index')

    # Processing purposes
    purpose_ids = fields.Many2many(
        'trn.data.purpose',
        help="Legitimate purposes for processing this data"
    )

    # Metadata
    legal_basis = fields.Selection([
        ('consent', 'Consent'),
        ('contract', 'Contractual Necessity'),
        ('legal', 'Legal Obligation'),
        ('vital', 'Vital Interests'),
        ('public', 'Public Interest'),
        ('legitimate', 'Legitimate Interest'),
    ])
    data_source = fields.Char(help="Where this data originates")
    notes = fields.Text()

    _sql_constraints = [
        ('unique_field', 'UNIQUE(model_id, field_id)',
         'Each field can only have one classification')
    ]
```

#### 3. Auto-Detection Engine

Wizard to scan models and suggest classifications:

```python
class FieldClassificationDetector(models.TransientModel):
    _name = "trn.field.classification.detector"
    _description = "Auto-detect PII fields"

    # Detection patterns (configurable via XML data)
    PII_PATTERNS = {
        # Pattern: (pii_category, suggested_level_code)
        r'(national|passport|ssn|tax|identity).*id': ('direct_id', 'RESTRICTED'),
        r'(birth|dob|date.*birth)': ('quasi_id', 'CONFIDENTIAL'),
        r'(phone|mobile|tel|fax)': ('contact', 'CONFIDENTIAL'),
        r'email': ('contact', 'INTERNAL'),
        r'(address|street|city|postal|zip)': ('contact', 'CONFIDENTIAL'),
        r'(account|iban|bank|routing)': ('financial', 'RESTRICTED'),
        r'(family.*name|given.*name|first.*name|last.*name|surname)': ('direct_id', 'CONFIDENTIAL'),
        r'^name$': ('direct_id', 'CONFIDENTIAL'),
        r'(gender|sex)': ('quasi_id', 'INTERNAL'),
        r'(salary|income|wage|payment)': ('financial', 'CONFIDENTIAL'),
        r'(disability|health|medical|diagnosis)': ('health', 'RESTRICTED'),
        r'(religion|ethnic|race|political)': ('sensitive', 'RESTRICTED'),
        r'(fingerprint|biometric|face.*id|iris)': ('biometric', 'RESTRICTED'),
        r'(gps|latitude|longitude|geo.*location)': ('location', 'CONFIDENTIAL'),
    }

    model_ids = fields.Many2many('ir.model')
    include_existing = fields.Boolean(
        default=False,
        help="Include fields that already have classifications"
    )
    suggestion_ids = fields.One2many(
        'trn.field.classification.suggestion',
        'wizard_id'
    )

    def action_detect(self):
        """Scan selected models for PII patterns"""
        ...

    def action_apply_suggestions(self):
        """Create classifications from accepted suggestions"""
        ...
```

#### 4. Policy Enforcer

Abstract model providing enforcement hooks:

```python
class ClassificationPolicyEnforcer(models.AbstractModel):
    _name = "trn.classification.policy.enforcer"
    _description = "Enforce data classification policies"

    @api.model
    def get_field_classification(self, model_name, field_name):
        """Get classification for a specific field"""
        return self.env['trn.field.classification'].search([
            ('model_id.model', '=', model_name),
            ('field_id.name', '=', field_name),
        ], limit=1)

    @api.model
    def check_access(self, model_name, field_name, user=None):
        """Check if user can access unmasked field value"""
        user = user or self.env.user
        classification = self.get_field_classification(model_name, field_name)
        if not classification:
            return True  # Unclassified = unrestricted

        min_group = classification.classification_id.min_group_id
        if min_group and not user.has_group(min_group.get_external_id()[min_group.id]):
            return False
        return True

    @api.model
    def apply_masking(self, model_name, field_name, value, user=None):
        """Apply masking if user doesn't have full access"""
        if not value:
            return value

        classification = self.get_field_classification(model_name, field_name)
        if not classification or not classification.classification_id.requires_masking:
            return value

        if self.check_access(model_name, field_name, user):
            return value

        return self._mask_value(value, classification.mask_pattern)

    def _mask_value(self, value, pattern):
        """Apply mask pattern to value"""
        if not pattern:
            # Default: show last 4 characters
            return '*' * max(0, len(str(value)) - 4) + str(value)[-4:]
        # Pattern like "****-****-####" where # = show, * = hide
        ...
```

#### 5. Data Subject Request Handler (GDPR)

```python
class DataSubjectRequest(models.Model):
    _name = "trn.data.subject.request"
    _description = "Data Subject Access Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    partner_id = fields.Many2one('res.partner', required=True, tracking=True)
    request_type = fields.Selection([
        ('access', 'Right of Access (Art. 15)'),
        ('rectification', 'Right to Rectification (Art. 16)'),
        ('erasure', 'Right to Erasure (Art. 17)'),
        ('restriction', 'Right to Restriction (Art. 18)'),
        ('portability', 'Right to Data Portability (Art. 20)'),
        ('objection', 'Right to Object (Art. 21)'),
    ], required=True, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('verified', 'Identity Verified'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    # Verification
    identity_verified = fields.Boolean()
    verified_by_id = fields.Many2one('res.users')
    verified_date = fields.Datetime()
    verification_method = fields.Char()

    # Processing
    assigned_to_id = fields.Many2one('res.users')
    due_date = fields.Date()  # GDPR: 30 days
    completed_date = fields.Datetime()

    # Results
    export_file = fields.Binary(attachment=True)
    export_filename = fields.Char()
    rejection_reason = fields.Text()

    # Audit
    affected_model_ids = fields.Many2many('ir.model', readonly=True)
    records_processed = fields.Integer(readonly=True)

    def action_generate_export(self):
        """Generate complete data export for access/portability requests"""
        self.ensure_one()
        classifications = self.env['trn.field.classification'].search([])

        export_data = {}
        for classification in classifications:
            model = self.env[classification.model_id.model]
            # Find records related to this partner
            records = self._find_partner_records(model, self.partner_id)
            if records:
                export_data[classification.model_id.model] = self._export_records(
                    records, classification
                )

        # Generate JSON/CSV export
        ...

    def action_execute_erasure(self):
        """Execute right to erasure (with appropriate safeguards)"""
        ...
```

#### 6. Consent Management

```python
class DataProcessingPurpose(models.Model):
    _name = "trn.data.purpose"
    _description = "Data processing purpose"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    description = fields.Text(translate=True)
    legal_basis = fields.Selection([
        ('consent', 'Consent'),
        ('contract', 'Contractual Necessity'),
        ('legal', 'Legal Obligation'),
        ('vital', 'Vital Interests'),
        ('public', 'Public Interest'),
        ('legitimate', 'Legitimate Interest'),
    ], required=True)
    is_mandatory = fields.Boolean(
        help="Required for service provision (cannot be withdrawn)"
    )


class DataConsent(models.Model):
    _name = "trn.data.consent"
    _description = "Data processing consent record"
    _inherit = ["mail.thread"]

    partner_id = fields.Many2one('res.partner', required=True, index=True)
    purpose_id = fields.Many2one('trn.data.purpose', required=True)

    # Consent state
    granted = fields.Boolean(tracking=True)
    granted_date = fields.Datetime()
    granted_method = fields.Selection([
        ('written', 'Written Form'),
        ('digital', 'Digital Signature'),
        ('verbal', 'Verbal (Witnessed)'),
        ('implied', 'Implied'),
    ])

    # Withdrawal
    withdrawn = fields.Boolean(tracking=True)
    withdrawn_date = fields.Datetime()
    withdrawn_reason = fields.Text()

    # Evidence
    consent_form_id = fields.Many2one('ir.attachment')
    witness_id = fields.Many2one('res.users')
    ip_address = fields.Char()  # For digital consent

    # Validity
    valid_from = fields.Date()
    valid_until = fields.Date()

    @api.model
    def check_consent(self, partner_id, purpose_code):
        """Check if partner has valid consent for purpose"""
        purpose = self.env['trn.data.purpose'].search([
            ('code', '=', purpose_code)
        ], limit=1)

        if not purpose:
            return False

        if purpose.legal_basis != 'consent':
            return True  # Other legal bases don't require explicit consent

        consent = self.search([
            ('partner_id', '=', partner_id),
            ('purpose_id', '=', purpose.id),
            ('granted', '=', True),
            ('withdrawn', '=', False),
            '|', ('valid_until', '=', False), ('valid_until', '>=', fields.Date.today()),
        ], limit=1)

        return bool(consent)
```

### Module Structure

```
trn_data_classification/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── classification_level.py
│   ├── field_classification.py
│   ├── policy_enforcer.py
│   ├── data_purpose.py
│   ├── data_consent.py
│   └── data_subject_request.py
├── wizards/
│   ├── __init__.py
│   ├── auto_detect_wizard.py
│   ├── bulk_classify_wizard.py
│   └── data_export_wizard.py
├── views/
│   ├── classification_level_views.xml
│   ├── field_classification_views.xml
│   ├── consent_views.xml
│   ├── dsar_views.xml
│   ├── dashboard_views.xml
│   └── menus.xml
├── security/
│   ├── ir.model.access.csv
│   ├── security_groups.xml
│   └── record_rules.xml
├── data/
│   ├── classification_levels.xml
│   ├── detection_patterns.xml
│   ├── processing_purposes.xml
│   └── demo_classifications.xml
├── reports/
│   ├── pii_inventory_report.xml
│   ├── consent_report.xml
│   └── dsar_report.xml
└── static/
    └── description/
        └── icon.png
```

### Integration Points

| Module | Integration |
|--------|-------------|
| `trn_pii_encryption` (planned) | Uses classifications to determine what to encrypt |
| `trn_audit` (planned) | Uses classifications to determine what to audit |
| `trn_security` | Uses classifications for field-level access control |
| `trn_contact` | Pre-classifies contact fields |
| `trn_order` (planned) | Pre-classifies order fields |

### Simplified Integration: "Secure by Default"

The goal is **zero-config security** for common cases, with escape hatches for complex scenarios.

#### Principle: Convention Over Configuration

Most developers should never need to write XML or think about classification. The system should:
1. **Auto-detect** PII fields by name patterns
2. **Auto-apply** sensible defaults
3. **Warn** about unclassified likely-PII fields
4. **Allow override** when needed

#### Approach 1: Field Attribute (Simplest)

Developers add a single attribute to field definitions:

```python
class Individual(models.Model):
    _name = "res.partner"

    # Option A: Simple boolean
    national_id = fields.Char(pii=True)

    # Option B: Classification level
    family_name = fields.Char(classification='confidential')
    bank_account = fields.Char(classification='restricted')

    # Option C: Full control when needed
    health_status = fields.Char(
        classification='restricted',
        pii_category='health',
        mask_pattern='[REDACTED]',
        search_strategy='none',
    )
```

**Implementation**: Extend Odoo's field system:

```python
# trn_data_classification/models/fields.py
from odoo import fields as odoo_fields

# Patch Field class to accept classification attributes
_original_field_init = odoo_fields.Field.__init__

def _patched_field_init(self, *args, **kwargs):
    self.pii = kwargs.pop('pii', False)
    self.classification = kwargs.pop('classification', None)
    self.pii_category = kwargs.pop('pii_category', None)
    self.mask_pattern = kwargs.pop('mask_pattern', None)
    self.search_strategy = kwargs.pop('search_strategy', None)
    _original_field_init(self, *args, **kwargs)

odoo_fields.Field.__init__ = _patched_field_init
```

**Auto-registration at model load**:

```python
class BaseModel(models.AbstractModel):
    _inherit = "base"

    @api.model
    def _setup_complete(self):
        super()._setup_complete()
        # Auto-register classified fields
        self.env['trn.field.classification']._register_model_fields(self._name)
```

#### Approach 2: Auto-Detection with Smart Defaults

Fields are **automatically classified** based on naming patterns:

```python
# No code needed! These fields are auto-classified at install:

class Individual(models.Model):
    _name = "res.partner"

    national_id = fields.Char()      # Auto: RESTRICTED (pattern: *_id with national/passport/tax)
    family_name = fields.Char()      # Auto: CONFIDENTIAL (pattern: *_name)
    phone = fields.Char()            # Auto: CONFIDENTIAL (pattern: phone/mobile/tel)
    email = fields.Char()            # Auto: INTERNAL (pattern: email)
    birthdate = fields.Date()        # Auto: CONFIDENTIAL (pattern: birth*)
    address = fields.Text()          # Auto: CONFIDENTIAL (pattern: address/street)
    gender = fields.Selection()      # Auto: INTERNAL (pattern: gender/sex)
```

**Configuration via system parameter** (not code):

```xml
<!-- trn_data_classification/data/detection_patterns.xml -->
<record id="pattern_national_id" model="trn.classification.pattern">
    <field name="pattern">(national|passport|ssn|tax|identity).*id</field>
    <field name="classification_id" ref="level_restricted"/>
    <field name="pii_category">direct_id</field>
    <field name="priority">100</field>
</record>
```

#### Approach 3: Mixin with Zero Config

Models just inherit a mixin - everything else is automatic:

```python
class Individual(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "trn.pii.aware"]  # Just add this!

    # All fields are now:
    # - Auto-scanned for PII patterns
    # - Auto-masked based on classification
    # - Auto-audited if required
    # - Auto-encrypted if required (with trn_pii_encryption)
```

**What the mixin does**:

```python
class PIIAwareMixin(models.AbstractModel):
    _name = "trn.pii.aware"
    _description = "PII-aware model mixin"

    @api.model
    def _setup_complete(self):
        super()._setup_complete()
        # Scan this model's fields and auto-classify
        self._auto_classify_fields()

    def _auto_classify_fields(self):
        """Scan fields and apply classification based on patterns"""
        Classification = self.env['trn.field.classification'].sudo()
        patterns = self.env['trn.classification.pattern'].search([])

        for field_name, field in self._fields.items():
            # Skip if already explicitly classified
            if getattr(field, 'classification', None):
                continue

            # Check field name against patterns
            for pattern in patterns:
                if pattern.matches(field_name):
                    Classification._ensure_classification(
                        self._name, field_name, pattern
                    )
                    break

    def read(self, fields=None, load='_classic_read'):
        """Override read to apply automatic masking"""
        result = super().read(fields, load)
        return self._apply_pii_masking(result, fields)

    def _apply_pii_masking(self, records_data, fields):
        """Apply masking based on classification and user access"""
        enforcer = self.env['trn.classification.policy.enforcer']
        # ... masking logic
        return records_data
```

#### Approach 4: Module-Level Declaration (One Line)

Modules declare classification scope in manifest:

```python
# trn_contact/__manifest__.py
{
    'name': 'Contact Module',
    'depends': ['trn_data_classification'],
    'pii_aware': True,  # Enable auto-classification for all models in this module
}
```

Or with more control:

```python
{
    'pii_aware': {
        'models': ['res.partner', 'trn.identifier', 'trn.phone.number'],
        'auto_detect': True,
        'default_level': 'confidential',
    }
}
```

#### Summary: Integration Complexity Levels

| Level | Developer Effort | Security | Use Case |
|-------|------------------|----------|----------|
| **Zero** | Add `'pii_aware': True` to manifest | Auto-detect | Most modules |
| **Minimal** | Add `pii=True` to sensitive fields | Explicit | When auto-detect misses |
| **Standard** | Add `classification='restricted'` | Explicit + level | Fine-grained control |
| **Full** | XML data files | Complete control | Compliance requirements |

**Recommended default**: Level Zero (manifest flag) + warnings for unclassified likely-PII fields.

### Developer Experience: What They See

#### At Module Install

```
[INFO] trn_contact: Auto-classified 12 PII fields
[INFO]   - res.partner.family_name → CONFIDENTIAL (direct_id)
[INFO]   - res.partner.birthdate → CONFIDENTIAL (quasi_id)
[INFO]   - trn.identifier.value → RESTRICTED (direct_id)
[WARNING] trn_contact: 2 fields may contain PII but are not classified:
[WARNING]   - res.partner.custom_field_1 (matches pattern: *_id)
[WARNING]   - trn.order.custom_notes (contains 'address' in help text)
[WARNING] Run 'Settings > Data Classification > Review Suggestions' to classify
```

#### In Development (Linter/Pre-commit)

```bash
$ pre-commit run tpl-pii-check

trn_contact/models/contact.py:45
  WARNING: Field 'emergency_contact' may contain PII (matches: contact)
  Add classification or mark as safe:
    emergency_contact = fields.Char(pii=True)  # or
    emergency_contact = fields.Char(pii=False)  # explicitly not PII
```

#### At Runtime (Admin Dashboard)

```
┌─────────────────────────────────────────────────────────────┐
│ Data Classification Status                                   │
├─────────────────────────────────────────────────────────────┤
│ ✓ 156 fields classified                                     │
│ ⚠ 3 fields need review                                      │
│ ✗ 0 unprotected RESTRICTED fields                           │
├─────────────────────────────────────────────────────────────┤
│ Coverage: 98.1%  │  Encryption: 100%  │  Audit: 100%        │
└─────────────────────────────────────────────────────────────┘
```

### Module Integration Patterns (Advanced)

For modules needing more control, these patterns are available:

#### Pattern 1: Declare Field Classifications via XML Data

Modules declare their PII fields in XML data files loaded at install:

```xml
<!-- trn_contact/data/field_classifications.xml -->
<odoo>
    <record id="classification_national_id_value" model="trn.field.classification">
        <field name="model_id" ref="model_trn_identifier"/>
        <field name="field_id" ref="field_trn_identifier__value"/>
        <field name="classification_id" ref="trn_data_classification.level_restricted"/>
        <field name="pii_category">direct_id</field>
        <field name="mask_pattern">****-****-####</field>
        <field name="search_strategy">blind_index</field>
        <field name="legal_basis">legal</field>
    </record>

    <record id="classification_partner_birthdate" model="trn.field.classification">
        <field name="model_id" ref="base.model_res_partner"/>
        <field name="field_id" ref="trn_contact.field_res_partner__birthdate"/>
        <field name="classification_id" ref="trn_data_classification.level_confidential"/>
        <field name="pii_category">quasi_id</field>
        <field name="search_strategy">range</field>
    </record>
</odoo>
```

#### Pattern 2: Query Classifications at Runtime

Modules query classifications to drive behavior:

```python
class MyModel(models.Model):
    _name = "my.model"

    def get_classified_fields(self):
        """Get all classified fields for this model"""
        return self.env['trn.field.classification'].search([
            ('model_id.model', '=', self._name),
        ])

    def get_fields_requiring_encryption(self):
        """Get fields that must be encrypted"""
        return self.env['trn.field.classification'].search([
            ('model_id.model', '=', self._name),
            ('classification_id.requires_encryption', '=', True),
        ])

    def get_restricted_fields(self):
        """Get RESTRICTED level fields"""
        restricted = self.env.ref('trn_data_classification.level_restricted')
        return self.env['trn.field.classification'].search([
            ('model_id.model', '=', self._name),
            ('classification_id', '=', restricted.id),
        ])
```

#### Pattern 3: Use Policy Enforcer Mixin

Modules inherit the policy enforcer for automatic enforcement:

```python
class EhIdentifier(models.Model):
    _name = "trn.identifier"
    _inherit = ["trn.identifier", "trn.classification.policy.mixin"]

    # Mixin automatically:
    # - Masks fields based on classification when reading
    # - Logs access to classified fields
    # - Checks consent before displaying sensitive data
```

#### Pattern 4: Hook into Classification Events

Modules can extend classification behavior:

```python
class FieldClassification(models.Model):
    _inherit = "trn.field.classification"

    @api.model_create_multi
    def create(self, vals_list):
        """Hook: When a field is classified"""
        records = super().create(vals_list)
        for record in records:
            if record.classification_id.requires_encryption:
                # Trigger encryption setup for this field
                self.env['trn.encryption.manager'].setup_field_encryption(
                    record.model_id.model,
                    record.field_id.name,
                )
        return records
```

#### Pattern 5: Export Classification Metadata

Modules can export classification data for external systems:

```python
class ClassificationExporter(models.AbstractModel):
    _name = "trn.classification.exporter"

    def export_to_data_catalog(self):
        """Export classifications to external data catalog"""
        classifications = self.env['trn.field.classification'].search([])
        return [{
            'model': c.model_id.model,
            'field': c.field_id.name,
            'classification': c.classification_id.code,
            'pii_category': c.pii_category,
            'gdpr_special': c.gdpr_special_category,
        } for c in classifications]
```

#### Pattern 6: Conditional UI Based on Classification

Views can conditionally show/hide based on classification:

```xml
<!-- Use widget that respects classification -->
<field name="national_id" widget="classified_field"/>

<!-- Or check classification in attrs -->
<field name="national_id"
       attrs="{'invisible': [('has_pii_access', '=', False)]}"
       options="{'classification_aware': true}"/>
```

#### Pattern 7: API Response Filtering

API controllers filter responses based on classification:

```python
class ContactAPI(http.Controller):

    @http.route('/api/v2/patients/<int:id>', type='json', auth='api_key')
    def get_patient(self, id):
        patient = request.env['res.partner'].browse(id)

        # Get API user's clearance level
        clearance = self._get_api_clearance(request.env.user)

        # Filter response based on classification
        enforcer = request.env['trn.classification.policy.enforcer']
        return enforcer.filter_record_for_api(
            patient,
            clearance_level=clearance,
            mask_restricted=True,
        )
```

#### Pattern 8: Batch Processing with Classification Awareness

Background jobs respect classification policies:

```python
class DataExportJob(models.Model):
    _name = "trn.data.export.job"

    def _export_with_classification(self, records, user):
        """Export records respecting classification"""
        enforcer = self.env['trn.classification.policy.enforcer']

        exported = []
        for record in records:
            record_data = {}
            for field in record._fields:
                classification = enforcer.get_field_classification(
                    record._name, field
                )
                if classification:
                    # Apply masking or skip based on user clearance
                    if enforcer.check_access(record._name, field, user):
                        record_data[field] = record[field]
                    elif classification.classification_id.requires_masking:
                        record_data[field] = enforcer.apply_masking(
                            record._name, field, record[field], user
                        )
                    # else: skip field entirely
                else:
                    record_data[field] = record[field]
            exported.append(record_data)
        return exported
```

#### Pattern 9: Audit Log Integration (planned)

`trn_audit` (planned) uses classification to determine what to audit:

```python
class AuditRule(models.Model):
    _inherit = "trn.audit.rule"

    use_classification = fields.Boolean(
        default=True,
        help="Automatically audit fields based on their classification"
    )

    def _get_fields_to_audit(self):
        """Get fields requiring audit based on classification"""
        if not self.use_classification:
            return super()._get_fields_to_audit()

        # Get all fields where classification requires audit
        classifications = self.env['trn.field.classification'].search([
            ('model_id', '=', self.model_id.id),
            ('classification_id.requires_audit', '=', True),
        ])
        return classifications.mapped('field_id')
```

#### Pattern 10: Consent Check Before Data Access

Modules check consent before accessing certain data:

```python
class Contact(models.Model):
    _inherit = "res.partner"

    def get_contact_info(self):
        """Get contact info with consent check"""
        self.ensure_one()

        # Check consent for contact purpose
        if not self.env['trn.data.consent'].check_consent(
            self.id, 'contact_communication'
        ):
            raise UserError(_(
                "Contact has not consented to contact for this purpose."
            ))

        return {
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
        }
```

### Example: trn_contact Integration

```python
# trn_contact/__manifest__.py
{
    'name': 'Contact Module',
    'depends': ['trn_data_classification'],  # Add dependency
    'data': [
        'data/field_classifications.xml',  # Declare PII fields
    ],
}

# trn_contact/models/contact.py
class Contact(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "trn.classification.policy.mixin"]

    # Fields are automatically:
    # - Masked based on classification
    # - Audited if classification requires
    # - Encrypted if classification requires (via trn_pii_encryption)
```

```xml
<!-- trn_contact/data/field_classifications.xml -->
<odoo noupdate="1">
    <!-- Phone Number -->
    <record id="classify_phone_number" model="trn.field.classification">
        <field name="model_id" ref="trn_contact.model_trn_phone_number"/>
        <field name="field_id" ref="trn_contact.field_trn_phone_number__phone_no"/>
        <field name="classification_id" ref="trn_data_classification.level_confidential"/>
        <field name="pii_category">contact</field>
        <field name="mask_pattern">***-***-####</field>
        <field name="search_strategy">partial_index</field>
    </record>

    <!-- Registry ID Value -->
    <record id="classify_registry_id_value" model="trn.field.classification">
        <field name="model_id" ref="model_trn_identifier"/>
        <field name="field_id" ref="field_trn_identifier__value"/>
        <field name="classification_id" ref="trn_data_classification.level_restricted"/>
        <field name="pii_category">direct_id</field>
        <field name="mask_pattern">****-****-####</field>
        <field name="search_strategy">blind_index</field>
        <field name="gdpr_special_category" eval="False"/>
        <field name="legal_basis">legal</field>
        <field name="data_source">Government ID Document</field>
    </record>

    <!-- Individual Name -->
    <record id="classify_individual_family_name" model="trn.field.classification">
        <field name="model_id" ref="base.model_res_partner"/>
        <field name="field_id" ref="trn_contact.field_res_partner__family_name"/>
        <field name="classification_id" ref="trn_data_classification.level_confidential"/>
        <field name="pii_category">direct_id</field>
        <field name="search_strategy">phonetic</field>
    </record>
</odoo>
```

### UI Features

1. **Classification Dashboard**
   - Visual overview of PII across system
   - Gap analysis (unclassified likely-PII fields)
   - Compliance status indicators

2. **Model Browser**
   - Navigate models and fields
   - See classification status per field
   - Quick-classify from context

3. **Bulk Classification Wizard**
   - Select multiple fields
   - Apply same classification
   - Useful for initial setup

4. **DSAR Management**
   - Track data subject requests
   - Generate exports
   - Audit trail of actions

## Consequences

### Positive

1. **Visibility**: Complete inventory of PII across the system
2. **Foundation**: Enables encryption, masking, retention policies
3. **Compliance**: Supports GDPR, local regulations, donor requirements
4. **Consistency**: Single source of truth for data sensitivity
5. **Automation**: Auto-detection reduces manual effort
6. **Flexibility**: Configurable levels and policies per deployment

### Negative

1. **Initial effort**: All existing fields need classification
2. **Maintenance**: New fields must be classified
3. **Performance**: Policy checks add overhead (cacheable)
4. **Complexity**: Another system to learn and manage

### Neutral

1. **Dependency**: Other modules depend on this for security features
2. **Data migration**: Existing deployments need classification data

## Alternatives Considered

### Alternative 1: Field Attributes Only
Add `is_pii=True` attribute to field definitions without full classification system.

**Rejected**: Too simplistic. Doesn't support multiple levels, policies, or compliance reporting.

### Alternative 2: External Data Catalog
Use external tools like Apache Atlas or Collibra.

**Rejected**: Over-engineered for this use case. Adds operational complexity.

### Alternative 3: Classify at Database Level
Use PostgreSQL comments/labels for classification.

**Rejected**: Not accessible to application layer. Can't drive UI behavior or policies.

## Implementation Plan

| Phase | Deliverable | Effort |
|-------|-------------|--------|
| 1 | Core models (levels, field classification) | 1 week |
| 2 | Auto-detection wizard | 3-4 days |
| 3 | Policy enforcer + masking widget | 1 week |
| 4 | DSAR handler | 1 week |
| 5 | Consent management | 1 week |
| 6 | Reports and dashboard | 3-4 days |
| 7 | Pre-classify core models | 2-3 days |

## References

- [GDPR Articles 13-22](https://gdpr-info.eu/) - Data subject rights
- [GDPR Article 30](https://gdpr-info.eu/art-30-gdpr/) - Records of processing activities
- [GDPR Article 9](https://gdpr-info.eu/art-9-gdpr/) - Special categories of data
- [NIST SP 800-122](https://csrc.nist.gov/publications/detail/sp/800-122/final) - Guide to Protecting PII
- [ISO 27701](https://www.iso.org/standard/71670.html) - Privacy Information Management

## Related ADRs

- ADR-004: Access Rights Management (field-level access control)
- ADR-012: PII Encryption Strategy (uses classifications)
