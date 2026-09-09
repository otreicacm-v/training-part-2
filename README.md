# Odoo 19 Project Template

A batteries-included template for building Odoo 19 projects with consistent module structure, a developer CLI, and Claude Code integration.

## Using This Template

1. **Create a new repository** from this template — click **"Use this template"** on GitHub, or download a ZIP and extract into a fresh repo
2. **Initialize your project**: `./odoo-project init <prefix> <name>` (e.g., `./odoo-project init eh EHealth`)
3. **Verify your environment**: `./odoo-project doctor`
4. **Build and start**: `./odoo-project build && ./odoo-project start`
5. **Open** http://localhost:8069 (admin / admin)

<details>
<summary>What does <code>init</code> replace?</summary>

| Placeholder  | Where                                  | Replace With         | Example              |
| ------------ | -------------------------------------- | -------------------- | -------------------- |
| `tpl`        | Module names, model names, code        | Your project prefix  | `eh`, `myapp`        |
| `Training Sample`  | Documentation, manifest categories     | Your project name    | `EHealth`, `MyApp`   |

Use `--dry-run` to preview: `./odoo-project init --dry-run eh EHealth`

</details>

## Prerequisites

- **Docker** and **Docker Compose v2** (required)
- **Git** (required)
- **Python 3.11+** (required — the CLI is a Python script)
- **pre-commit** (recommended — used by `./odoo-project lint`)
- **Claude Code** (recommended — AI-assisted development)
- **argcomplete** (optional — enables tab completion for the CLI)

Run `./odoo-project doctor` to check all of these at once.

> **Windows users:** Use `python odoo-project <command>` instead of `./odoo-project <command>`, or run from Git Bash / WSL where `./` syntax works.

## The `odoo-project` CLI

A single entry point for running, testing, and managing your Odoo project locally with Docker.

### Quick Start

```bash
./odoo-project doctor                    # check prerequisites
./odoo-project build                     # build Docker image
./odoo-project start                     # start Odoo at http://localhost:8069
./odoo-project test trn_vocabulary       # run tests
./odoo-project stop                      # stop all services
```

### Command Reference

Every command has a short alias shown in parentheses.

| Command          | Alias | Description                                         |
| ---------------- | ----- | --------------------------------------------------- |
| `test`           | `t`   | Run module tests in an isolated container            |
| `start`          | `s`   | Start Odoo (default: ui profile, port 8069)          |
| `stop`           |       | Stop all Docker containers across all profiles       |
| `restart`        | `r`   | Restart the running Odoo container                   |
| `resetdb`        |       | Drop and recreate the database                       |
| `update`         | `u`   | Auto-detect and upgrade changed modules              |
| `build`          | `b`   | Build the Docker image                               |
| `logs`           | `l`   | View container logs                                  |
| `shell`          | `sh`  | Open an interactive Odoo Python shell                |
| `sql`            |       | Run SQL queries or open interactive psql             |
| `url`            |       | Show the running Odoo instance URL                   |
| `lint`           |       | Run ruff, ruff-format, and prettier via pre-commit   |
| `status`         | `st`  | Show running Docker containers                       |
| `doctor`         |       | Verify prerequisites and environment health          |
| `init`           |       | Initialize from template (replace `tpl` prefix)      |
| `activate`       |       | Output shell script for tab completion               |
| `fix-odoo19`     |       | Fix Odoo 19 Command API compatibility                |
| `fix-lint`       |       | Fix linting issues (ruff, pylint, prettier)          |
| `fix-security`   |       | Fix security compliance issues                       |
| `audit-security` |       | Audit modules for security compliance                |
| `audit-modules`  |       | Audit module compliance (AI agent)                   |

### Common Workflows

**First time setup:**

```bash
./odoo-project doctor
./odoo-project build
./odoo-project start --demo=base
```

**Daily development:**

```bash
./odoo-project start
# ... make code changes ...
./odoo-project update                    # auto-detect changed modules
./odoo-project test trn_vocabulary       # run tests
./odoo-project lint                      # lint changed files
```

**Fresh restart (wipe everything):**

```bash
./odoo-project stop -v -y               # stop and delete all data
./odoo-project build --no-cache          # full rebuild
./odoo-project start --demo=base        # fresh start with demo
```

**Before a PR:**

```bash
./odoo-project test trn_vocabulary
./odoo-project lint
```

### Configuration

Defaults can be customized via `~/.odoo-project.toml`:

```toml
default_demo = "base"       # auto-install demo on start
default_profile = "ui"      # "ui" or "dev"
default_db = "odoo"          # database name
```

See the full [CLI Guide](docs/guides/odoo-project-cli.md) for all options, command chaining, dry-run mode, and troubleshooting.

## Working with Claude Code

This project is configured for Claude Code with project-level instructions, path-scoped rules, and specialized subagents.

### Setting Up Your Repo

1. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. Run `claude` from the project root — it automatically loads `CLAUDE.md` and path-scoped rules
3. Customize personal permissions in `.claude/settings.local.json` (gitignored)

### Daily Development Workflow

1. **Start with Plan mode** (shift+tab twice) for non-trivial features
2. **Use `/implement`** for TDD workflow with subagents
3. **Use `/verify-tests`** after subagent work to catch removed tests
4. **Use `/commit`** for conventional commit format
5. **Use `/pr`** for GitHub PR creation

### Commands

| Command          | Purpose                                                 |
| ---------------- | ------------------------------------------------------- |
| `/implement`     | Full TDD workflow with subagents and expert review      |
| `/verify-tests`  | Check test integrity after subagent work                |
| `/analyze`       | Deep analysis mode — understand before implementing     |
| `/expert-review` | Parallel code review from multiple perspectives         |
| `/commit`        | Conventional commit (feat/fix/chore/docs/refactor/test) |
| `/pr`            | GitHub PR creation                                      |

### Subagents

| Agent              | Best For                               |
| ------------------ | -------------------------------------- |
| `@odoo-developer`  | Core implementation (models, views, security) |
| `@code-reviewer`   | Security, naming, Odoo 19 compliance   |
| `@ux-expert`       | UI/UX patterns and form layouts        |
| `@code-simplifier` | Reduce complexity after implementation |
| `@verify-module`   | Test module installation and tests     |

### What Loads Automatically

| Editing                            | Rule Loaded       | Covers                                  |
| ---------------------------------- | ----------------- | --------------------------------------- |
| `models/*.py`, `wizard/*.py`       | `odoo-python.md`  | Naming, Odoo 19 API, error handling     |
| `views/*.xml`, `data/*.xml`        | `odoo-xml.md`     | View syntax, form layout, accessibility |
| `security/*`                       | `security.md`     | ACLs, groups, record rules              |
| `tests/*.py`                       | `testing.md`      | Coverage targets, test patterns, quirks |
| `__manifest__.py`, `readme/*`      | `module-setup.md` | Visibility, architecture, descriptions  |

See [Claude Code for Developers](docs/guides/claude-code-for-developers.md) for the full guide.

## Project Structure

```
├── docker/                  # Docker configuration (dev + production)
├── docs/
│   ├── architecture/        # Architecture vision and ADRs
│   │   └── decisions/       # Architecture Decision Records
│   ├── guides/              # Developer guides (CLI, testing, modules)
│   ├── principles/          # Development standards (naming, security, UI)
│   └── security/            # Security scanning documentation
├── scripts/                 # CI/CD, linting, compliance, and test scripts
│   ├── compliance/          # Module structure auditing
│   ├── lint/                # Linting and formatting checks
│   └── zap/                 # OWASP ZAP security scanning
├── tests/                   # Cross-module integration tests
├── tools/                   # Developer tooling and utilities
├── trn_vocabulary/          # Example module (rename trn_ to your prefix)
├── .claude/                 # Claude Code configuration and rules
├── .github/                 # GitHub Actions workflows and templates
├── CLAUDE.md                # Claude Code project instructions
├── CONTRIBUTING.md          # Contribution guidelines
└── odoo-project             # Developer CLI entry point
```

## Architecture

Dependencies flow downward — higher layers depend on lower ones, never the reverse.

```
Layer 3: DOMAIN EXTENSIONS (trn_reports, trn_api)
    ↓
Layer 2: DOMAIN CORE (trn_sale, trn_inventory, trn_hr)
    ↓
Layer 1: FOUNDATION (trn_security, trn_vocabulary)
    ↓
Layer 0: ODOO CORE (base, hr, stock, account, calendar)
```

See [Architecture Vision](docs/architecture/vision.md) and [Integration Patterns](docs/architecture/integration-patterns.md) for details.

## Documentation Map

| Area                     | Location                                                                         |
| ------------------------ | -------------------------------------------------------------------------------- |
| Architecture vision      | [docs/architecture/vision.md](docs/architecture/vision.md)                       |
| Integration patterns     | [docs/architecture/integration-patterns.md](docs/architecture/integration-patterns.md) |
| Architecture decisions   | [docs/architecture/decisions/](docs/architecture/decisions/)                     |
| Development principles   | [docs/principles/](docs/principles/)                                             |
| CLI guide                | [docs/guides/odoo-project-cli.md](docs/guides/odoo-project-cli.md)              |
| Module development guide | [docs/guides/module-development.md](docs/guides/module-development.md)          |
| Testing guide            | [docs/guides/testing-guide.md](docs/guides/testing-guide.md)                    |
| Claude Code guide        | [docs/guides/claude-code-for-developers.md](docs/guides/claude-code-for-developers.md) |
| Security audit guide     | [docs/guides/security-audit-guide.md](docs/guides/security-audit-guide.md)      |
| Docker setup             | [docker/README.md](docker/README.md)                                             |
| Scripts reference        | [scripts/README.md](scripts/README.md)                                           |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting changes, commit conventions, and the review process.
