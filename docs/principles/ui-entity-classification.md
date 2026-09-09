# UI Entity Classification

Quick reference for choosing UI patterns based on entity type.

---

## The 6 Entity Classes

| Class | Examples | Record Count | Update Freq | UI Pattern |
|-------|----------|--------------|-------------|------------|
| **Master Data** | Categories, tags, settings, areas | <1k | Rare | Simple 1-2 tab form |
| **Workflow Entities** | Orders, requests, approvals, transfers | <10k | Regular | 4-5 tab form + kanban |
| **Registry Entities** | Contacts, products, warehouses | 100k-10M | Moderate | 4-7 tab form, stat buttons |
| **Transactional** | Stock moves, journal entries, audit logs | 1M-100M | High | Minimal form, import/export |
| **Relationship (Simple)** | Area assignments, tags | Variable | Follows parent | Embedded only, no standalone view |
| **Relationship (Rich)** | Order line items, group membership | Variable | Moderate | Embedded + searchable list view |

---

## Classification Decision Tree

```
Does the entity have a state-based workflow?
├─ No → Is it a lookup/configuration table?
│   └─ Yes → MASTER DATA
│   └─ No → Does it link two other entities?
│       └─ Yes → Is it a log/event created in bulk?
│       │   └─ Yes → TRANSACTIONAL
│       │   └─ No → Does it need searchable list view?
│       │       └─ Yes → RELATIONSHIP (Rich)
│       │       └─ No → RELATIONSHIP (Simple)
│       └─ No → Is it a log/event created in bulk?
│           └─ Yes → TRANSACTIONAL
│           └─ No → REGISTRY ENTITY
└─ Yes → WORKFLOW ENTITY
```

---

## Prescribed Patterns by Class

| Class | Form Tabs | List Limit | Search Panel | Analytics | Kanban | O2M Edit |
|-------|-----------|------------|--------------|-----------|--------|----------|
| Master Data | 1-2 | None | ✅ Yes | ❌ No | ❌ No | Inline |
| Workflow | 4-5 | 80 | ✅ Yes | ✅ Include | ✅ Yes | Wizard |
| Registry | 4-7 | 80 | ⚠️ Selective | ⚠️ Separate | ❌ No | Wizard |
| Transactional | 2-3 | 80 | ❌ No | ❌ Pre-agg | ❌ No | Import |
| Relationship (Simple) | None | Parent | Parent | ❌ No | ❌ No | Parent |
| Relationship (Rich) | 2-3 | 80 | ⚠️ Yes | ⚠️ Separate | ❌ No | Wizard |

**Usage**: Classify your entity first → patterns are automatically prescribed

**Relationship (Simple) vs (Rich)**:
- **Simple**: Pure join table, no additional attributes beyond foreign keys (e.g., `trn.area.assignment`)
- **Rich**: Has own attributes, state, dates; needs reconciliation and auditing (e.g., `trn.order.line` with scheduled_date, state, product_id)

---

## Reference Implementations

| Class | Module | Key Views |
|-------|--------|-----------|
| Master Data | `trn_area` | `views/area.xml` |
| Workflow Entity | `trn_order` (planned) | `views/order_view.xml` |
| Registry Entity | `trn_vocabulary` | `views/vocabulary_views.xml` |
| Transactional | `trn_log` (planned) | `views/log_view.xml` |

---

## Examples by Class

### Master Data
- `trn.area` - Geographic areas
- `trn.vocabulary` - Vocabulary definitions (status codes, categories, types)
- `res.country` - Countries

**Characteristics**: Few records, rarely change, simple structure

---

### Workflow Entities
- `trn.order` (planned) - Business orders
- `trn.request` (planned) - Service requests
- `trn.transfer` (planned) - Stock transfers

**Characteristics**: State machine, approval workflows, moderate record count

---

### Registry Entities
- `res.partner` (as contact) - Contact records
- `product.product` - Product records

**Characteristics**: Large record count, complex relationships, many tabs

---

### Transactional
- `trn.log.entry` (planned) - Activity log entries
- `trn.audit.log` - Audit trail entries

**Characteristics**: Millions of records, created in bulk, import/export heavy

---

### Relationship (Simple)
- `trn.area.assignment` - Area assignments (just partner_id + area_id)
- Many2many through tables with no extra fields

**Characteristics**: Pure join table, no additional attributes, embedded only

---

### Relationship (Rich)
- `trn.order.line` (planned) - Order line items (has scheduled_date, state, product_id)
- `trn.identifier` - Entity identifiers (has type, value, system_uri)

**Characteristics**: Join table with attributes, state, dates; needs searchable list for reconciliation and auditing

---

**Full patterns**: See [ui-design.md](ui-design.md) for templates and [ui-performance.md](ui-performance.md) for scalability rules.
