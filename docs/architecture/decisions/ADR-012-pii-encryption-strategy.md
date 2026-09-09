# ADR-012: PII Encryption Strategy

## Status

**IMPLEMENTED** - Phase 1 complete (~75-80%)

**Date:** 2025-11-28
**Accepted Date:** 2025-12-04

> **Post-refactor:** Code examples updated to current model names. `trn.identifier` (was `trn.registry.id`).
> Identifier encryption is in `trn_pii_encryption`. The identifier model is defined in the domain module that implements identifiers.

### Implementation Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Encrypted Field Mixin | ✅ Complete | AES-256-GCM with random nonce |
| Blind Indexes | ✅ Complete | HMAC-SHA256, exact/partial/phonetic |
| Key Management | ✅ Complete | 6 providers (config, DB, Vault, AWS, GCP, Azure) |
| Data Classification | ✅ Complete | 9 PII categories, 4 classification levels |
| Identifier Encryption | ✅ Complete | `trn_pii_encryption` module |
| Phone Number Encryption | ✅ Complete | With normalization |
| Email/Address | ✅ Complete | Selective encryption |
| Payment Data Encryption | ❌ Not started | Phase 2 |
| Masked Field Widget | ✅ Complete | JS widget exists |
| Widget Deployment in Views | ⚠️ Pending | Widget not yet in form views |

**Modules:** `trn_pii_encryption` (planned), `trn_key_management` (planned), `trn_data_classification` (planned)

**Note:** Core infrastructure is production-ready. Phase 2 needed for payment encryption and UI widget deployment.

## Context

The system stores sensitive PII. Current state analysis reveals:

| Field Type | Example Location | Current State | Risk |
|------------|------------------|---------------|------|
| National IDs | `trn.identifier.value` | Plaintext | Critical |
| Bank Accounts | `trn.payment.account_number` (planned) | Plaintext | Critical |
| Phone Numbers | `trn.phone.number.phone_no` | Plaintext | High |
| Names | `res.partner.name` | Plaintext | High |
| Addresses | `res.partner.address` | Plaintext | Medium |
| DOB | Individual model | Plaintext | Medium |

### Existing Infrastructure

The `trn_encryption` module provides:
- RSA-OAEP with A256GCM encryption
- JWK-based key storage
- JWT signing (RS256)
- JSON-LD proof signatures

However, this infrastructure is **not connected** to field-level data protection.

### Threats to Address

| Threat | Mitigation |
|--------|------------|
| Database breach | Encryption at rest |
| SQL injection | Application-level encryption |
| Backup exposure | Encrypted backups |
| Insider threat | Field-level access + encryption |
| Shoulder surfing | Display masking |
| Log exposure | Already addressed (no PII in logs) |

### Requirements

1. **Encryption at rest** for high-value PII
2. **Transparent UX** - users shouldn't notice encryption
3. **Searchable** - must be able to find records by ID
4. **Flexible key management** - from config files to HSM
5. **Compliance** - GDPR, local regulations, donor requirements
6. **Performance** - acceptable latency impact (<200ms)

### Dependency

This ADR depends on **ADR-011: Data Classification System** which identifies which fields require encryption.

## Decision

We will implement a **hybrid encryption strategy** combining:

1. **Database TDE** for data-at-rest protection
2. **Application-Level Encryption (ALE)** for high-value fields
3. **Blind indexes** for searchability
4. **Tiered key management** supporting basic to enterprise deployments

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PII Encryption Architecture                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         User Interface                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │    │
│  │  │  Masked     │  │  Reveal     │  │  Search (uses blind index)  │  │    │
│  │  │  Display    │  │  on Demand  │  │                             │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Application Layer (trn_pii_encryption)            │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │    │
│  │  │ Encrypted   │  │   Blind     │  │  Masking    │  │  Audit    │  │    │
│  │  │ Field Mixin │  │   Indexes   │  │  Widget     │  │  Logger   │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Key Management Layer                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │    │
│  │  │   Config    │  │  Database   │  │   Vault     │  │  Cloud    │  │    │
│  │  │   (Basic)   │  │ (Standard)  │  │(Enterprise) │  │  KMS      │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Database Layer                                    │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │  PostgreSQL with TDE (Transparent Data Encryption)          │    │    │
│  │  │  - Encrypts data files, WAL, backups                        │    │    │
│  │  │  - Transparent to application                               │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer 1: Database Transparent Data Encryption (TDE)

**Purpose**: Protect against physical theft, backup exposure, disk access.

**Options by Deployment**:

| Environment | TDE Solution |
|-------------|--------------|
| PostgreSQL 16+ | Native TDE |
| AWS RDS | RDS encryption (AES-256) |
| Azure Database | Azure TDE |
| Self-hosted | LUKS/dm-crypt volume encryption |

**Configuration**:
```ini
# odoo.conf
[encryption]
db_tde_enabled = true
db_tde_provider = rds  # or native, azure, volume
```

**Note**: TDE alone is insufficient - data is decrypted in memory and visible to anyone with database access.

### Layer 2: Application-Level Encryption (ALE)

**Purpose**: Protect high-value fields even from database administrators and SQL injection attacks.

#### Encrypted Field Mixin

```python
class EncryptedFieldMixin(models.AbstractModel):
    _name = "trn.encrypted.field.mixin"
    _description = "Mixin for models with encrypted fields"

    def _get_encryption_provider(self):
        """Get configured encryption provider"""
        return self.env['trn.encryption.provider'].get_active_provider()

    def _encrypt_value(self, value, field_name):
        """Encrypt a value for storage"""
        if not value:
            return value

        provider = self._get_encryption_provider()
        # Use field name as additional authenticated data (AAD)
        encrypted = provider.encrypt_data(
            value.encode('utf-8'),
            aad=f"{self._name}.{field_name}".encode()
        )
        return base64.b64encode(encrypted).decode('ascii')

    def _decrypt_value(self, encrypted_value, field_name):
        """Decrypt a stored value"""
        if not encrypted_value:
            return encrypted_value

        provider = self._get_encryption_provider()
        decrypted = provider.decrypt_data(
            base64.b64decode(encrypted_value),
            aad=f"{self._name}.{field_name}".encode()
        )
        return decrypted.decode('utf-8')

    def _compute_blind_index(self, value, field_name, index_type='exact'):
        """Compute searchable blind index"""
        if not value:
            return None

        salt = self._get_index_salt(field_name)
        normalized = self._normalize_for_index(value, index_type)

        return hmac.new(
            salt,
            normalized.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _normalize_for_index(self, value, index_type):
        """Normalize value for consistent indexing"""
        value = str(value).strip()

        if index_type == 'exact':
            # Remove formatting, uppercase
            return re.sub(r'[\s\-\.\(\)]', '', value).upper()
        elif index_type == 'phonetic':
            # Soundex or Metaphone for name matching
            return soundex(value)
        elif index_type == 'partial':
            # Last N characters only
            return value[-4:] if len(value) >= 4 else value

        return value
```

#### Encrypted Field Definition Pattern

```python
class Identifier(models.Model):
    _name = "trn.identifier"
    _inherit = ["trn.identifier", "trn.encrypted.field.mixin"]

    # Original field becomes storage for encrypted data
    value = fields.Char(string="ID Value (Encrypted)")

    # Computed field for transparent access
    value_decrypted = fields.Char(
        compute="_compute_value_decrypted",
        inverse="_inverse_value_decrypted",
        string="ID Value"
    )

    # Blind index for searching
    value_index = fields.Char(
        index=True,
        readonly=True,
        string="Search Index"
    )

    # Partial index for partial matching
    value_last4 = fields.Char(
        index=True,
        readonly=True,
        string="Last 4 Characters"
    )

    @api.depends('value')
    def _compute_value_decrypted(self):
        for record in self:
            record.value_decrypted = record._decrypt_value(
                record.value, 'value'
            )

    def _inverse_value_decrypted(self):
        for record in self:
            plaintext = record.value_decrypted
            record.value = record._encrypt_value(plaintext, 'value')
            record.value_index = record._compute_blind_index(
                plaintext, 'value', 'exact'
            )
            record.value_last4 = plaintext[-4:] if plaintext else None

    def search_by_id_value(self, search_value):
        """Search by ID value using blind index"""
        blind_index = self._compute_blind_index(search_value, 'value', 'exact')
        return self.search([('value_index', '=', blind_index)])
```

### Layer 3: Key Management

#### Provider Interface

```python
class KeyManagementProvider(models.AbstractModel):
    _name = "trn.key.provider"
    _description = "Key management provider interface"

    def get_data_key(self, key_id, version=None):
        """
        Retrieve data encryption key.
        Returns: bytes (the key material)
        """
        raise NotImplementedError

    def get_index_salt(self, purpose):
        """
        Retrieve salt for blind index computation.
        Returns: bytes
        """
        raise NotImplementedError

    def rotate_key(self, key_id):
        """
        Create new key version.
        Returns: new version identifier
        """
        raise NotImplementedError

    def list_key_versions(self, key_id):
        """
        List all versions of a key (for re-encryption).
        Returns: list of version identifiers
        """
        raise NotImplementedError

    def get_key_metadata(self, key_id):
        """
        Get key metadata (creation date, algorithm, etc.)
        Returns: dict
        """
        raise NotImplementedError
```

#### Tier 1: Config-Based Provider (Development/Small Deployments)

```python
class ConfigKeyProvider(models.AbstractModel):
    _name = "trn.key.provider.config"
    _inherit = "trn.key.provider"
    _description = "Configuration file based key provider"

    def get_data_key(self, key_id, version=None):
        """Read key from Odoo config file"""
        key_b64 = config.get(f'encryption_key_{key_id}')
        if not key_b64:
            raise UserError(_(
                "Encryption key '%s' not found in configuration. "
                "Add 'encryption_key_%s = <base64_key>' to odoo.conf"
            ) % (key_id, key_id))
        return base64.b64decode(key_b64)

    def get_index_salt(self, purpose):
        salt_b64 = config.get(f'index_salt_{purpose}')
        if not salt_b64:
            # Generate and warn
            _logger.warning(
                "Index salt for '%s' not configured. "
                "Using derived salt. Configure 'index_salt_%s' for production.",
                purpose, purpose
            )
            master = self.get_data_key('master')
            return hashlib.sha256(f"{purpose}:{master.hex()}".encode()).digest()
        return base64.b64decode(salt_b64)
```

**Configuration**:
```ini
# odoo.conf
[encryption]
key_provider = config

# Keys (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
encryption_key_master = <base64_encoded_32_byte_key>
encryption_key_pii = <base64_encoded_32_byte_key>
index_salt_default = <base64_encoded_32_byte_salt>
```

#### Tier 2: Database Provider (Standard Production)

```python
class DatabaseKeyProvider(models.AbstractModel):
    _name = "trn.key.provider.database"
    _inherit = "trn.key.provider"
    _description = "Database stored key provider with envelope encryption"

    def get_data_key(self, key_id, version=None):
        """
        Retrieve key from database.
        Keys are encrypted with master key from config.
        """
        key_record = self.env['trn.encryption.key'].sudo().search([
            ('key_id', '=', key_id),
            ('version', '=', version) if version else ('is_current', '=', True),
        ], limit=1)

        if not key_record:
            raise UserError(_("Encryption key '%s' not found") % key_id)

        # Decrypt with master key (from config)
        master_key = self._get_master_key()
        return self._decrypt_key(key_record.encrypted_key, master_key)


class EncryptionKey(models.Model):
    _name = "trn.encryption.key"
    _description = "Encrypted key storage"

    key_id = fields.Char(required=True, index=True)
    version = fields.Integer(required=True)
    is_current = fields.Boolean(default=True)
    encrypted_key = fields.Binary(required=True, attachment=False)
    algorithm = fields.Char(default='AES-256-GCM')
    created_date = fields.Datetime(default=fields.Datetime.now)
    created_by_id = fields.Many2one('res.users')
    expires_date = fields.Datetime()
    purpose = fields.Char()  # 'pii', 'financial', 'index', etc.

    _sql_constraints = [
        ('unique_key_version', 'UNIQUE(key_id, version)',
         'Key version must be unique'),
    ]
```

#### Tier 3: Vault Provider (Enterprise)

```python
class VaultKeyProvider(models.AbstractModel):
    _name = "trn.key.provider.vault"
    _inherit = "trn.key.provider"
    _description = "HashiCorp Vault key provider"

    def _get_vault_client(self):
        """Get authenticated Vault client"""
        import hvac

        url = config.get('vault_url', 'http://localhost:8200')
        auth_method = config.get('vault_auth_method', 'token')

        client = hvac.Client(url=url)

        if auth_method == 'token':
            client.token = config.get('vault_token')
        elif auth_method == 'approle':
            client.auth.approle.login(
                role_id=config.get('vault_role_id'),
                secret_id=config.get('vault_secret_id'),
            )
        elif auth_method == 'kubernetes':
            client.auth.kubernetes.login(
                role=config.get('vault_k8s_role'),
                jwt=self._get_k8s_jwt(),
            )

        return client

    def get_data_key(self, key_id, version=None):
        """
        Use Vault Transit secrets engine for encryption.
        Key never leaves Vault - we send data to Vault for encryption.
        """
        client = self._get_vault_client()
        mount_point = config.get('vault_transit_mount', 'transit')

        # For data key retrieval, use datakey endpoint
        response = client.secrets.transit.generate_data_key(
            name=key_id,
            key_type='aes256-gcm96',
            mount_point=mount_point,
        )

        return base64.b64decode(response['data']['plaintext'])

    def encrypt_with_vault(self, key_id, plaintext):
        """
        Alternative: Encrypt directly with Vault (key never exposed).
        Higher latency but maximum security.
        """
        client = self._get_vault_client()
        response = client.secrets.transit.encrypt_data(
            name=key_id,
            plaintext=base64.b64encode(plaintext).decode(),
        )
        return response['data']['ciphertext']

    def rotate_key(self, key_id):
        """Rotate key in Vault"""
        client = self._get_vault_client()
        client.secrets.transit.rotate_key(name=key_id)
        return self._get_current_version(key_id)
```

**Configuration**:
```ini
# odoo.conf
[encryption]
key_provider = vault
vault_url = https://vault.example.com:8200
vault_auth_method = kubernetes
vault_k8s_role = myproject-prod
vault_transit_mount = transit
```

#### Tier 4: Cloud KMS Provider

```python
class AWSKMSProvider(models.AbstractModel):
    _name = "trn.key.provider.aws_kms"
    _inherit = "trn.key.provider"
    _description = "AWS KMS key provider"

    def get_data_key(self, key_id, version=None):
        """Generate data key using AWS KMS"""
        import boto3

        client = boto3.client('kms', region_name=config.get('aws_region'))
        key_arn = config.get(f'aws_kms_key_{key_id}')

        response = client.generate_data_key(
            KeyId=key_arn,
            KeySpec='AES_256',
        )

        # Return plaintext data key
        # Encrypted version can be stored alongside data for re-decryption
        return response['Plaintext']

    def encrypt_data_key(self, key_id, data_key):
        """Encrypt data key for storage (envelope encryption)"""
        import boto3

        client = boto3.client('kms')
        key_arn = config.get(f'aws_kms_key_{key_id}')

        response = client.encrypt(
            KeyId=key_arn,
            Plaintext=data_key,
        )

        return response['CiphertextBlob']
```

### Layer 4: Search Strategies

Different data types require different search approaches:

#### Exact Match (National IDs, Account Numbers)

```python
def search_by_national_id(self, search_value):
    """Exact match using blind index"""
    blind_index = self._compute_blind_index(
        search_value,
        field_name='national_id',
        index_type='exact'
    )
    return self.search([('national_id_index', '=', blind_index)])
```

#### Partial Match (Last N Digits)

```python
def search_by_phone_partial(self, last_digits):
    """Search by last 4 digits of phone"""
    # Last N digits stored unencrypted
    return self.search([('phone_last4', '=', last_digits)])
```

#### Phonetic Match (Names)

```python
def search_by_name_phonetic(self, name):
    """Fuzzy name search using phonetic encoding"""
    from metaphone import doublemetaphone

    primary, secondary = doublemetaphone(name)
    domain = ['|',
        ('name_metaphone_primary', '=', primary),
        ('name_metaphone_secondary', '=', secondary),
    ]
    return self.search(domain)
```

#### Range Queries (Dates)

```python
# Store year/month unencrypted for range queries
birth_year = fields.Integer(index=True)
birth_month = fields.Integer(index=True)
birthdate_encrypted = fields.Char()  # Full date encrypted

def search_by_birth_year_range(self, year_from, year_to):
    return self.search([
        ('birth_year', '>=', year_from),
        ('birth_year', '<=', year_to),
    ])
```

### Layer 5: UX Components

#### Masked Field Widget

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";
import { useService } from "@web/core/utils/hooks";

export class MaskedPIIField extends CharField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = {
            revealed: false,
            loading: false,
        };
    }

    get displayValue() {
        if (this.state.revealed) {
            return this.props.value;
        }
        return this.applyMask(this.props.value);
    }

    applyMask(value) {
        if (!value) return "";
        const maskPattern = this.props.maskPattern || "****####";
        // Show last 4 characters by default
        const visibleChars = 4;
        const masked = "*".repeat(Math.max(0, value.length - visibleChars));
        return masked + value.slice(-visibleChars);
    }

    async onRevealClick() {
        this.state.loading = true;
        try {
            // Log the reveal action
            await this.orm.call(
                this.props.resModel,
                "log_pii_access",
                [this.props.resId, this.props.name]
            );
            this.state.revealed = true;
            // Auto-hide after 30 seconds
            setTimeout(() => {
                this.state.revealed = false;
                this.render();
            }, 30000);
        } catch (error) {
            this.notification.add(
                "Unable to reveal field. Access may be restricted.",
                { type: "danger" }
            );
        }
        this.state.loading = false;
    }
}

registry.category("fields").add("masked_pii", MaskedPIIField);
```

**Usage in XML**:
```xml
<field name="national_id" widget="masked_pii" options="{'maskPattern': '****-****-####'}"/>
```

#### Re-authentication for Sensitive Actions

```python
class PIIAccessController(http.Controller):

    @http.route('/pii/reveal', type='json', auth='user')
    def reveal_pii(self, model, record_id, field):
        """Reveal PII field value with audit logging"""
        user = request.env.user

        # Check classification
        classification = request.env['trn.field.classification'].search([
            ('model_id.model', '=', model),
            ('field_id.name', '=', field),
        ], limit=1)

        if not classification:
            return {'error': 'Field not found'}

        # Check if re-auth required
        if classification.classification_id.code == 'RESTRICTED':
            if not self._verify_recent_auth(user):
                return {'require_reauth': True}

        # Log access
        request.env['trn.pii.access.log'].sudo().create({
            'user_id': user.id,
            'model': model,
            'res_id': record_id,
            'field_name': field,
            'access_type': 'reveal',
            'ip_address': request.httprequest.remote_addr,
        })

        # Return decrypted value
        record = request.env[model].browse(record_id)
        return {'value': record[field]}
```

### Module Structure

```
trn_pii_encryption/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── encrypted_field_mixin.py
│   ├── key_provider.py
│   ├── key_provider_config.py
│   ├── key_provider_database.py
│   ├── key_provider_vault.py
│   ├── key_provider_aws.py
│   ├── encryption_key.py
│   └── pii_access_log.py
├── controllers/
│   ├── __init__.py
│   └── pii_access.py
├── wizards/
│   ├── __init__.py
│   ├── key_rotation_wizard.py
│   └── bulk_encryption_wizard.py
├── views/
│   ├── encryption_key_views.xml
│   ├── pii_access_log_views.xml
│   ├── key_management_views.xml
│   └── menus.xml
├── security/
│   ├── ir.model.access.csv
│   ├── security_groups.xml
│   └── record_rules.xml
├── data/
│   └── key_purposes.xml
├── static/
│   └── src/
│       ├── js/
│       │   └── masked_pii_field.js
│       └── xml/
│           └── masked_pii_field.xml
└── readme/
    └── DESCRIPTION.md
```

### Implementation for Core Models

```python
# The domain module implementing trn.identifier (e.g., models/identifier.py)
class Identifier(models.Model):
    _inherit = ["trn.identifier", "trn.encrypted.field.mixin"]

    # Encrypted storage (replaces original 'value')
    value_encrypted = fields.Char(string="Encrypted Value")

    # Transparent access
    value = fields.Char(
        compute="_compute_value",
        inverse="_inverse_value",
        store=False,
    )

    # Search indexes
    value_blind_index = fields.Char(index=True, readonly=True)
    value_last4 = fields.Char(index=True, readonly=True)

    @api.depends('value_encrypted')
    def _compute_value(self):
        for record in self:
            if record.value_encrypted:
                record.value = record._decrypt_value(
                    record.value_encrypted, 'value'
                )
            else:
                record.value = False

    def _inverse_value(self):
        for record in self:
            if record.value:
                record.value_encrypted = record._encrypt_value(
                    record.value, 'value'
                )
                record.value_blind_index = record._compute_blind_index(
                    record.value, 'value', 'exact'
                )
                record.value_last4 = record.value[-4:] if len(record.value) >= 4 else record.value
            else:
                record.value_encrypted = False
                record.value_blind_index = False
                record.value_last4 = False

    @api.model
    def search_by_id_value(self, id_value, id_type=None):
        """Search registry IDs by value using blind index"""
        blind_index = self._compute_blind_index(id_value, 'value', 'exact')
        domain = [('value_blind_index', '=', blind_index)]
        if id_type:
            domain.append(('id_type_id', '=', id_type.id))
        return self.search(domain)
```

## Consequences

### Positive

1. **Defense in depth**: Multiple layers of protection
2. **Compliance ready**: Meets GDPR, industry requirements
3. **Flexible deployment**: From simple config to enterprise HSM
4. **Searchable encryption**: Blind indexes maintain functionality
5. **Transparent UX**: Users work normally, protection is invisible
6. **Audit trail**: All PII access is logged

### Negative

1. **Performance overhead**: Encryption/decryption adds latency (~10-50ms per field)
2. **Complexity**: Multiple components to maintain
3. **Key management burden**: Keys must be backed up, rotated, secured
4. **Search limitations**: Some query types not possible on encrypted data
5. **Migration effort**: Existing data must be encrypted

### Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Key loss | LOW | CRITICAL | Key backup procedures, key escrow |
| Performance degradation | MEDIUM | MEDIUM | Caching, async decryption, optimize hot paths |
| Search functionality gaps | MEDIUM | HIGH | Multiple index types, phonetic matching |
| Implementation bugs | MEDIUM | HIGH | Security review, penetration testing |
| Vendor lock-in (KMS) | LOW | LOW | Abstract provider interface |

## Alternatives Considered

### Alternative 1: Database-Only Encryption (TDE/pgcrypto)

**Pros**:
- Transparent to application
- No code changes needed
- Searchable

**Cons**:
- Doesn't protect against SQL injection
- Keys in database = accessible to DBAs
- Column-level encryption (pgcrypto) exposes keys in queries

**Decision**: Rejected as sole solution, but included as base layer.

### Alternative 2: Application Encryption Without Blind Indexes

**Pros**:
- Maximum security
- Simpler implementation

**Cons**:
- No search capability on encrypted fields
- Unusable for registries

**Decision**: Rejected. Search is mandatory for operations.

### Alternative 3: Tokenization Service

**Pros**:
- Industry standard approach
- Separation of data and tokens
- Compliance friendly

**Cons**:
- External service dependency
- Latency for every access
- Cost for managed services

**Decision**: Considered for future. Current approach doesn't preclude this.

### Alternative 4: Homomorphic Encryption

**Pros**:
- Compute on encrypted data
- Ultimate privacy

**Cons**:
- Extremely slow (1000x overhead)
- Limited operations supported
- Immature tooling

**Decision**: Rejected. Not practical for current use case.

## Implementation Plan

| Phase | Deliverable | Effort | Priority |
|-------|-------------|--------|----------|
| 1 | Key management abstraction + config provider | 1 week | P0 |
| 2 | Encrypted field mixin | 1 week | P0 |
| 3 | Blind index implementation | 1 week | P0 |
| 4 | Masked field widget | 3-4 days | P0 |
| 5 | Encrypt `trn.identifier.value` | 3-4 days | P0 |
| 6 | Encrypt `trn.payment.account_number` (planned) | 2-3 days | P0 |
| 7 | Database key provider | 1 week | P1 |
| 8 | Vault provider | 1-2 weeks | P2 |
| 9 | AWS/Azure KMS providers | 1-2 weeks | P2 |
| 10 | Key rotation tooling | 1 week | P1 |
| 11 | Migration tool for existing data | 1 week | P0 |

### Migration Strategy

1. **Deploy module** with encryption disabled
2. **Run migration** to add encrypted columns
3. **Encrypt existing data** in batches (background job)
4. **Enable encryption** for new writes
5. **Verify** all data encrypted
6. **Remove** plaintext columns (future release)

```python
class PIIEncryptionMigration(models.TransientModel):
    _name = "trn.pii.encryption.migration"

    model_id = fields.Many2one('ir.model', required=True)
    field_name = fields.Char(required=True)
    batch_size = fields.Integer(default=1000)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ])
    progress = fields.Float()
    error_log = fields.Text()

    def action_migrate(self):
        """Queue background job to encrypt existing data"""
        self.with_delay().migrate_batch(offset=0)

    def migrate_batch(self, offset):
        """Encrypt batch of records"""
        Model = self.env[self.model_id.model]
        records = Model.search([], limit=self.batch_size, offset=offset)

        for record in records:
            # Trigger encryption via write
            plaintext = record[self.field_name]
            if plaintext and not self._is_encrypted(plaintext):
                record.write({self.field_name: plaintext})

        if len(records) == self.batch_size:
            # More records to process
            self.with_delay().migrate_batch(offset + self.batch_size)
        else:
            self.state = 'completed'
```

## Security Considerations

1. **Key Storage**: Master keys never in database; config/Vault/KMS only
2. **Key Rotation**: Support concurrent key versions during rotation
3. **Audit Logging**: Log all PII access (not values, just access events)
4. **Access Control**: Integrate with `trn_security` for field-level permissions
5. **Secure Deletion**: Crypto-shredding via key destruction
6. **Memory Protection**: Clear plaintext from memory after use
7. **Transport Security**: TLS for all key management communications

## References

- [NIST SP 800-57](https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final) - Key Management Recommendations
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [HashiCorp Vault Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [AWS KMS Developer Guide](https://docs.aws.amazon.com/kms/latest/developerguide/)
- [Blind Index Paper](https://eprint.iacr.org/2019/011.pdf) - Searchable Symmetric Encryption

## Related ADRs

- ADR-011: Data Classification System (prerequisite - defines what to encrypt)
- ADR-004: Access Rights Management (field-level access control)
- ADR-010: Verifiable Credentials System (uses encryption infrastructure)
