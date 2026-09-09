# odoo-project CLI

Developer CLI for running, testing, and managing your Odoo project locally with Docker.

## Prerequisites

Run `./odoo-project doctor` to verify your environment:

- **Docker** and **Docker Compose v2** (required)
- **Git** (optional, used by `lint`)
- **pre-commit** (optional, used by `lint`)
- **argcomplete** (optional, enables tab completion)

## Quick Start

```bash
# 1. Check prerequisites
./odoo-project doctor

# 2. Build the Docker image
./odoo-project build

# 3. Start Odoo
./odoo-project start

# 4. Open http://localhost:8069 (admin / admin)

# 5. Run tests
./odoo-project test trn_vocabulary

# 6. Stop everything
./odoo-project stop
```

### init — Initialize from template

Replaces the `tpl` placeholder prefix and `Training Sample` name throughout the codebase, then renames `trn_*` directories to match your project.

```bash
./odoo-project init eh EHealth             # replace trn -> eh, Training Sample -> EHealth
./odoo-project init --dry-run eh EHealth   # preview changes without modifying files
./odoo-project init myapp "My App"         # any lowercase prefix works
```

| Option          | Description                                      |
|-----------------|--------------------------------------------------|
| `prefix`        | Your project prefix (lowercase, e.g., `eh`)      |
| `project_name`  | Your project display name (e.g., `EHealth`)       |
| `--dry-run, -n` | Show what would change without modifying files    |

What gets replaced:

| Pattern      | Example                              |
|--------------|--------------------------------------|
| `trn_` → `{prefix}_` | `trn_vocabulary` → `eh_vocabulary` |
| `trn.` → `{prefix}.` | `trn.vocabulary` → `eh.vocabulary` |
| `trn/` → `{prefix}/` | `trn/Core` → `eh/Core`            |
| `trn ` → `{prefix} ` | `trn Vocabulary` → `eh Vocabulary` |
| `Training Sample` → name   | `Training Sample` → `EHealth`           |

Binary files and `.git/` are always skipped.

## Commands

Every command has a short alias shown in parentheses.

### test (t) — Run module tests

Runs tests in an isolated container that does not affect your running dev instance.

```bash
./odoo-project test trn_vocabulary
./odoo-project t trn_vocabulary                     # alias
./odoo-project test trn_vocabulary --tags=post_install
./odoo-project test trn_vocabulary --local           # force local mode (no Docker)
./odoo-project test trn_vocabulary --docker           # force Docker mode
```

| Option     | Description                        |
|------------|------------------------------------|
| `--tags`   | Test tags filter (e.g. `post_install`) |
| `--local`  | Force local mode (uses local venv) |
| `--docker` | Force Docker mode                  |

### start (s) — Start Odoo

Starts the Odoo development server. Defaults to the **ui** profile on port 8069.

```bash
./odoo-project start                     # default: ui profile, port 8069
./odoo-project s                         # alias
./odoo-project start --profile dev       # dynamic port, auto-reload enabled
./odoo-project start --demo=base         # install base demo data on start
./odoo-project start --wipe              # wipe all data first (fresh DB)
./odoo-project start --wipe --demo=base  # fresh start with demo data
./odoo-project start --no-build          # skip Docker image freshness check
./odoo-project start -y                  # auto-confirm prompts (rebuild, etc.)
```

| Option        | Description                                              |
|---------------|----------------------------------------------------------|
| `--profile`   | `ui` (fixed port 8069, default) or `dev` (dynamic port) |
| `--demo`      | Demo data profile to install (see [Demo Profiles](#demo-profiles)) |
| `--wipe`      | Delete all data (database + filestore) before starting   |
| `--no-watch`  | Disable auto-reload (dev profile enables it by default)  |
| `--no-build`  | Skip Docker image freshness check                        |
| `-y, --yes`   | Skip confirmation prompts                                |

### stop — Stop all services

Stops all Docker containers across all profiles.

```bash
./odoo-project stop
./odoo-project stop -v           # also remove volumes (deletes DB data)
./odoo-project stop -y           # skip confirmation prompt
./odoo-project stop -v -y        # remove volumes without confirmation
```

| Option        | Description                       |
|---------------|-----------------------------------|
| `-v, --volumes` | Also remove Docker volumes (destructive) |
| `-y, --yes`     | Skip confirmation prompt           |

### restart (r) — Restart Odoo

Auto-detects which profile is running and restarts the Odoo container.

```bash
./odoo-project restart
./odoo-project r                 # alias
```

### resetdb — Reset database

Drops and recreates the database. Use with `start` to initialize with modules.

```bash
./odoo-project resetdb -y                          # reset with defaults
./odoo-project resetdb --demo=base -y              # reset with demo profile
./odoo-project resetdb --db=mydb -y                # reset a named database
./odoo-project resetdb --demo=base start           # reset then start (chained)
```

| Option     | Description                                            |
|------------|--------------------------------------------------------|
| `--demo`   | Demo profile to install after reset                    |
| `--db`     | Database name (default: `odoo`)                        |
| `-y, --yes` | Skip confirmation prompt                             |

### update (u) — Update modules

Uses `click-odoo-update` to auto-detect changed modules based on file checksums.

```bash
./odoo-project update
./odoo-project u                      # alias
./odoo-project update --db=mydb       # target a specific database
```

| Option | Description                     |
|--------|---------------------------------|
| `--db` | Database name (default: `odoo`) |

### build (b) — Build Docker images

Builds the Docker image for the specified profile.

```bash
./odoo-project build
./odoo-project b                      # alias
./odoo-project build --no-cache       # full rebuild without cache
./odoo-project build --profile dev    # build dev profile image
```

| Option       | Description                       |
|--------------|-----------------------------------|
| `--profile`  | `ui` (default) or `dev`           |
| `--no-cache` | Build without using Docker cache  |

### logs (l) — View logs

Shows container logs. Auto-detects the running Odoo service.

```bash
./odoo-project logs
./odoo-project l                      # alias
./odoo-project logs -f                # follow (stream) logs
./odoo-project logs --tail 50         # last 50 lines
./odoo-project logs db                # show database logs
```

| Option        | Description                        |
|---------------|------------------------------------|
| `-f, --follow` | Stream logs in real time          |
| `--tail`       | Number of lines (default: 100)   |
| `service`      | Service name (`db`, `odoo-app`, etc.) |

### shell (sh) — Open Odoo shell

Opens an interactive Odoo Python shell connected to the running instance.

```bash
./odoo-project shell
./odoo-project sh                     # alias
./odoo-project shell --db             # open PostgreSQL shell instead
./odoo-project shell -d mydb          # connect to a specific database
```

| Option          | Description                              |
|-----------------|------------------------------------------|
| `--db`          | Open PostgreSQL shell instead of Odoo shell |
| `-d, --database` | Database name (default: `odoo`)         |

### sql — Run SQL queries

Opens an interactive PostgreSQL shell or executes a query directly.

```bash
./odoo-project sql                                           # interactive psql
./odoo-project sql "SELECT name FROM trn_vocabulary"         # run a query
./odoo-project sql -f scripts/report.sql                     # run SQL from file
./odoo-project sql -d mydb "SELECT 1"                        # target specific DB
```

| Option          | Description                     |
|-----------------|---------------------------------|
| `query`         | SQL query to execute (optional) |
| `-d, --database` | Database name (default: `odoo`) |
| `-f, --file`    | SQL file to execute             |

### url — Show server URL

Displays the URL of the running Odoo instance.

```bash
./odoo-project url
./odoo-project url --open             # open in default browser
```

| Option      | Description             |
|-------------|-------------------------|
| `-o, --open` | Open URL in browser    |

### lint — Run linters

Runs `ruff`, `ruff-format`, and `prettier` via pre-commit on specified files.

```bash
./odoo-project lint                                   # lint changed files (git diff)
./odoo-project lint trn_vocabulary/models/*.py        # lint specific files
```

| Option  | Description                                      |
|---------|--------------------------------------------------|
| `files` | Files to lint (default: git changed files)       |

### status (st) — Show service status

Shows running Docker containers.

```bash
./odoo-project status
./odoo-project st                     # alias
```

### doctor — Check prerequisites

Verifies that all required and optional tools are installed.

```bash
./odoo-project doctor
```

Checks: Docker, Docker Compose, Docker daemon, Git, pre-commit, argcomplete, config file, port 8069.

### activate — Enable tab completion

Outputs a shell script that enables tab completion for commands and module names.

```bash
# Add to your shell profile (~/.zshrc or ~/.bashrc)
eval "$(./odoo-project activate)"
```

Requires `argcomplete` (`pip install argcomplete`).

### fix-odoo19 — Fix Odoo 19 compatibility

Applies automatic fixes for Odoo 19 Command API tuples in Python files.

```bash
./odoo-project fix-odoo19                        # fix all modules
./odoo-project fix-odoo19 trn_vocabulary          # fix specific module
./odoo-project fix-odoo19 --dry-run               # preview changes
```

| Option          | Description                                    |
|-----------------|------------------------------------------------|
| `modules`       | Modules to fix (default: all)                  |
| `--dry-run, -n` | Preview changes without applying               |

### fix-lint — Fix linting issues

Runs ruff, pylint, and prettier across module files and optionally invokes an AI agent for remaining issues.

```bash
./odoo-project fix-lint trn_vocabulary            # fix specific module
./odoo-project fix-lint                           # fix all modules
./odoo-project fix-lint trn_vocabulary --lint-only # linters only, no AI
```

| Option        | Description                                      |
|---------------|--------------------------------------------------|
| `modules`     | Modules to fix (default: all)                    |
| `--lint-only` | Only run linters, skip AI fixing                 |

### fix-security — Fix security compliance

Applies mechanical fixes for Odoo 19 security issues (tuple syntax, field renames) and optionally invokes an AI agent for complex issues.

```bash
./odoo-project fix-security trn_vocabulary        # fix specific module
./odoo-project fix-security --all                 # fix all modules with issues
./odoo-project fix-security --dry-run trn_api     # preview changes
./odoo-project fix-security --mechanical-only trn_api  # no AI
```

| Option              | Description                                      |
|---------------------|--------------------------------------------------|
| `modules`           | Modules to fix                                   |
| `--all`             | Fix all modules with issues                      |
| `--dry-run, -n`     | Show what would be fixed                         |
| `--mechanical-only` | Only apply mechanical fixes (no AI agent)        |

### audit-security — Audit security compliance

Audits modules for access rights compliance using the Python security audit script.

```bash
./odoo-project audit-security                     # audit all modules
./odoo-project audit-security trn_vocabulary      # audit specific module
./odoo-project audit-security --report            # generate markdown report
./odoo-project audit-security --json              # output as JSON
```

| Option     | Description                          |
|------------|--------------------------------------|
| `modules`  | Modules to audit (default: all)      |
| `--report` | Generate markdown report             |
| `--json`   | Output as JSON                       |

### audit-modules — Audit module compliance

Audits modules against project principles using an AI agent (requires `cursor-agent` or `claude`).

```bash
./odoo-project audit-modules                      # audit all modules
./odoo-project audit-modules trn_vocabulary       # audit specific module
./odoo-project audit-modules --fix                # auto-fix simple issues
./odoo-project audit-modules --fix --commit       # fix and commit
```

| Option    | Description                                    |
|-----------|------------------------------------------------|
| `modules` | Modules to audit (default: all)                |
| `--fix`   | Auto-fix clear, mechanical issues              |
| `--commit` | Auto-commit fixes after each module           |
| `--model` | AI model to use (default: `composer-1`)        |

## Demo Profiles

Demo profiles are predefined sets of modules to install:

| Profile | Modules Installed  |
|---------|--------------------|
| `base`  | `trn_vocabulary`   |

Use with `start` or `resetdb`:

```bash
./odoo-project start --demo=base
./odoo-project resetdb --demo=base -y
```

## Command Chaining

Commands can be chained in a single invocation. Options apply to the preceding command.

```bash
./odoo-project resetdb --demo=base start         # reset DB, then start
./odoo-project stop start --wipe                  # stop, then wipe and start
./odoo-project resetdb --demo=base start --wipe   # reset, then wipe and start
```

## Dry Run Mode

Add `--dry-run` (or `-n`) to see what commands would be executed without running them.

```bash
./odoo-project --dry-run start
./odoo-project -n stop -v
```

## Configuration

Defaults can be customized via `~/.odoo-project.toml`:

```toml
default_demo = "base"       # auto-install demo on start
default_profile = "ui"      # "ui" or "dev"
default_db = "odoo"          # database name
```

Create the file:

```bash
echo 'default_profile = "ui"' > ~/.odoo-project.toml
```

## Common Workflows

### Fresh start with demo data

```bash
./odoo-project start --wipe --demo=base -y
```

### Daily development

```bash
./odoo-project start                # start Odoo
# ... make code changes ...
./odoo-project update               # auto-detect and upgrade changed modules
./odoo-project test trn_vocabulary   # run tests
./odoo-project lint                  # lint changed files
```

### Debugging a module

```bash
./odoo-project start
./odoo-project shell                 # open Odoo shell
>>> env['trn.vocabulary'].search([])

./odoo-project sql "SELECT * FROM trn_vocabulary"
./odoo-project logs -f               # watch logs in real time
```

### Quick test cycle

```bash
./odoo-project test trn_vocabulary
./odoo-project test trn_vocabulary --tags=post_install
```

### Complete reset

```bash
./odoo-project stop -v -y            # stop and delete all data
./odoo-project build --no-cache      # full rebuild
./odoo-project start --demo=base     # fresh start with demo
```

## Troubleshooting

### Port 8069 already in use

```bash
./odoo-project doctor                # will show port status
./odoo-project stop                  # stop any running containers
```

### Docker image seems stale

The CLI auto-detects when `Dockerfile` or `requirements.txt` change and prompts to rebuild. To force:

```bash
./odoo-project build --no-cache
```

### Tests fail but dev instance works

Tests run in an isolated container with a temporary database. Check:

```bash
./odoo-project test trn_vocabulary   # re-run tests
./odoo-project logs                  # check logs for errors
```

### Module not updating after code changes

```bash
./odoo-project update                # auto-detect and upgrade changed modules
./odoo-project restart               # restart if update doesn't pick up changes
```

### Database connection issues

```bash
./odoo-project doctor                # check Docker daemon is running
./odoo-project status                # check container states
./odoo-project logs db               # check database logs
```
