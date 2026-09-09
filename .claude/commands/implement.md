Execute a full implementation based on the plan discussed above. Work autonomously until complete.

## Prime Directive

**COMPLETE IMPLEMENTATION ONLY** - No stubs, no placeholders, no "TODO" comments, no "implement later". Every function
must be fully working. Every test must be real. Every feature must be verified.

If you cannot complete something, STOP and explain why - do not leave partial work.

## Phase 1: Analyze & Organize

Review the plan from our conversation above. Break the work into:

1. **Parallel tasks** - Independent work that can be done simultaneously
2. **Sequential tasks** - Work that depends on previous steps
3. **Verification points** - Where to test before proceeding

```
Example structure:
├── PARALLEL: Create models (trn_feature/models/)
├── PARALLEL: Create security (ir.model.access.csv, groups)
├── PARALLEL: Create views (form, list, menu)
├── SEQUENTIAL: Create business logic (depends on models)
├── SEQUENTIAL: Create tests (depends on logic)
├── VERIFY: Install module, run tests
├── SEQUENTIAL: Fix any issues found
└── VERIFY: Final verification
```

## Phase 2: Implement with Subagents

For complex features, delegate to specialized subagents:

- **@odoo-developer** - Core implementation work
- **@ux-expert** - Form/view design (for UI work)

Launch parallel work simultaneously when tasks are independent.

### Implementation Standards

Follow @docs/principles/:

- Naming: `trn_*` modules, `trn.*` models, `is_*` booleans
- Security: Always create `ir.model.access.csv`
- Odoo 19: Use `Command.create()`, `hasclass()` in XPath
- No print(), no bare except:, no cr.commit() in loops
- Tests: Write real tests, not stubs

## Phase 3: Self-Verify

After implementation, run verification:

```bash
# Lint check
pre-commit run --all-files

# Install and test
./scripts/test_single_module.sh <module_name>
```

**If tests fail**: Fix the issues immediately. Do not proceed until green.

## Phase 4: Simplify

Invoke @code-simplifier to review and clean up the implementation:

- Remove unnecessary complexity
- Improve readability
- Eliminate duplication

## Phase 5: Expert Review

Run parallel expert reviews:

1. **@code-reviewer** - Security, naming, Odoo 19 compatibility
2. **@ux-expert** - UI/UX patterns (if views were created)
3. **@verify-module** - Final end-to-end verification

Address any Critical or Important issues found.

## Phase 6: Final Verification

```bash
# Final test run
./scripts/test_single_module.sh <module_name>

# Verify clean status
git status
git diff --stat
```

## Completion Criteria

Before reporting done, confirm:

- [ ] All planned features implemented (no stubs)
- [ ] All tests pass
- [ ] Linting passes
- [ ] Module installs without errors
- [ ] Expert reviews addressed
- [ ] Code is clean and readable

## Progress Updates

Every 15-20 minutes of work, provide a brief status:

- What's completed
- What's in progress
- Any blockers

## If Blocked

If you encounter a blocker you cannot resolve:

1. Document what you tried
2. Explain the specific issue
3. Suggest alternatives
4. Ask for guidance

Do NOT leave work in a broken state. Either complete it or roll back.

---

**START NOW**: Review the plan above and begin Phase 1.
