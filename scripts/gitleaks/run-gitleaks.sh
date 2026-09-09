#!/bin/bash
# Scan repository for secrets and credentials using Gitleaks
#
# Gitleaks detects hardcoded secrets like:
# - API keys and tokens
# - Passwords and credentials
# - Private keys
# - Cloud provider secrets (AWS, GCP, Azure)
#
# Usage:
#   ./scripts/gitleaks/run-gitleaks.sh [options]
#
# Options:
#   --ci              CI mode: exit with error on findings
#   --report-dir=DIR  Override report directory
#   --sarif           Generate SARIF format output
#   --baseline=FILE   Use baseline file to ignore known issues
#   --history         Scan full git history (default: current state only)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-${ROOT_DIR}/static/security/latest}"
CI_MODE=false
SARIF_OUTPUT=false
BASELINE_FILE=""
SCAN_HISTORY=false
FOUND_SECRETS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --ci) CI_MODE=true; shift ;;
        --report-dir=*) REPORT_DIR="${1#*=}"; shift ;;
        --sarif) SARIF_OUTPUT=true; shift ;;
        --baseline=*) BASELINE_FILE="${1#*=}"; shift ;;
        --history) SCAN_HISTORY=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$REPORT_DIR"

echo "============================================"
echo "Secret Scanning (Gitleaks)"
echo "Report directory: $REPORT_DIR"
echo "============================================"
echo ""

# Build gitleaks command
GITLEAKS_OPTS=()

if [[ -n "$BASELINE_FILE" ]] && [[ -f "$BASELINE_FILE" ]]; then
    echo "Using baseline: $BASELINE_FILE"
    GITLEAKS_OPTS+=(--baseline-path "/baseline/$(basename "$BASELINE_FILE")")
fi

# ===========================================
# Scan current state (detect mode, no history)
# ===========================================
echo "--- Scanning repository for secrets ---"

# Run gitleaks detect (scans current state only, no git history)
SCAN_EXIT=0
docker run --rm \
    -v "$ROOT_DIR:/repo:ro" \
    -v "$REPORT_DIR:/reports:rw" \
    ${BASELINE_FILE:+-v "$(dirname "$BASELINE_FILE"):/baseline:ro"} \
    zricethezav/gitleaks:latest \
    detect \
    --source /repo \
    --config /repo/.gitleaks.toml \
    --report-path /reports/gitleaks.json \
    --report-format json \
    --no-git \
    "${GITLEAKS_OPTS[@]}" \
    2>&1 || SCAN_EXIT=$?

# Check scan result
if [[ "$SCAN_EXIT" -eq 1 ]]; then
    FOUND_SECRETS=true
    echo "Secrets detected!"
elif [[ "$SCAN_EXIT" -gt 1 ]]; then
    echo "Gitleaks encountered an error (exit code: $SCAN_EXIT)"
    exit "$SCAN_EXIT"
else
    echo "No secrets detected"
fi

# Generate human-readable report
if [[ -f "$REPORT_DIR/gitleaks.json" ]]; then
    REPORT_DIR="$REPORT_DIR" python3 << 'PYTHON' > "$REPORT_DIR/gitleaks.txt" 2>/dev/null || true
import json
import os
import sys

try:
    report_dir = os.environ["REPORT_DIR"]
    with open(os.path.join(report_dir, "gitleaks.json")) as f:
        findings = json.load(f)

    if not findings:
        print("No secrets found.")
        sys.exit(0)

    print(f"Found {len(findings)} potential secret(s):\n")
    print("=" * 80)

    for i, finding in enumerate(findings, 1):
        print(f"\n[{i}] {finding.get('Description', 'Unknown')}")
        print(f"    Rule: {finding.get('RuleID', 'N/A')}")
        print(f"    File: {finding.get('File', 'N/A')}:{finding.get('StartLine', '?')}")
        print(f"    Secret: {finding.get('Secret', 'N/A')[:50]}...")
        print("-" * 80)

except Exception as e:
    print(f"Error processing report: {e}")
PYTHON
fi

# Generate SARIF if requested
if [[ "$SARIF_OUTPUT" == true ]]; then
    SARIF_EXIT=0
    docker run --rm \
        -v "$ROOT_DIR:/repo:ro" \
        -v "$REPORT_DIR:/reports:rw" \
        ${BASELINE_FILE:+-v "$(dirname "$BASELINE_FILE"):/baseline:ro"} \
        zricethezav/gitleaks:latest \
        detect \
        --source /repo \
        --config /repo/.gitleaks.toml \
        --report-path /reports/gitleaks.sarif \
        --report-format sarif \
        --no-git \
        "${GITLEAKS_OPTS[@]}" \
        2>&1 || SARIF_EXIT=$?

    if [[ "$SARIF_EXIT" -gt 1 ]]; then
        echo "Gitleaks SARIF generation failed (exit code: $SARIF_EXIT)"
        exit "$SARIF_EXIT"
    fi
fi

echo ""

# ===========================================
# Scan git history (opt-in via --history)
# ===========================================
if [[ "$SCAN_HISTORY" == true ]]; then
    echo "--- Scanning git history for secrets ---"

    HISTORY_EXIT=0
    docker run --rm \
        -v "$ROOT_DIR:/repo:ro" \
        -v "$REPORT_DIR:/reports:rw" \
        zricethezav/gitleaks:latest \
        detect \
        --source /repo \
        --report-path /reports/gitleaks-history.json \
        --report-format json \
        --log-opts="--all --full-history" \
        2>&1 || HISTORY_EXIT=$?

    if [[ "$HISTORY_EXIT" -eq 1 ]]; then
        echo "Secrets found in git history!"
        FOUND_SECRETS=true

        # Count findings
        if [[ -f "$REPORT_DIR/gitleaks-history.json" ]]; then
            count=$(REPORT_DIR="$REPORT_DIR" python3 -c "import json,os; print(len(json.load(open(os.path.join(os.environ['REPORT_DIR'],'gitleaks-history.json')))))" 2>/dev/null || echo "?")
            echo "  Found $count secret(s) in history"
        fi
    elif [[ "$HISTORY_EXIT" -gt 1 ]]; then
        echo "Gitleaks history scan failed (exit code: $HISTORY_EXIT)"
        exit "$HISTORY_EXIT"
    else
        echo "No secrets found in git history"
    fi

    echo ""
fi

echo "============================================"
echo "Secret scan complete!"
echo "============================================"
echo ""
echo "Reports:"
[[ -f "$REPORT_DIR/gitleaks.json" ]] && echo "  - Current state: $REPORT_DIR/gitleaks.json"
[[ -f "$REPORT_DIR/gitleaks.txt" ]] && echo "  - Current state: $REPORT_DIR/gitleaks.txt"
[[ -f "$REPORT_DIR/gitleaks.sarif" ]] && echo "  - SARIF: $REPORT_DIR/gitleaks.sarif"
[[ -f "$REPORT_DIR/gitleaks-history.json" ]] && echo "  - Git history: $REPORT_DIR/gitleaks-history.json"

# CI mode: fail if secrets found
if [[ "$CI_MODE" == true ]] && [[ "$FOUND_SECRETS" == true ]]; then
    echo ""
    echo "::error::Secrets detected in repository!"
    exit 1
fi
