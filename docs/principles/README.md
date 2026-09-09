# Training Sample Development Principles

This directory contains the core principles and standards that guide Training Sample development. These principles ensure consistency, maintainability, and quality across all modules.

## Principle Documents

| Document | Description |
|----------|-------------|
| [Naming Conventions](naming-conventions.md) | Standards for naming modules, models, fields, XML IDs, and security groups |
| [Access Rights](access-rights.md) | Security architecture, permission levels, and group hierarchy |
| [Module Architecture](module-architecture.md) | Module organization, consolidation decisions, and extension patterns |
| [Module Visibility](module-visibility.md) | `application`, `auto_install`, and category settings |
| [API Design](api-design.md) | External identifiers, API standards, and integration patterns |
| [Performance & Scalability](performance-scalability.md) | Database optimization, batch processing, and async patterns |
| [Testing](testing.md) | Coverage targets, test types, and quality requirements |
| [Approval Workflows](approval-workflows.md) | Standardized approval patterns and state machines |
| [Error Handling & Logging](error-handling.md) | Exception patterns, logging standards, and PII protection |
| [Audit & Compliance](audit-compliance.md) | Audit trails, data integrity, and regulatory compliance |
| [UI Design](ui-design.md) | Form layouts, tab structure, extension points, and CSS patterns |
| [UI Entity Classification](ui-entity-classification.md) | Choose UI patterns based on entity type and record volume |
| [UI Performance](ui-performance.md) | Scalability patterns for list views, search panels, and large datasets |
| [Pretty URLs](pretty-urls.md) | User-friendly URL paths for actions |
| [Odoo 19 Compatibility](odoo19-compatibility.md) | Odoo 19 gotchas (constraints, views, Command API) |
| [Module Descriptions](module-descriptions.md) | Writing readme/DESCRIPTION.md files for modules |

## How to Use These Principles

1. **New Development**: Review relevant principles before starting new features
2. **Code Reviews**: Reference principles when reviewing pull requests
3. **Onboarding**: New team members should read all principle documents
4. **Decision Making**: Use principles to guide architectural decisions

## Relationship to Other Documentation

These principles are extracted from and complement:

- [Architecture Decisions](../architecture/decisions/) - Architectural Decision Records (ADRs)

## Contributing

When proposing changes to principles:

1. Create an ADR in `docs/architecture/decisions/` for significant changes
2. Update the relevant principle document
3. Ensure consistency across all principle documents
4. Get team review before merging
