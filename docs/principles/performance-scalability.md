# Performance & Scalability Principles

Patterns for handling millions of records across large-scale deployments.

## Core Principles

1. **Async-First** - Heavy operations use `queue_job`
2. **Batch Processing** - 5,000 records per chunk
3. **Cursor Pagination** - Never use offset-based pagination
4. **Strategic Caching** - ORM cache with TTL

## Performance Targets

| Operation | Target |
|-----------|--------|
| List view load (10K+ records) | < 2s |
| Form open | < 1s |
| Search (100K+ records) | < 2s |
| API GET single | < 300ms |
| API GET list (100) | < 1s |
| Bulk record import (10K) | < 10min |

## Database Optimization

### Partial Indexes

```sql
-- Only index a subset, not all partners
CREATE INDEX idx_supplier ON res_partner (id)
WHERE is_supplier = true;
```

### Materialized Views

Use for complex reporting queries that don't need real-time data.

## Batch Processing Pattern

Use `queue_job` for batch processing to ensure data consistency. Avoid `self.env.cr.commit()` in loops as it can leave data in a partial state if later chunks fail.

```python
BATCH_SIZE = 5000

def process_large_dataset(self, records):
    """Queue each batch as a separate job for safe processing"""
    for i in range(0, len(records), BATCH_SIZE):
        chunk_ids = records[i:i + BATCH_SIZE].ids
        self.with_delay(
            description=f"Process batch {i // BATCH_SIZE + 1}"
        )._process_chunk(chunk_ids)

def _process_chunk(self, record_ids):
    """Each job runs in its own transaction"""
    records = self.browse(record_ids)
    # Process records...
```

## Async Operations

```python
# Queue heavy operations
self.with_delay(
    priority=5,
    description="Process 10K orders"
)._process_orders(order_ids)
```

## When to Use Async

| Records | Approach |
|---------|----------|
| < 500 | Synchronous |
| 500 - 5,000 | Batch with progress |
| > 5,000 | Background job |

## Pagination

```python
# ✅ Cursor-based
last_id = 0
while True:
    records = Model.search([('id', '>', last_id)], limit=100, order='id')
    if not records:
        break
    last_id = records[-1].id

# ❌ Offset-based (slow at scale)
Model.search([], offset=10000, limit=100)  # DON'T DO THIS
```

## Avoid N+1 Queries

```python
# ❌ N+1 problem
for record in records:
    print(record.partner_id.name)  # Query per record

# ✅ Prefetch
records.mapped('partner_id')  # Single query
for record in records:
    print(record.partner_id.name)
```

## Raw SQL for Bulk Updates

```python
# When ORM is too slow
self.env.cr.execute("""
    UPDATE trn_order
    SET state = 'completed', completed_date = NOW()
    WHERE id = ANY(%s)
""", (list(ids),))
self.env['trn.order'].invalidate_model()
```

## CEL Expression Scalability

CEL expressions are compiled to SQL queries. Poorly written expressions can generate inefficient queries that don't scale.

### Enforced Limits

| Constraint | Limit | Rationale |
|------------|-------|-----------|
| IN clause size | 1,000 items | Large IN clauses are slow and hit parameter limits |
| Negative limit | Normalized to 0 | Prevents database errors |

### Patterns to Avoid

```python
# ❌ Large IN clause - won't scale to millions
r.id in [1, 2, 3, ..., 10000]  # Rejected: exceeds 1000 item limit

# ❌ Building large lists dynamically
ids = [r.id for r in self.env['res.partner'].search([])]
expr = f"r.id in {ids}"  # Don't do this!
```

### Recommended Alternatives

```python
# ✅ Use saved filters/domains instead of ID lists
# Define eligibility criteria as CEL expressions
r.age >= 18 and r.is_active == true

# ✅ Use subqueries via related fields
r.order_ids.exists(o, o.state == "completed")

# ✅ For batch operations, process in chunks
for chunk in chunks(ids, 1000):
    # Process each chunk separately
```

### CEL Performance Best Practices

1. **Prefer field comparisons over ID lists** - `r.age >= 18` is better than `r.id in [list of adult IDs]`
2. **Use indexes** - Ensure CEL-queried fields have database indexes
3. **Avoid cross-model aggregations in tight loops** - Use `queue_job` for heavy metric calculations
4. **Cache computed values** - Use stored computed fields or `ir.config_parameter` for expensive calculations with TTL

## Linting and Enforcement

A performance linter exists at `scripts/lint/check_performance.py` to detect:
- N+1 query patterns
- Offset-based pagination
- `cr.commit()` in loops

> **Note:** As of 2025-12, the linter is not yet enforced in CI.
> Run it manually before submitting PRs with data-heavy operations.

---

**See also:** [Testing](testing.md), [Approval Workflows](approval-workflows.md)
