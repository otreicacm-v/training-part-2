# ADR-022: API V2 Application-Level Authorization

## Status

Accepted

## Context

The API V2 (`trn_api_v2`, planned) will provide machine-to-machine access to data for external systems
(partner organizations, integrating systems). It will run on Odoo 19 using FastAPI.

Odoo provides built-in authorization via groups and record rules (`ir.rule`). The question is whether the API should
use Odoo's native authorization or implement its own.

### Key constraints

1. **Consent filtering (GDPR Article 6)**: Each API response must be filtered based on whether the individual has
   consented to share their data with the requesting organization. This consent can be:
   - Specific to an organization (`recipient_ids`)
   - Category-based (e.g., "all NGOs" via `organization_type`)
   - Scoped to resource types and field sets (`trn.consent.scope`)

2. **API clients are not Odoo users**: External systems authenticate via OAuth 2.0 (client credentials flow), not
   Odoo user sessions. The API runs as the Public user (uid=3).

3. **Scope-based access control**: Each API client has granular scopes (e.g., `individual:read`, `program:create`)
   that cannot be modeled as Odoo groups without creating one group per client.

4. **Performance**: Consent checks must be fast. The `consent_summary` cache on `res.partner` provides O(1) lookups
   for category-based consent, which would not be possible through `ir.rule` domain evaluation.

## Decision

The API V2 uses **application-level authorization** with `sudo()` to bypass Odoo record rules, implementing a
three-layer authorization stack:

1. **Authentication (JWT)**: Validates the API client identity via signed JWT tokens.
2. **Scope enforcement**: Each endpoint checks `api_client.has_scope(resource, action)` before processing.
3. **Consent filtering**: `ConsentService.filter_response()` applies per-record consent checks, returning only
   data the requesting organization is authorized to see.

All service methods operate on `sudo()` records because the Public user has no inherent access to `res.partner` or
other registry models. Authorization is enforced at the API layer, not the ORM layer.

## Consequences

### Positive

- Consent filtering with field-level granularity works correctly (impossible to express in `ir.rule`)
- Category-based consent ("all NGOs") uses cached O(1) lookups instead of per-query domain evaluation
- Scope enforcement is explicit and auditable in each endpoint
- No need to create/manage Odoo users for API clients

### Negative

- Every service method must use `sudo()`, creating a larger trust boundary
- Authorization bugs in the API layer are not caught by Odoo's ORM safety net
- Requires disciplined code review to ensure all endpoints enforce scopes

### Mitigations

- Comprehensive scope enforcement tests (`test_scope_enforcement.py`) cover every endpoint
- Consent service tests verify filtering behavior for all consent states
- Search endpoints exclude consent-denied records from results to prevent existence leakage
- Audit logging tracks all API access for post-hoc review

## Alternatives Considered

### 1. Odoo record rules per API client

Create an `ir.rule` per client with dynamic domains. Rejected because:
- Cannot express consent field-level filtering in domain syntax
- Category-based consent requires joining consent tables per query
- Performance degrades with many clients (one rule evaluation per client per query)

### 2. Hybrid: Odoo groups for resource access + application-level consent

Use Odoo groups for coarse access (e.g., "can read individuals") and consent service for filtering. Rejected because:
- Would require creating Odoo users for each API client
- Adds complexity without meaningful security benefit (scope checks are equivalent)
- Consent filtering still needs `sudo()` to access consent records
