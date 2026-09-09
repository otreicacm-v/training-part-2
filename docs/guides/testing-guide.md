# Testing Guide

How to write, run, and maintain tests for project modules.

## Running Tests

```bash
# Run all tests for a single module (recommended — Docker-isolated, cross-platform)
./odoo-project test trn_inventory

# Run multiple modules
./odoo-project test trn_vocabulary
./odoo-project test trn_project

# Filter by test tags
./odoo-project test trn_inventory --tags=post_install
```

The CLI creates a temporary database (`test_<module>_<random>`), installs the module and all dependencies, runs the test suite, then tears it down. It uses `--no-http` so no port binding is needed.

If you are working inside a DevContainer (Claude Code web), run `./scripts/setup_test_env.sh` once per session before testing.

## Test Structure

### File location

```
trn_inventory/
└── tests/
    ├── __init__.py
    └── test_stock_move.py
```

The `__init__.py` must import the test module:

```python
# tests/__init__.py
from . import test_stock_move
```

### Class and method patterns

```python
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestStockMove(TransactionCase):
    """Tests for trn.stock.move model."""

    def setUp(self):
        super().setUp()
        # Use tracking_disable to suppress mail side effects
        self.warehouse = self.env["trn.warehouse"].with_context(
            tracking_disable=True
        ).create({
            "name": "Main Warehouse",
        })

    def test_quantity_must_be_positive(self):
        """Stock move quantity must be a positive number."""
        with self.assertRaises(ValidationError):
            self.env["trn.stock.move"].create({
                "warehouse_id": self.warehouse.id,
                "quantity": -10,
            })

    def test_stock_move_linked_to_warehouse(self):
        """Creating a stock move links it to the warehouse via One2many."""
        move = self.env["trn.stock.move"].create({
            "warehouse_id": self.warehouse.id,
            "quantity": 50,
            "product_name": "Widget A",
        })
        self.assertIn(move, self.warehouse.stock_move_ids)
```

Use `TransactionCase` for all unit tests. Each test method runs in a transaction that is rolled back after the method finishes, giving you a clean slate per test.

## Coverage Targets

| Module type | Minimum coverage |
|-------------|-----------------|
| Core (`trn_vocabulary`, `trn_project`) | 85% |
| API modules | 90% |
| Utility/helper | 80% |
| UI-only | 60% |

## What to Test

### Constraints

Test that invalid data is rejected. One `assertRaises` per constraint.

```python
def test_end_date_after_start_date(self):
    """End date must not precede start date."""
    with self.assertRaises(ValidationError):
        self.env["trn.project"].create({
            "start_date": "2026-03-10",
            "end_date": "2026-03-01",
        })
```

### Computed fields

Test the output value, not the implementation.

```python
def test_total_computed_from_quantity_and_price(self):
    """Total is calculated as quantity * unit_price."""
    move = self.env["trn.stock.move"].create({
        "warehouse_id": self.warehouse.id,
        "quantity": 10,
        "unit_price": 25.50,
    })
    # 10 * 25.50 = 255.00
    self.assertAlmostEqual(move.total_value, 255.00, places=2)
```

### State machines

Test each valid and invalid transition.

```python
def test_order_can_be_confirmed_from_draft(self):
    """Draft order can be moved to confirmed."""
    self.assertEqual(self.order.state, "draft")
    self.order.action_confirm()
    self.assertEqual(self.order.state, "confirmed")

def test_order_cannot_be_confirmed_twice(self):
    """Confirming an already-confirmed order raises an error."""
    self.order.action_confirm()
    with self.assertRaises(UserError):
        self.order.action_confirm()
```

### ACLs and security

Always test with the appropriate user role, not just admin. Admin bypasses record rules, which gives you false confidence.

```python
def test_officer_can_create_stock_move(self):
    """Officers can create stock move records."""
    officer = self.env.ref("trn_vocabulary_demo.demo_officer")
    move = self.env["trn.stock.move"].with_user(officer).create({
        "warehouse_id": self.warehouse.id,
        "quantity": 50,
    })
    self.assertTrue(move.id)

def test_viewer_cannot_create_stock_move(self):
    """Viewers have read-only access — create raises AccessError."""
    from odoo.exceptions import AccessError
    viewer = self.env.ref("trn_vocabulary_demo.demo_viewer")
    with self.assertRaises(AccessError):
        self.env["trn.stock.move"].with_user(viewer).create({
            "warehouse_id": self.warehouse.id,
            "quantity": 50,
        })
```

### Demo data

If your module ships demo records, write a test that confirms they load correctly.

```python
def test_demo_stock_move_records_exist(self):
    """Demo data creates at least one stock move record."""
    moves = self.env["trn.stock.move"].search([])
    self.assertTrue(
        moves,
        "Demo data should have created at least one trn.stock.move record",
    )
```

## Odoo Testing Quirks

### `assertRaises` does not accept tuples

Odoo's test framework overrides Python's `assertRaises`. Passing a tuple of exception types raises a `TypeError`.

```python
# Wrong — will fail with TypeError at runtime
with self.assertRaises((ValidationError, UserError)):
    some_operation()

# Correct — use a single exception type
with self.assertRaises(ValidationError):
    some_operation()

# If you genuinely need to catch either, use the common base
with self.assertRaises(Exception):
    some_operation()
```

### Suppress mail/tracking side effects in setUp

Odoo's chatter and field tracking fire during `create()` and `write()`. In test setUp, suppress them to keep tests fast and output clean.

```python
def setUp(self):
    super().setUp()
    self.partner = self.env["res.partner"].with_context(
        tracking_disable=True
    ).create({"name": "Test Partner"})
```

### Approval flow test data

If you test an approval workflow, you must build the full chain — don't just set `approval_state` directly on the record.

```python
# Wrong — bypasses the state machine
self.order.write({"approval_state": "approved"})

# Correct — create the approval review records and approve through them
approval = self.env["trn.approval.review"].create({
    "definition_id": self.approval_definition.id,
    "record_ref": f"trn.order,{self.order.id}",
    "group_id": self.approver_group.id,
})
approval.with_user(self.manager).action_approve()
```

When creating an `trn.approval.definition`, always include `approval_group_id` — it is required even when `approval_type` defaults to `group`.

```python
cls.approval_definition = cls.env["trn.approval.definition"].create({
    "name": "Test Approval",
    "model_id": model_id,
    "approval_type": "group",
    "approval_group_id": cls.approver_group.id,
})
```

## Role-Based Testing Matrix

Use this as a checklist when testing any model that has access control:

| Operation | viewer | officer | manager |
|-----------|--------|---------|---------|
| Read records | allowed | allowed | allowed |
| Create record | denied | allowed | allowed |
| Edit record | denied | allowed (own) | allowed (all) |
| Delete record | denied | denied | allowed |
| Access config menus | denied | denied | allowed |

Officer-level access often uses record rules that restrict to own records or team records. Test both cases: officer sees their own record, officer cannot see another officer's record.

## Common Pitfalls

These pitfalls have caused real failures on this project.

**AccessError in tests**: When a test fails with `AccessError`, the fix is always in `ir.model.access.csv` — not in the test. Do not add `sudo()` calls to make tests pass.

**Related models missing ACLs**: If `trn.project` has an ACL entry, every related model it references (`trn.task`, `trn.note`) also needs its own ACL entries. Missing entries cause `AccessError` when loading the form view.

**Demo data ownership**: Records created by `OdooBot` (the script runner) may be invisible to human demo users because of record rules. Create demo data `with_user(demo_officer)` so that the ownership matches what record rules expect.

**Never remove or weaken tests**: If a test is inconvenient, the test is probably right. Fix the implementation, not the test. Any removal requires explicit approval.

## Deep Dives

- `docs/principles/testing.md` — coverage targets, E2E patterns, Playwright setup
- `docs/principles/odoo19-compatibility.md` — `assertRaises`, Command API, other Odoo 19 quirks
- `docs/principles/approval-workflows.md` — approval chain test data patterns
- `.claude/rules/testing.md` — auto-loaded rule summary (loaded when editing `tests/*.py`)
