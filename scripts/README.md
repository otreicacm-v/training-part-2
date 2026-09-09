# Odoo 19 Testing Scripts

This directory contains scripts for setting up and testing Odoo 19 modules.

## Quick Start for Claude Code on the Web

For [Claude Code on the web](https://claude.ai/code), the test environment is automatically set up via SessionStart
hook. The hook runs `scripts/setup_test_env.sh` which:

1. **Tries pre-built cache first** - Downloads ~350MB bundle (~30 seconds)
2. **Falls back to manual setup** - If cache unavailable (~2 minutes with uv)
3. **Skips if already ready** - Uses marker file check (<1 second)

**No manual setup needed!** Just run tests:

```bash
./odoo-project test trn_vocabulary
```

### Setup Performance

| Scenario          | Time   | Description                      |
| ----------------- | ------ | -------------------------------- |
| Cache download    | ~30s   | Pre-built bundle from GitHub     |
| Manual setup (uv) | ~2 min | Download Odoo + install packages |
| Already cached    | <1s    | Environment already exists       |

### Options

```bash
# Default: try cache first, fall back to manual
./scripts/setup_test_env.sh

# Force complete rebuild (ignores existing environment)
./scripts/setup_test_env.sh --force

# Skip cache, build from scratch
./scripts/setup_test_env.sh --no-cache

# Only refresh module symlinks (very fast)
./scripts/setup_test_env.sh --links-only
```

### Custom Cache URL

Override the default cache URL with environment variable:

```bash
export PROJECT_VENV_CACHE_URL="https://your-server.com/cache.tar.gz"
./scripts/setup_test_env.sh
```

### Building Cache Bundles

To build a cache bundle for your team:

```bash
./scripts/build_env_cache.sh build  # Creates /tmp/odoo19-env-v1.0.0.tar.gz (~350MB)
# Upload to GitHub Release, Google Drive, or any HTTP server
```

## Scripts

### Security & Compliance

#### `security_report.py`

Generates comprehensive visualizations and reports of the Odoo security model (groups, permissions, record rules).

**What it does:**

- Visualizes group hierarchy (inheritance via implied_ids)
- Generates permission matrix (groups × models)
- Shows user effective permissions
- Lists record rules with domains
- Exports to multiple formats: Text, HTML, CSV, Mermaid

**Usage (in Odoo shell):**

```bash
# Start Odoo shell
odoo shell -d mydb

# Load the script
>>> exec(open('scripts/security_report.py').read())

# Create report instance
>>> report = SecurityReport(env)

# Print ASCII hierarchy tree
>>> report.print_hierarchy()
>>> report.print_hierarchy(filter_prefix='tpl')

# Print permission matrix
>>> report.print_matrix()
>>> report.print_matrix(filter_groups=['vocabulary'], filter_models=['trn.vocabulary'])

# Check user permissions
>>> report.print_user_permissions('admin')

# Generate HTML report (interactive, filterable)
>>> report.generate_html('security_report.html')

# Generate CSV matrix for spreadsheet analysis
>>> report.generate_csv('permissions_matrix.csv')

# Generate Mermaid diagram for documentation
>>> report.generate_mermaid()
>>> report.generate_mermaid(filter_prefix='tpl', filename='security_diagram.md')

# Print record rules
>>> report.print_record_rules(filter_models=['trn.vocabulary'])
```

**Output formats:**

1. **Text/ASCII** - Terminal-friendly hierarchy trees and tables
2. **HTML** - Interactive report with filtering, search, collapsible sections
3. **CSV** - Permission matrix for Excel/Google Sheets analysis
4. **Mermaid** - Diagrams for documentation (renders on GitHub)

**HTML Report Features:**

- Collapsible group hierarchy tree
- Filterable permission matrix (by group or model)
- Searchable record rules
- Color-coded permissions (green=read, yellow=write, red=delete)
- Export to CSV directly from browser

**Use cases:**

- Security audits and compliance checks
- Documenting access control architecture
- Debugging permission issues
- Onboarding new developers
- Generating security documentation

**Duration:** < 1 minute to generate all reports

---

#### `security_audit.py`

Static analysis script that audits Odoo modules for compliance with ADR-004 security architecture.

**Usage:**

```bash
# Audit single module
python scripts/security_audit.py trn_vocabulary

# Audit all modules
python scripts/security_audit.py --all

# Generate detailed report
python scripts/security_audit.py --report > audit_report.md
```

See file header for detailed usage.

---

### Testing & Environment Setup

### 0. `setup_test_env.sh` (Recommended for Claude Code)

Optimized environment setup script designed for ephemeral environments like Claude Code on the web.

**Key optimizations:**

- **Cache-first**: Tries pre-built bundle download (~30s) before manual setup
- **Uses uv**: 10-100x faster than pip for package installation (fallback)
- **Smart caching**: Skips setup entirely if environment already exists
- **Marker file**: Uses `/tmp/.odoo_env_ready` to track setup state

**Usage:**

```bash
# Smart setup - tries cache first (automatic on Claude Code session start)
./scripts/setup_test_env.sh

# Force complete rebuild
./scripts/setup_test_env.sh --force

# Skip cache, build from scratch
./scripts/setup_test_env.sh --no-cache

# Only refresh module symlinks (very fast)
./scripts/setup_test_env.sh --links-only
```

**Performance:**

| Scenario          | Time   | Notes                              |
| ----------------- | ------ | ---------------------------------- |
| Pre-built cache   | ~30s   | Downloads 350MB bundle             |
| Manual setup (uv) | ~2 min | Downloads Odoo + installs packages |
| Already ready     | <1s    | Marker file exists                 |
| Links-only        | <1s    | Just refreshes symlinks            |

**Duration:** <1 second (cached) to 30 seconds (cache download) to 2 minutes (manual setup)

---

### 1. `setup_odoo19_environment.sh`

Sets up a complete Odoo 19 testing environment with all dependencies.

**What it does:**

- Configures PostgreSQL for Odoo 19
- Creates Python 3.10 virtual environment
- Downloads Odoo 19.0 from GitHub
- Installs all Python dependencies
- Links all custom modules from current branch
- Creates Odoo configuration file
- Verifies the environment

**Usage:**

```bash
# Full setup (rebuilds everything)
sudo ./setup_odoo19_environment.sh

# Fast mode (reuses existing downloads/venv)
sudo ./setup_odoo19_environment.sh --fast
```

**Fast mode optimizations:**

- **Uses uv** when available (10-100x faster than pip)
- Reuses existing Python virtualenv if valid
- Reuses existing Odoo 19 download if valid
- Uses cached zip file if available
- Uses `requirements-odoo19.txt` for faster dependency resolution

**Expected output:**

- Environment ready for Odoo 19 testing
- Custom modules at version 19.0.x
- PostgreSQL configured
- Virtual environment with Odoo 19 dependencies

**Duration:** 5-10 minutes

### 2. `test_odoo19_modules.sh`

Tests Odoo module installation and compatibility with Odoo 19.

**What it does:**

- Verifies Odoo 19 environment setup
- Checks module versions (should be 19.0.x)
- Tests for Odoo 19 breaking changes
- Installs modules in a test database
- Runs module tests
- Generates compatibility report

**Usage:**

Check environment:

```bash
./test_odoo19_modules.sh check
```

Install all modules:

```bash
./test_odoo19_modules.sh install-all
```

Install specific module:

```bash
./test_odoo19_modules.sh install trn_vocabulary
```

Run full test workflow:

```bash
./test_odoo19_modules.sh full
```

**Duration:** 10-30 minutes (depending on operation)

### 3. `cleanup_odoo19_environment.sh`

Cleans up all temporary files and directories created during testing.

**What it does:**

- Calculates and displays disk space to be freed
- Removes Odoo 19 installation
- Removes Python virtual environment
- Removes addons and dependencies directories
- Removes configuration files
- Optionally removes test logs and databases
- Provides summary of cleanup

**Usage:**

Interactive cleanup (confirms before deleting):

```bash
./cleanup_odoo19_environment.sh
```

Force cleanup (no confirmation):

```bash
./cleanup_odoo19_environment.sh -f
```

Keep test logs:

```bash
./cleanup_odoo19_environment.sh -f --keep-logs
```

Remove test databases too:

```bash
./cleanup_odoo19_environment.sh -f --remove-dbs
```

Stop PostgreSQL after cleanup:

```bash
./cleanup_odoo19_environment.sh -f --stop-postgres
```

**Duration:** < 1 minute

## Prerequisites

Before running these scripts:

1. **System Requirements:**

   - Ubuntu 22.04 or similar
   - PostgreSQL 12+
   - Python 3.10+
   - 8GB+ RAM
   - 20GB+ free disk space
   - Root/sudo access

2. **Network Access:**

   - Access to GitHub (to clone repositories)
   - Access to PyPI (for Python packages)

3. **Current Branch:**
   - Scripts operate on the current git branch
   - Ensure you're on the correct branch before running

## Quick Start

```bash
# 1. Setup the environment
sudo ./setup_odoo19_environment.sh

# 2. Check everything is ready
./test_odoo19_modules.sh check

# 3. Run full test
./test_odoo19_modules.sh full

# 4. Cleanup when done
./cleanup_odoo19_environment.sh
```

## Understanding the Output

### Color Coding

- 🟢 **Green (✓)**: Success - operation completed successfully
- 🔴 **Red (ERROR)**: Critical error - needs fixing
- 🟡 **Yellow (⚠)**: Warning - non-critical issue
- 🔵 **Blue (ℹ)**: Information - status update

### Expected Warnings

When running the setup, you'll see warnings about:

1. **MUK modules at 17.0**: May need updates
2. **OCA modules**: Some may not have 19.0 branches yet

## Logs

All logs are saved to `/tmp/odoo19-test-logs/`:

- Installation logs: `<module>_install_YYYYMMDD_HHMMSS.log`
- Test logs: `<module>_test_YYYYMMDD_HHMMSS.log`
- Reports: `odoo19_test_report_YYYYMMDD_HHMMSS.txt`

## Common Issues

### Issue 1: Type 'json' Not Found

**Symptom:** HTTP route errors with `type='json'`

**Cause:** Odoo 19 requires `type='jsonrpc'` instead of `type='json'`

**Solution:** Check for any remaining instances with:

```bash
grep -r "type=['\"]json['\"]" /tmp/odoo19-addons/trn_*
```

### Issue 2: PostgreSQL Connection Failed

**Symptom:** Cannot connect to PostgreSQL

**Solution:**

```bash
sudo service postgresql start
sudo -u postgres psql -c "ALTER USER odoo WITH PASSWORD 'odoo_password' SUPERUSER;"
```

### Issue 3: Python Version Mismatch

**Symptom:** Odoo 19 requires Python 3.10+

**Solution:**

```bash
sudo apt-get install python3.10 python3.10-venv python3.10-dev
```

## Testing Strategy

### Phase 1: Foundation Modules

Test installation of foundation modules:

- trn_vocabulary

### Phase 2: Domain Modules

Test domain modules:

- tpl\_... (add your domain modules here)

### Phase 3: Integration

Test module integrations with external dependencies

## Environment Details

When setup completes, you'll have:

```
Odoo 19:     /tmp/odoo-19/
Config:      /tmp/odoo19-test.conf
Addons:      /tmp/odoo19-addons/
Virtual Env: /tmp/odoo19-venv/
Logs:        /tmp/odoo19-test-logs/
```

## Next Steps After Testing

1. **If tests pass:**

   - Deploy to staging environment

2. **If tests fail:**
   - Review logs in `/tmp/odoo19-test-logs/`
   - Check for breaking changes
   - Fix issues and re-run tests

## Cleanup

After testing, free up disk space by cleaning up the test environment:

```bash
# Interactive cleanup (recommended)
./cleanup_odoo19_environment.sh

# Quick cleanup (skip confirmation)
./cleanup_odoo19_environment.sh -f

# Keep logs for review
./cleanup_odoo19_environment.sh -f --keep-logs

# Also remove test databases
./cleanup_odoo19_environment.sh -f --remove-dbs
```

The cleanup script will remove:

- `/tmp/odoo-19/` (~500MB - Odoo installation)
- `/tmp/odoo19-venv/` (~200MB - Python packages)
- `/tmp/odoo19-addons/` (~100MB - Module links)
- `/tmp/odoo19-deps/` (~200MB - Git repositories)
- `/tmp/odoo19-test.conf` (Configuration file)
- `/tmp/odoo19-test-logs/` (Test logs)

**Total space freed:** ~1GB

## Related Documentation

- `.github/workflows/ci-full.yml` - Full CI/CD configuration
- `.github/workflows/ci-local.yml` - Local CI configuration
- `docs/guides/module-development.md` - Module development guide

## Support

For issues:

1. Check the logs in `/tmp/odoo19-test-logs/`
2. Review documentation
3. Create a GitHub issue in your project repository

## Workflow Summary

```bash
# Complete testing workflow
./setup_odoo19_environment.sh          # Setup (~5-10 min)
./test_odoo19_modules.sh check         # Verify (~30 sec)
./test_odoo19_modules.sh full          # Test (~20-30 min)
./cleanup_odoo19_environment.sh -f     # Cleanup (~30 sec)
```

---

**Last Updated:** 2025-11-18 **Odoo Version:** 19.0 **Python Version:** 3.10+ **Disk Space Required:** ~1GB (temporary)
