# ADR-004: Access Rights Management Architecture

## Status

**IMPLEMENTED** - Core architecture complete, rollout ongoing

**Date:** 2025-11-26
**Implementation Date:** 2025-12-04

**Decision Owners:** Core Team

### Implementation Summary

| Component | Status | Notes |
|-----------|--------|-------|
| trn_security core module | ✅ Complete | 26 domain categories defined |
| Odoo 19 privilege system | ✅ Complete | Uses `res.groups.privilege` |
| Three-tier architecture | ✅ Complete | Technical → Functional → Roles |
| Core domain modules | ✅ Complete | 13 modules fully implemented |
| Naming conventions | ✅ 95% | Minor variations documented |
| Remaining modules | 🔄 In progress | ~21 partial, ~111 pending |

### Implementation Coverage

| Category | Modules | Status |
|----------|---------|--------|
| **Fully implemented** | trn_contact, trn_vocabulary + others | Complete |
| **Not yet migrated** | Remaining modules | Future scope |

**Key Code Locations:**
- `trn_security/security/categories.xml` - All 26 domain categories
- `trn_security/security/groups_admin.xml` - Admin group + Odoo system admin link
- `trn_contact/security/` - Reference implementation (groups.xml, privileges.xml)

**Note:** The architecture is strategically sound. Not all modules require domain-specific security roles.

## Context

The project currently has a fragmented access rights implementation:

- **82 modules** with security definitions
- **60+ unique security groups** scattered across modules
- **14 module categories** for organizing groups
- **29 record rules** with varied patterns
- **Inconsistent naming** conventions across modules

### Problems Identified

1. **Inconsistent Naming**: Groups use mixed patterns (`group_trn_admin` vs `read_registry` vs `group_user`)
2. **Odoo 19 Incompatibility**: Most groups don't use the new `res.groups.privilege` model
3. **No Central Definition**: Each module defines groups independently, causing duplication
4. **Role Confusion**: Users must be assigned to multiple scattered groups
5. **Missing Documentation**: No security matrix or group hierarchy documentation
6. **Collision Risk**: Generic names like `group_user` defined in multiple modules

### Odoo 19 Changes

- `category_id` field removed from `res.groups`
- New `res.groups.privilege` model introduced for UI organization
- Old tuple syntax `(4, ref())` deprecated in favor of `Command.link()`

## Decision

**We will implement a three-tier access rights architecture with domain-specific group definitions.**

### Core Principles

1. **Modular by Design**: Groups defined in their domain modules, not centrally
2. **Layered Architecture**: Roles → Privileges → Base Permissions
3. **Odoo 19 Native**: Full use of `res.groups.privilege` system
4. **Consistent Naming**: Strict naming conventions enforced
5. **Flexible Extension**: Modules can extend, not override
6. **Documentation First**: Every group has `comment` field documentation
7. **Categories Centralized, Groups Distributed**: Category hierarchy in `trn_security`, groups in domain modules

### Key Design Constraint: Modular Installations

The system is designed for flexibility. Each implementation selects modules based on their specific requirements. There is
no "standard" or "typical" configuration.

**Examples of possible configurations (non-exhaustive):**

- Contact only
- Contact + Order + Notes
- Contact + Inventory + Requisitions
- Contact + Lab Orders + Observations
- Any other valid combination...

**The access rights system must not assume any particular module combination.** Groups must only exist when their domain
module is installed, preventing UI clutter and ensuring clean permission boundaries regardless of which modules are
active.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TIER 1: USER ROLES (optional)                    │
│  Defined in: trn_roles module (optional)                            │
│  Example: "Operations Staff" = Contact Officer + Order Officer       │
│  NOTE: Only available when multiple domain modules installed        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TIER 2: FUNCTIONAL PRIVILEGES                    │
│  Defined in: Each domain module (trn_contact, trn_order, etc.)         │
│  Example: Contact Viewer, Contact Officer, Contact Manager           │
│  NOTE: Groups only exist when domain module is installed            │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TIER 3: BASE PERMISSIONS                         │
│  Defined in: Each domain module alongside Tier 2                    │
│  Example: group_contact_read, group_contact_write                   │
│  NOTE: Technical groups, not user-facing                            │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    trn_security (Core)                              │
│  - Category hierarchy (ir.module.category)                          │
│  - Admin group (always needed)                                      │
│  - Base multi-company record rules                                  │
│  - Backward-compatible aliases (migration period)                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Naming Conventions

| Type                     | Pattern                      | Example                               |
| ------------------------ | ---------------------------- | ------------------------------------- |
| Module Category          | `category_trn_{domain}`      | `category_trn_contact`                |
| Privilege                | `privilege_{domain}_{level}` | `privilege_contact_officer`           |
| User Group (Tier 2)      | `group_{domain}_{level}`     | `group_contact_officer`               |
| Technical Group (Tier 3) | `group_{domain}_{action}`    | `group_contact_read`                  |
| Role (Tier 1)            | `role_trn_{name}`            | `role_trn_clinical_staff`             |
| Access CSV ID            | `access_{model}_{group}`     | `access_res_partner_patient_officer`  |
| Record Rule ID           | `rule_{model}_{purpose}`     | `rule_partner_company`                |

### Domain Categories

| Domain          | Category ID                   | Description                  |
| --------------- | ----------------------------- | ---------------------------- |
| Contact         | `category_trn_contact`        | Contact management           |
| Order           | `category_trn_order`          | Order management             |
| Inventory       | `category_trn_inventory`      | Inventory management         |
| Approvals       | `category_trn_approvals`      | Approval workflow            |
| Payments        | `category_trn_payments`       | Payment processing           |
| API             | `category_trn_api`            | API access                   |
| Admin           | `category_trn_admin`          | System administration        |

### Permission Levels

Each domain should define up to 4 levels:

| Level | Name    | Typical Permissions          |
| ----- | ------- | ---------------------------- |
| 1     | Viewer  | Read only                    |
| 2     | Officer | Read, Write, Create          |
| 3     | Manager | All + some admin functions   |
| 4     | Admin   | Full access including delete |

## Implementation

### New Module: `trn_security`

Central module that defines:

- All module categories
- All privileges
- Base technical groups
- Core record rules (company, ownership)

### Module Structure

```
trn_security/
├── __manifest__.py
├── __init__.py
├── security/
│   ├── categories.xml          # ir.module.category records
│   ├── privileges.xml          # res.groups.privilege records
│   ├── groups_base.xml         # Tier 3: Technical groups
│   ├── groups_contact.xml      # Tier 2: Contact domain
│   ├── groups_order.xml        # Tier 2: Order domain
│   ├── groups_admin.xml        # Admin groups
│   ├── rules_base.xml          # Base record rules
│   └── ir.model.access.csv     # Base model access
└── readme/
    └── DESCRIPTION.md
```

### Existing Module Updates

Each existing module should:

1. Depend on `trn_security`
2. Remove duplicate group definitions
3. Reference groups from `trn_security`
4. Add domain-specific groups if needed (following conventions)

### Migration Strategy

**Phase 1: Create `trn_security` module**

- Define all categories and privileges
- Define base technical groups
- No breaking changes to existing modules

**Phase 2: Update core modules**

- `trn_contact` → use `trn_security` groups
- `trn_vocabulary` → use `trn_security` groups
- `trn_order` (planned) → use `trn_security` groups

**Phase 3: Update remaining modules**

- Gradually migrate all 82 modules
- Maintain backward compatibility via group aliases

**Phase 4: Cleanup**

- Remove deprecated group aliases
- Update documentation
- Final security audit

## Consequences

### Positive

1. **Consistency**: One naming convention, one hierarchy
2. **Maintainability**: Central location for security definitions
3. **Odoo 19 Ready**: Native privilege system support
4. **Better UX**: Organized groups in user settings
5. **Documentation**: Built-in via `comment` fields
6. **Flexibility**: Clear extension patterns for implementations

### Negative

1. **Migration Effort**: All 82 modules need updates
2. **New Dependency**: All modules depend on `trn_security`
3. **Learning Curve**: Team must learn new conventions
4. **Potential Breakage**: Existing customizations may need updates

### Risks & Mitigations

| Risk                          | Probability | Impact | Mitigation                                   |
| ----------------------------- | ----------- | ------ | -------------------------------------------- |
| Breaking existing deployments | MEDIUM      | HIGH   | Backward-compatible aliases, migration guide |
| Complex group hierarchy       | LOW         | MEDIUM | Clear documentation, simple patterns         |
| Performance impact            | LOW         | LOW    | Efficient group inheritance                  |
| Team adoption                 | MEDIUM      | MEDIUM | Training, code review enforcement            |

## Alternatives Considered

### Alternative 1: Keep Current Structure

**Pros:**

- No migration effort
- No risk of breaking changes

**Cons:**

- Continued inconsistency
- Odoo 19 incompatibility grows
- Technical debt accumulates

**Decision:** Rejected - Odoo 19 forces changes anyway

### Alternative 2: Per-Module Privilege System

**Pros:**

- Less coupling between modules
- More flexibility

**Cons:**

- Continued fragmentation
- No consistent user experience
- Harder to define cross-cutting roles

**Decision:** Rejected - doesn't solve core problems

### Alternative 3: External RBAC System

**Pros:**

- More powerful role management
- Industry-standard approach

**Cons:**

- Additional system to maintain
- Not native to Odoo
- Higher complexity

**Decision:** Rejected - Odoo's built-in system is sufficient

## Success Criteria

Migration is successful if:

- [ ] All 82 modules use consistent naming
- [ ] All groups use `res.groups.privilege` system
- [ ] Security matrix documentation complete
- [ ] No duplicate group definitions
- [ ] All implementations can extend the base system
- [ ] User settings show organized privilege structure

## References

- [Odoo 19 Groups Documentation](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html)

---

**Document Version:** 1.0 **Last Updated:** 2025-11-26 **Next Review:** After Phase 1 implementation
