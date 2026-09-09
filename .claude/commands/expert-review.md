Request expert review of recent changes from multiple perspectives.

## Context

Reference @docs/principles/ for standards.

## Review Process

Launch these reviewers in parallel:

### 1. Code Reviewer (@code-reviewer)

- Security and access control
- Naming conventions (`trn_*`, `trn.*`, `is_*`)
- Odoo 19 compatibility (Command API, hasclass())
- Code quality (no print(), proper exceptions, logging)

### 2. UX Expert (@ux-expert)

For UI/view changes:

- Form layout patterns (minimal header, content in tabs)
- Multi-column layouts (nested groups)
- Extension points (named groups/divs for injection)

### 3. Verify Module (@verify-module)

- Run tests and confirm they pass
- Check module installs cleanly
- Scan for anti-patterns

## Output Format

```markdown
## Expert Review Summary

### Critical Issues (Must Fix)

- **[Reviewer]** [file:line]: Issue → Fix

### Important Issues (Should Fix)

- **[Reviewer]** [file:line]: Issue → Recommendation

### Suggestions

- **[Reviewer]** [file:line]: Improvement idea

### Verification

| Check              | Status | Notes |
| ------------------ | ------ | ----- |
| Naming conventions | PASS   |       |
| Security/ACL       | PASS   |       |
| Odoo 19 compat     | PASS   |       |
| Tests pass         | PASS   |       |
| UI patterns        | N/A    |       |
```
