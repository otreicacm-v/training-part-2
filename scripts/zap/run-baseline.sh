#!/bin/bash
# Run OWASP ZAP surface scan against an Odoo instance
#
# Scans unauthenticated attack surface only. Not a substitute for
# authenticated penetration testing. Passive scanning only — safe
# for any environment.
# Or use: make zap-scan
#
# Usage:
#   ./scripts/zap/run-baseline.sh [options]
#
# Options:
#   --ci              CI mode: fail on high severity findings
#   --target=URL      Override target URL (default: http://localhost:8069)
#   --report-dir=DIR  Override report directory
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-${ROOT_DIR}/static/security/latest}"
TARGET_URL="${TARGET_URL:-http://localhost:8069}"
CI_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --ci) CI_MODE=true; shift ;;
        --target=*) TARGET_URL="${1#*=}"; shift ;;
        --report-dir=*) REPORT_DIR="${1#*=}"; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$REPORT_DIR"

echo "============================================"
echo "Running ZAP surface scan (unauthenticated only)"
echo "Target: $TARGET_URL"
echo "Reports: $REPORT_DIR"
echo "============================================"

# Run ZAP baseline scan using Docker
docker run --rm \
    -v "$SCRIPT_DIR:/zap/wrk:ro" \
    -v "$REPORT_DIR:/zap/reports:rw" \
    --network host \
    -e TARGET_URL="$TARGET_URL" \
    -e REPORT_DIR="/zap/reports" \
    ghcr.io/zaproxy/zaproxy:stable \
    zap.sh -cmd -autorun /zap/wrk/zap-baseline.yaml

echo ""
echo "Scan complete!"
echo "  HTML Report: $REPORT_DIR/zap_report.html"
echo "  JSON Report: $REPORT_DIR/zap_report.json"

# In CI mode, check for high-severity findings
if [[ "$CI_MODE" == true ]]; then
    if grep -q '"riskdesc":"High"' "$REPORT_DIR/zap_report.json" 2>/dev/null; then
        echo "::error::High severity findings detected!"
        exit 1
    fi
fi
