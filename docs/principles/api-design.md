# API Design Principles

Standards for building APIs in Training Sample.

## Core Principles

1. **External Identifiers Only** - Never expose internal database IDs
2. **Standards-Based** - Use well-known standards for interoperability
3. **Field Filtering** - Control which fields are returned per endpoint
4. **Versioned** - Explicit versioning with deprecation periods

## External Identifier Rule (Critical)

**NEVER expose internal database IDs for cross-system integration.**

```python
# WRONG - exposes internal ID
{
    "id": 12345,
    "name": "Jane Smith"
}

# CORRECT - uses external identifiers
{
    "identifier": [
        {"name": "National ID", "identifier": "US-123456789"},
        {"name": "Tax ID", "identifier": "12-3456789"}
    ],
    "name": "Jane Smith"
}
```

**Why:** Integrated systems require stable, external IDs for cross-system references.

## Use `trn.identifier` for All Identifiers

```python
# Single system for flexible + external IDs
trn.vocabulary.code  # Configuration: identifier types (National ID, Tax ID, etc.)
trn.identifier       # Storage: partner_id, type_id, system_uri, value
res.partner.identifier_ids → Many trn.identifier records
```

## API Response Pattern

```json
{
    "identifier": [...],
    "givenName": "Jane",
    "familyName": "Smith",
    "birthDate": "1990-01-15"
}
```

## Versioning

- Path-based: `/api/v1/`, `/api/v2/`
- 6-month compatibility period for deprecated endpoints
- Deprecation warnings in response headers

```python
@route('/api/v2/trn/contacts/<id>')
```

## Namespace Convention

All APIs use the `trn.*` namespace:

- Models: `trn.{domain}` or `trn.{domain}.{entity}`
- REST mixins: `trn.process.individual.rest.mixin`, `trn.process.group.rest.mixin`

## Field Filtering

Use `trn.api.path` model for configuration:

```
API Path → field_ids → Only these fields returned
        → filter_domain → Which records accessible
        → limit → Max records per request
```

## Supported Standards

| Standard | Purpose |
|----------|---------|
| REST/JSON | Standard API format |
| OpenID VCI | Verifiable credentials |

## Authentication

- OAuth 2.0 for external APIs
- API keys with scoped permissions
- Audit logging via `trn_api.log`

---

**Authoritative Sources:**
- Architecture documentation for API-First design philosophy

**See also:** [Module Architecture](module-architecture.md), [Access Rights](access-rights.md)
