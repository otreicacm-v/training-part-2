# OWASP ZAP - Unauthenticated Surface Discovery

Discovers unauthenticated attack surface on a running Odoo instance. Finds public endpoints, exposed admin interfaces,
and misconfigured routes that should require authentication. Passive scanning only.

This is a **local/manual DAST tool**. It is not run in CI because it requires a running Odoo instance.

## Prerequisites

- Docker installed
- Odoo instance running (default: http://localhost:8069)

## Usage

```bash
# Run baseline scan (passive only)
make zap-scan

# Run with custom target
TARGET_URL=http://your-server:8069 ./scripts/zap/run-baseline.sh
```

## Configuration Files

- `zap-baseline.yaml` - Passive scan configuration (spider + passive rules)

## Reports

Reports are generated in `static/security/latest/`:

- `zap_report.html` - Human-readable report
- `zap_report.json` - Machine-readable report

## Security Notes

- This scan is passive only and safe for any environment
- It does not perform active exploitation or fuzzing
- Use it to verify that admin endpoints are not publicly accessible
