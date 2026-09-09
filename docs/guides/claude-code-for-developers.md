# Claude Code for Developers

How Claude Code is configured for this project and how to get the most out of it.

## What Claude Sees Automatically

### Always loaded (every conversation)

- **`CLAUDE.md`** — project overview, architecture, checklist, commands, pitfalls
- **Auto-memory** — persistent notes about patterns discovered across sessions

### Loaded when you edit matching files (`.claude/rules/`)

| Editing | Rule loaded | What it covers |
|---------|-------------|----------------|
| `models/*.py`, `wizard/*.py` | `odoo-python.md` | Naming, Command API, error handling, logging |
| `views/*.xml`, `data/*.xml` | `odoo-xml.md` | Odoo 19 view syntax, form layout, accessibility |
| `security/*` | `security.md` | ACLs, groups, record rules, anti-patterns |
| `tests/*.py` | `testing.md` | Coverage targets, Odoo test quirks, approval flows |
| `trn_*/*` domain modules | Domain-specific rules | Domain-specific patterns and constraints |
| `__manifest__.py`, `readme/*` | `module-setup.md` | Module visibility, architecture, descriptions |

### NOT loaded automatically (read on demand)

- **`docs/principles/`** — Deep-dive principle files. Claude reads these when it needs detail beyond what the rules provide.
- **`docs/architecture/`** — Architecture vision, module integration patterns, ADRs.

## Recommended Workflow

1. **Start with Plan mode** (shift+tab twice) for non-trivial features
2. **Use `/implement`** for TDD workflow with subagents
3. **Use `/verify-tests`** after subagent work to catch removed tests
4. **Use `/commit`** for conventional commit format
5. **Use `/pr`** for GitHub PR creation

## Available Subagents

| Agent | Best for |
|-------|----------|
| `@odoo-developer` | Core implementation (models, views, security) |
| `@code-reviewer` | Security, naming, Odoo 19 compliance review |
| `@ux-expert` | UI/UX patterns, form layouts |
| `@code-simplifier` | Reducing complexity after implementation |
| `@verify-module` | Testing module installation and tests |

## Personal Setup

### `settings.local.json` (not committed)

Personal permissions and preferences go in `.claude/settings.local.json`. This file is gitignored
so each developer can customize without affecting others.

```json
{
  "permissions": {
    "allow": [
      "Bash(ls:*)",
      "WebSearch"
    ]
  }
}
```

### `settings.json` (committed, team-shared)

Team-wide permissions for project scripts are in `.claude/settings.json`. These apply to everyone.

## Tips

- If Claude isn't following a principle, ask it to read the specific file: "Read `docs/principles/access-rights.md`"
- The rules are concise summaries — for full rationale and examples, point Claude to the source principle doc
- After discovering a recurring mistake, propose an update to the relevant rule or Known Pitfalls in CLAUDE.md
