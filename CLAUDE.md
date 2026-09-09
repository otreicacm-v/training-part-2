# Odoo 19 Project Development Guidelines

Odoo 19 project template. Modules use `trn_*` naming.

## Auto-Loaded Rules (`.claude/rules/`)

Path-scoped rules load automatically when you edit matching files:

| Rule              | Triggers On                   | Covers                                  |
| ----------------- | ----------------------------- | --------------------------------------- |
| `odoo-python.md`  | `models/*.py`, `wizard/*.py`  | Naming, Odoo 19 API, error handling     |
| `odoo-xml.md`     | `views/*.xml`, `data/*.xml`   | View syntax, form layout, accessibility |
| `security.md`     | `security/*`                  | ACLs, groups, record rules              |
| `testing.md`      | `tests/*.py`                  | Coverage targets, test patterns, quirks |
| `module-setup.md` | `__manifest__.py`, `readme/*` | Visibility, architecture, descriptions  |

Full principle docs remain in `docs/principles/` for deep dives.

## Documentation

| Area                | Location                                             |
| ------------------- | ---------------------------------------------------- |
| Principles          | `docs/principles/`                                   |
| Architecture & ADRs | `docs/architecture/`, `docs/architecture/decisions/` |
| Guides              | `docs/guides/`                                       |

## Architecture

### Module Layers (Dependencies flow downward)

```
Layer 3: DOMAIN EXTENSIONS (trn_reports, trn_api)
    ↓
Layer 2: DOMAIN CORE (trn_sale, trn_inventory, trn_hr)
    ↓
Layer 1: FOUNDATION (trn_security, trn_vocabulary)
    ↓
Layer 0: ODOO CORE (base, hr, stock, account, calendar)
```

### Extension Patterns

- **Inherit and Extend**: `_inherit = "res.partner"` + add fields
- **Hook Methods**: `_pre_check_in_hook()`, `_post_checkout_hook()`
- **Never expose DB IDs** in APIs — use external identifiers

## Quick Checklist

- [ ] Naming follows `trn_*` / `trn.*` conventions
- [ ] `application` and `auto_install` set correctly per [module-visibility](docs/principles/module-visibility.md)
- [ ] Country-specific modules (`trn_*_{country}`) have `excludes` for other country variants
- [ ] `ir.model.access.csv` exists and complete
- [ ] No `print()` - use `_logger`
- [ ] No bare `except:` clauses
- [ ] No `cr.commit()` in loops - use `queue_job`
- [ ] No PII in log messages
- [ ] Tests exist for core functionality

## Known Pitfalls (from recurring issues)

**Bug fixing**: write a failing test first, then fix at the source (not workarounds).

### Access Rights (Most Common Error)

- **Always check `ir.model.access.csv`** before declaring a module complete
- When tests fail with `AccessError`, fix the ACL, don't bypass with `sudo()`
- Tests must run with appropriate user context (officer, manager), not just admin
- After security changes, **always re-run affected tests** - they often break
- Related models need ACLs too (e.g., if `trn.order` has ACL, `trn.order.line` likely needs one)

### Demo Data

- Demo data must create **complete, consistent records** — check all required relations
- Use `with_context(tracking_disable=True)` to avoid sending notifications
- Test demo data generation with dedicated tests

### State Machines and Approvals

- Approval states must match approval records (e.g., `approval_state='pending'` requires pending approval review
  records)
- When creating test data for approval flows, create the full approval chain

After every correction or PR, propose updates to this Known Pitfalls section.

## Running Locally

**Quick Start:**

```bash
./odoo-project build                    # Build Docker image (first time)
./odoo-project start                    # http://localhost:8069 (admin/admin)
./odoo-project stop                     # Stop
./odoo-project stop -v -y              # Clean restart (fresh DB)
```

## Running Tests

```bash
./odoo-project test <module_name>                # Docker-based, isolated (cross-platform)
./odoo-project test <module> --tags=post_install # Filter by test tags
./odoo-project test <module> --local             # Local mode (Claude Code web only)
./scripts/setup_test_env.sh                      # Claude Code web: run once per session first
```

## Linting and Compliance

```bash
pre-commit run ruff --files <changed_files>      # Lint
pre-commit run ruff-format --files <changed_files>  # Format
pre-commit run prettier --files <changed_files>  # XML/MD/JSON format
./odoo-project audit-security                    # Security/ACL audit
./odoo-project audit-modules                     # Module structure audit (AI agent)
./odoo-project fix-lint <module>                 # Auto-fix linting (review changes!)
./odoo-project fix-security <module>             # Auto-fix security (review changes!)
./odoo-project fix-odoo19                        # Fix Odoo 19 Command API tuples
```

## Verification (before marking any task complete)

1. `./odoo-project test <module>` — run tests
2. `pre-commit run --files <changed_files>` — run linters
3. `/verify-tests` — confirm no tests were removed or weakened
4. If demo data modified: verify records created correctly
5. If UX changes: confirm correct view displays in UI

## Custom Commands

| Command          | When                | Purpose                                                 |
| ---------------- | ------------------- | ------------------------------------------------------- |
| `/implement`     | Implementing        | Full TDD workflow with subagents and expert review      |
| `/verify-tests`  | After subagent work | Check test integrity (catch removed tests)              |
| `/analyze`       | Debugging           | Deep analysis mode - understand before implementing     |
| `/expert-review` | Review              | Parallel code review from multiple perspectives         |
| `/commit`        | Before commit       | Conventional commit (feat/fix/chore/docs/refactor/test) |
| `/pr`            | After commit        | GitHub PR creation                                      |

**Starting work**: Enter Plan mode (shift+tab twice) for brainstorming.

## Subagents

| Agent              | Model  | Use For                                |
| ------------------ | ------ | -------------------------------------- |
| `@odoo-developer`  | sonnet | Core implementation work               |
| `@code-reviewer`   | opus   | Security, naming, Odoo 19 compliance   |
| `@ux-expert`       | opus   | UI/UX patterns and form layouts        |
| `@code-simplifier` | sonnet | Reduce complexity, improve readability |
| `@verify-module`   | sonnet | Test module installation and tests     |
