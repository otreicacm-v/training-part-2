---
paths:
  - "*/tests/*.py"
---

# Testing Rules

## Coverage Targets

| Module Type         | Target |
| ------------------- | ------ |
| Core domain modules | 85%+   |
| API modules         | 90%+   |
| Utility/helper      | 80%+   |
| UI-only             | 60%+   |

## Test Structure

- Use `TransactionCase` for unit tests (rolled back per test).
- `setUp()` calls `super().setUp()` then creates test data.
- Test names: `test_{what_it_tests}` — descriptive, not generic.
- Docstrings explain the expected behavior, not the implementation.

## Rules

- **NEVER remove or weaken existing tests** without explicit approval.
- Tests must run with appropriate user context (officer, manager), not just admin.
- When fixing security issues, update test user context — don't skip tests.
- If tests can't run due to install issues, fix the install — don't mark tests as skipped.

## Odoo Testing Quirks

- `assertRaises` does NOT support tuples — use a single exception type.
- Use `with self.assertRaises(ValidationError):` not `(ValueError, UserError)`.
- Use `with_context(tracking_disable=True)` in test setUp to avoid mail side effects.

## Approval Flow Test Data

- `approval_state='pending'` requires pending approval review records.
- `approval_state='approved'` requires all reviews approved.
- Create the full approval chain — don't just set the state field directly.

## Running Tests

```bash
./scripts/test_single_module.sh <module_name>
```

## Deep-Dive References

- `docs/principles/testing.md`
- `docs/principles/odoo19-compatibility.md`
- `docs/principles/approval-workflows.md`
