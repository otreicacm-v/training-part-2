# ADR-010: API V2 Architecture

**Status:** **IMPLEMENTED** - Phase 1 & 2 complete, Phase 3 basic, Phase 4 deferred
**Date:** 2024-11-28
**Accepted Date:** 2025-12-04
**Decision Makers:** Architecture Team
**Technical Story:** Design a modern, scalable API V2

### Implementation Summary

| Phase | Status | Components |
|-------|--------|------------|
| Phase 1: Foundation | ✅ Complete | OAuth2, external IDs, consent filtering, FastAPI |
| Phase 2: Transactions | ✅ Complete | Bundle/$batch, placeholder resolution, atomic rollback |
| Phase 3: Extensions | ⚠️ Basic | Extension registry, manual module registration |

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI routers | ✅ Complete | 9 routers: oauth, metadata, individual, group, program, membership, consent, batch, filter |
| OAuth2 client credentials | ✅ Complete | Scrypt-hashed secrets, JWT tokens, 1h expiry |
| External identifiers only | ✅ Complete | No DB IDs exposed (verified in tests) |
| Consent-based filtering | ✅ Complete | Field-level scoping, legal basis support |
| FHIR-inspired patterns | ✅ Complete | CapabilityStatement, Bundle, CodeableConcept |
| Tests | ✅ Complete | 169 tests (~95% coverage), 23 test files |
| Rate limiting | ❌ Not enforced | Model defined, middleware not implemented |

**Code Location:** `trn_api_v2/` module (planned)

## Context

The system needs a robust API layer that:
- Scales to 50M+ records
- Supports multiple integration patterns (REST, FHIR-inspired)
- Respects consent and data sharing policies
- Handles extensible models (modules can add fields)
- Performs well despite Odoo's inherent overhead

### Current State Analysis

| Module | Purpose | Technology |
|--------|---------|------------|
| `trn_api` | Base API with bearer tokens | JSON-RPC |
| `trn_api` | Resource CRUD | FastAPI + Pydantic |
| `trn_fhir_api_server` | FHIR-compliant registry access | Odoo HTTP Controller |
| `fastapi` | OCA FastAPI integration | FastAPI + a2wsgi |
| `extendable_fastapi` | Schema extension support | extendable-pydantic |

**Issues with Current Implementation:**
1. Multiple inconsistent API patterns
2. Internal database IDs exposed in some endpoints
3. No formal capability discovery
4. Limited consent-based field filtering
5. No bundle/transaction support for atomic operations
6. Extension fields not automatically exposed

## Decision

### 1. Primary API Paradigm: REST

**Decision:** REST as the primary API paradigm.

**Rationale:**

| Factor | Why REST |
|--------|----------|
| Government/Enterprise fit | Mature, auditable, well-understood |
| Standards compliance | Native fit with existing standards |
| Caching | HTTP-native (CDN, browser) |
| Security | Well-understood patterns |
| Performance at scale | Scales to 100K+ req/s |
| Odoo integration | Natural fit with ORM |

### 2. Architecture: Enhanced Odoo (Not Microservice)

**Decision:** Keep API within Odoo, leveraging Odoo 19 + PostgreSQL 17/18 improvements.

**Against Microservice:**
- Data duplication complexity at 50M scale
- Sync lag for real-time requirements
- Additional infrastructure (message queues, sync jobs)
- Loss of Odoo's transactional guarantees

**Performance Strategy:**

```
┌─────────────────────────────────────────────────────────────┐
│                     Load Balancer                           │
└─────────────────────────────┬───────────────────────────────┘
                              │
                        ┌─────▼─────┐
                        │   Odoo    │
                        │   API     │
                        │  Workers  │
                        └─────┬─────┘
                              │
                        ┌─────▼─────┐
                        │ PostgreSQL│
                        │   + Pool  │
                        └───────────┘
```

**Optimizations:**
1. **PgBouncer** for connection pooling
2. **PostgreSQL 17/18 async I/O** (2-3x improvement for read-heavy)
3. **Odoo 19 workers** = 2 × CPU cores
4. **Redis** for session/cache (optional)

### 3. FHIR-Inspired Patterns

Adopt these patterns from FHIR without full compliance:

#### 3.1 Capability Statement

```json
GET /api/v2/trn/metadata

{
  "resourceType": "CapabilityStatement",
  "version": "2.0.0",
  "status": "active",
  "date": "2024-11-28",
  "kind": "instance",
  "software": {
    "name": "MyProject",
    "version": "19.0.2.0.0"
  },
  "resources": [
    {
      "type": "Individual",
      "supportedProfiles": ["urn:tpl:profile:individual:basic"],
      "interactions": ["read", "search", "create", "update"],
      "searchParams": [
        {"name": "identifier", "type": "token"},
        {"name": "name", "type": "string"},
        {"name": "birthdate", "type": "date"}
      ]
    },
    {
      "type": "Group",
      "interactions": ["read", "search", "create", "update"],
      "searchParams": [...]
    }
  ],
  "extensions": [
    {
      "module": "trn_custom",
      "fields": ["custom_category", "tags", "priority"]
    }
  ]
}
```

**Value:** Clients can discover available endpoints, fields, and module extensions.

#### 3.2 Bundle Transactions

```json
POST /api/v2/trn/$batch

{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [
    {
      "request": {"method": "POST", "url": "Individual"},
      "resource": {
        "identifier": [{"system": "urn:gov:us:ssa:ssn", "value": "123-45-6789"}],
        "name": {"given": "Jane", "family": "Smith"}
      },
      "fullUrl": "urn:uuid:temp-1"
    },
    {
      "request": {"method": "POST", "url": "Group"},
      "resource": {
        "name": "Smith Household",
        "member": [{"reference": "urn:uuid:temp-1", "role": "head"}]
      },
      "fullUrl": "urn:uuid:temp-2"
    },
    {
      "request": {"method": "POST", "url": "ProgramMembership"},
      "resource": {
        "individual": {"reference": "urn:uuid:temp-2"},
        "program": {"reference": "Program/benefits"}
      }
    }
  ]
}
```

**Features:**
- Atomic transactions (all-or-nothing)
- Placeholder UUIDs for cross-references
- Batch mode available (independent operations)

#### 3.3 External Identifiers Only

Per existing ADR-007, never expose database IDs:

```json
// ❌ WRONG
{"id": 12345, "name": "Maria"}

// ✅ CORRECT
{
  "identifier": [
    {"system": "urn:gov:us:ssa:ssn", "value": "123-45-6789"}
  ],
  "name": {"given": "Jane", "family": "Smith"}
}
```

### 4. Consent-Based Data Access

#### 4.1 Consent Model Enhancement

Extend `trn.consent` to support field-level consent:

```python
class ConsentScope(models.Model):
    _name = "trn.consent.scope"

    consent_id = fields.Many2one("trn.consent")
    resource_type = fields.Selection([
        ("individual", "Individual"),
        ("group", "Group"),
        ("encounter", "Encounter"),
    ])
    fields_allowed = fields.Many2many("ir.model.fields")  # Explicit allow-list
    purpose = fields.Selection([
        ("service_delivery", "Service Delivery"),
        ("analytics", "Anonymized Analytics"),
        ("research", "Research"),
        ("audit", "Audit"),
    ])
    third_party_id = fields.Many2one("res.partner")  # Who can access
    valid_until = fields.Date()
```

#### 4.2 API Client Scopes

Each API client gets explicit scopes:

```python
class ApiClientScope(models.Model):
    _name = "trn.api.client.scope"

    client_id = fields.Many2one("trn.api.client")
    resource = fields.Selection([...])
    actions = fields.Selection([
        ("read", "Read"),
        ("search", "Search"),
        ("write", "Write"),
    ], multiple=True)
    field_filter_id = fields.Many2one("trn.api.field.filter")
    require_consent = fields.Boolean(default=True)
```

#### 4.3 Request-Time Consent Check

```python
def filter_response_by_consent(individual, api_client, response_data):
    """Filter response fields based on consent and client scope."""

    # Get active consent for this individual + client
    consent = env["trn.consent"].search([
        ("partner_id", "=", individual.id),
        ("third_party_id", "=", api_client.partner_id.id),
        ("expiry", ">", fields.Date.today()),
    ])

    if not consent:
        # Return minimal identifier-only response
        return {"identifier": response_data["identifier"]}

    # Filter to consented fields only
    allowed_fields = consent.scope_ids.mapped("fields_allowed.name")
    return {k: v for k, v in response_data.items() if k in allowed_fields}
```

### 5. Extensible Schema Pattern

Handle modules that add fields to resources:

#### 5.1 Extension Registry

```python
class ApiExtension(models.Model):
    _name = "trn.api.extension"
    _description = "API Extension Registry"

    name = fields.Char(required=True)
    module_id = fields.Many2one("ir.module.module")
    base_resource = fields.Selection([
        ("individual", "Individual"),
        ("group", "Group"),
    ])
    field_ids = fields.Many2many("ir.model.fields")
    schema_definition = fields.Text()  # JSON Schema fragment

    @api.model
    def get_extended_schema(self, resource_type):
        """Merge base schema with all active extensions."""
        extensions = self.search([
            ("base_resource", "=", resource_type),
            ("module_id.state", "=", "installed"),
        ])
        # Build merged Pydantic model dynamically
        ...
```

#### 5.2 Dynamic Schema Generation

```python
# In a domain module
class CustomExtension(models.Model):
    _inherit = "trn.api.extension"

    @api.model
    def _register_extension(self):
        self.create({
            "name": "Custom Extension",
            "base_resource": "individual",
            "field_ids": [(6, 0, [
                self.env.ref("trn_custom.field_category").id,
                self.env.ref("trn_custom.field_tags").id,
            ])],
        })
```

#### 5.3 Response with Extensions

```json
GET /api/v2/trn/individual/ID-123456789?_extensions=extra_fields

{
  "identifier": [...],
  "name": {"given": "Jane", "family": "Smith"},
  "extensions": {
    "extra_fields": {
      "url": "urn:tpl:extension:extra_fields",
      "custom_category": "premium",
      "tags": [
        {
          "code": "VIP",
          "display": "VIP Customer",
          "system": "urn:tpl:vocab:tags"
        }
      ]
    }
  }
}
```

### 6. API Module Structure (planned)

```
trn_api_v2/                       # Planned module
├── models/
│   ├── api_client.py            # Client credentials + scopes
│   ├── api_extension.py         # Extension registry
│   └── consent_scope.py
├── schemas/
│   ├── base.py                  # BaseResource, Identifier, CodeableConcept
│   └── extensions/              # Auto-loaded from installed modules
├── routers/
│   ├── metadata.py              # GET /metadata
│   ├── individual.py            # CRUD + search
│   └── batch.py                 # POST /$batch
├── middleware/
│   ├── consent_filter.py        # Response filtering
│   └── audit_log.py             # Request/response logging
├── security/
│   └── ir.model.access.csv
└── tests/
```

### 7. Versioning Strategy

```
/api/v2/trn/...          # Current stable
/api/v3/trn/...          # Next major (when needed)
/api/v2-beta/trn/...     # Preview features

Response headers:
X-API-Version: 2.0.0
X-Deprecation-Notice: v1 endpoints deprecated, sunset 2025-06-01
```

## Consequences

### Positive
- Standards-aligned (FHIR-inspired patterns)
- Consent-respecting by design
- Extension-friendly for modules
- No microservice complexity
- Leverages Odoo 19 + PG18 improvements

### Negative
- Still bound to Odoo's ORM performance
- Complex consent logic adds latency
- Dynamic schema generation adds complexity

### Risks
- Performance at extreme scale (100M+) may require additional caching
- Consent logic needs careful testing to avoid data leaks

## Performance Benchmarks (Target)

| Operation | Target Latency (p95) | Throughput |
|-----------|---------------------|------------|
| Single read | <100ms | 1000 req/s |
| Search (100 results) | <500ms | 200 req/s |
| Batch create (100 records) | <2s | 50 req/s |
| Capability statement | <50ms | 5000 req/s (cached) |

## Implementation Phases

### Phase 1: Foundation ✅
- [x] Core schema models (Individual, Group)
- [x] Capability statement endpoint
- [x] External identifier enforcement
- [x] Basic consent filtering
- [x] OAuth2 client credentials with JWT

### Phase 2: Transactions ✅
- [x] Bundle transaction support
- [x] Placeholder ID resolution
- [x] Atomic rollback

### Phase 3: Extensions (In Progress)
- [x] Extension registry
- [ ] Dynamic schema generation (partial)
- [ ] Auto-discovery of module extensions

## References

- [FHIR HTTP Interactions](https://www.hl7.org/fhir/http.html)
- [FHIR RESTful API](https://www.hl7.org/fhir/http.html)
- [Odoo 19 Query Optimizations](https://stormatics.tech/blogs/query-optimizations-in-odoo-versions-17-19-for-faster-postgresql-performance)
- [PostgreSQL 18 Async I/O](https://betterstack.com/community/guides/databases/postgresql-asynchronous-io/)
- [GraphQL vs REST 2024 Comparison](https://tailcall.run/graphql/graphql-vs-rest-api-comparison/)

## Related ADRs

- ADR-007: Namespace URIs for Identifiers
- ADR-009: Vocabulary System
