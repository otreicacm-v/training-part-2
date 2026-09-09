# Security Scanning

Security scanning uses a combination of CI-automated and local tools.

## Overview

### CI-Automated (`.github/workflows/security.yml`)

These run automatically on PRs, pushes, and weekly schedule:

- **Gitleaks** - Secret detection (SARIF upload to GitHub Security tab)
- **pip-audit** - Python dependency vulnerability scanning (includes `__manifest__.py` deps)
- **npm audit** - JavaScript dependency scanning
- **Semgrep** - Static analysis with custom Odoo rules
- **Trivy** - Container image and filesystem scan (push + weekly only)

### Local/Manual Tools

- **OWASP ZAP** - Unauthenticated surface scan (requires running Odoo).
  Scans unauthenticated attack surface only. Not a substitute for
  authenticated penetration testing.

### Other CI Workflows

- **CodeQL** - GitHub code analysis (`.github/workflows/code-analysis.yml`)
- **pre-commit** - Lint and format checks (`.github/workflows/pre-commit.yml`)

## Quick Start (Local)

```bash
# Individual scans
make zap-scan           # OWASP ZAP baseline (requires running Odoo)
make trivy-scan         # Container image scan
make gitleaks-scan      # Secret detection
make dependency-scan    # pip-audit + npm audit
```

## Reports

Local scan reports are saved to `static/security/latest/`:

| File | Scanner | Description |
|------|---------|-------------|
| `zap_report.html` | ZAP | Surface scan HTML report (unauthenticated only) |
| `zap_report.json` | ZAP | Surface scan JSON report (unauthenticated only) |
| `trivy-image.json` | Trivy | Container vulnerabilities |
| `trivy-misconfig.json` | Trivy | Misconfigurations |
| `pip-audit.json` | pip-audit | Python vulnerabilities |
| `gitleaks.json` | Gitleaks | Detected secrets |

CI results appear in the GitHub Security tab (SARIF) and as workflow annotations.

## Individual Scanner Scripts

```bash
# ZAP Baseline (passive only, requires running Odoo)
./scripts/zap/run-baseline.sh [--ci] [--target=URL] [--report-dir=DIR]

# Trivy
./scripts/trivy/run-trivy.sh [--ci] [--image=NAME] [--sarif]

# Gitleaks (current state only by default)
./scripts/gitleaks/run-gitleaks.sh [--ci] [--sarif] [--history]

# Dependency Scan
./scripts/dependency-scan.sh [--ci] [--sarif]
```

## Understanding the Results

### Severity Levels

| Level | ZAP | Trivy | Action Required |
|-------|-----|-------|-----------------|
| **Critical** | - | CRITICAL | Immediate |
| **High** | High | HIGH | Within 24h |
| **Medium** | Medium | MEDIUM | Within sprint |
| **Low** | Low | LOW | Backlog |
| **Info** | Informational | - | Optional |

### What Gets Scanned

#### DAST (ZAP - local only, unauthenticated surface scan)
- Known public endpoints (`/web/login`, `/web/database/selector`, `/web/reset_password`, `/sitemap.xml`, `/robots.txt`)
- Spider-discovered pages from those seeds
- Public endpoints that should require authentication
- Misconfigured routes

> **Limitation:** This scan covers unauthenticated attack surface only.
> It does not test authenticated workflows, API endpoints behind login,
> or role-based access control. Authenticated penetration testing should
> be performed separately.

#### Container (Trivy)
- OS packages in Docker image
- Application dependencies
- Dockerfile misconfigurations

#### Dependencies (pip-audit)
- Python packages in requirements.txt
- Known CVEs from PyPI Advisory DB

#### Secrets (Gitleaks)
- API keys, tokens, passwords in code
- Cloud provider credentials
- Private keys

## Configuration Files

| File | Purpose |
|------|---------|
| `.gitleaks.toml` | Gitleaks allowlist for known false positives |
| `.trivyignore.yaml` | Trivy suppressions for accepted risks |
| `scripts/zap/zap-baseline.yaml` | ZAP spider and passive scan configuration |
| `.semgrep/` | Custom Semgrep rules for Odoo |

## Suppression Policy

### Trivy (`.trivyignore.yaml`)
- Only suppress CVEs with **no available fix** in the target platform
- CVEs with available fixes should be patched in the Dockerfile or image rebuild
- All suppressions have expiry dates and are reviewed periodically

### Gitleaks (`.gitleaks.toml`)
- Path-based allowlist for known false positives
- Test data directories, documentation, and vendored libraries excluded

## Extending the Scans

### Custom ZAP Configuration

Modify `scripts/zap/zap-baseline.yaml` to adjust spider depth, duration, or excluded paths.

### Adding New Scanners

1. Create script in `scripts/`
2. Add Makefile target for local use
3. Add job to `.github/workflows/security.yml` for CI

### Pre-commit Integration

Add to `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/gitleaks/gitleaks
  rev: v8.18.0
  hooks:
    - id: gitleaks
```
