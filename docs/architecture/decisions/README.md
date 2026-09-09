# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records documenting significant architectural decisions for the project.

## ADR Index

| # | Title | Status | Date | Summary |
|---|-------|--------|------|---------|
| [004](ADR-004-access-rights-management.md) | Access Rights Management | **Implemented** | 2025-11-26 | Three-tier security with Odoo 19 privileges |
| [007](ADR-007-namespace-uris-for-identifiers.md) | Namespace URIs for Identifiers | **Implemented** | 2025-11-28 | Globally unique URIs for ID types |
| [009](ADR-009-terminology-system.md) | Vocabulary System | **Implemented** | 2025-11-28 | Standard + extensible code vocabularies |
| [010](ADR-010-api-v2-architecture.md) | API V2 Architecture | **Implemented** | 2024-11-28 | REST-first, consent-based |
| [011](ADR-011-data-classification-system.md) | Data Classification System | **Implemented** | 2025-11-28 | PII taxonomy, masking, GDPR compliance |
| [012](ADR-012-pii-encryption-strategy.md) | PII Encryption Strategy | Accepted | 2025-11-28 | Application-level encryption + blind indexes |
| [018](ADR-018-dms-security-and-storage-enhancements.md) | DMS Security & Storage Enhancements | **Implemented** | 2025-12-14 | AV scanning, pluggable storage, audit |
| [020](ADR-020-unified-api-audit-log.md) | Unified API Audit Log | Accepted | 2025-12-14 | Single audit model for all API operations |
| [022](ADR-022-api-v2-application-level-authorization.md) | API V2 Application-Level Authorization | Accepted | 2025-12-14 | Scope + consent-based API auth |
| [023](ADR-023-bookstore-counter-on-sale-orders.md) | Bookstore Counter on Sale Orders | Accepted | 2026-09-09 | Build the school bookstore on `sale`, not `point_of_sale` |

## Status Legend

| Status | Meaning |
|--------|---------|
| **Proposed** | Under discussion, not yet approved |
| **Accepted** | Approved, implementation pending or in progress |
| **Implemented** | Fully implemented and in production |
| **Partial** | Partially implemented |
| **Deprecated** | No longer recommended |
| **Superseded** | Replaced by another ADR |

## Context

ADR-023 is specific to the school bookstore system. The remaining ADRs (004, 007, 009-012, 018, 020, 022) cover cross-cutting concerns (security, identifiers, terminology, data classification, encryption, document management, API audit/auth) that apply to any Odoo 19 project using the `trn_*` module convention.

## Creating New ADRs

1. Use the next available number (currently 024)
2. Follow the template: `ADR-NNN-short-title.md`
3. Include: Status, Date, Context, Decision, Consequences
4. Update this index after creating
