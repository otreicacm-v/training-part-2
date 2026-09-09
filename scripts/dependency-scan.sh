#!/bin/bash
# Scan Python and JavaScript dependencies for known vulnerabilities
#
# Uses:
# - pip-audit: Python dependency vulnerability scanner
# - npm audit: JavaScript dependency scanner (if package.json exists)
#
# Usage:
#   ./scripts/dependency-scan.sh [options]
#
# Options:
#   --ci              CI mode: exit with error on vulnerabilities
#   --report-dir=DIR  Override report directory
#   --sarif           Generate SARIF format output
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT_DIR="${REPORT_DIR:-${ROOT_DIR}/static/security/latest}"
CI_MODE=false
SARIF_OUTPUT=false
FOUND_VULNS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --ci) CI_MODE=true; shift ;;
        --report-dir=*) REPORT_DIR="${1#*=}"; shift ;;
        --sarif) SARIF_OUTPUT=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$REPORT_DIR"

echo "============================================"
echo "Dependency Vulnerability Scan"
echo "Report directory: $REPORT_DIR"
echo "============================================"
echo ""

# ===========================================
# Python Dependencies (pip-audit)
# ===========================================
echo "--- Python Dependencies (pip-audit) ---"

# Find all requirements files
REQ_FILES=$(find "$ROOT_DIR" -name "requirements*.txt" -not -path "*/\.*" -not -path "*/.venv/*" 2>/dev/null || true)

if [[ -n "$REQ_FILES" ]]; then
    echo "Found requirements files:"
    echo "$REQ_FILES" | while read -r f; do echo "  - $f"; done
    echo ""

    # Run pip-audit using Docker
    SARIF_FLAG=""
    if [[ "$SARIF_OUTPUT" == true ]]; then
        SARIF_FLAG="--format sarif --output /reports/pip-audit.sarif"
    fi

    # Create a temporary combined requirements file
    COMBINED_REQ=$(mktemp)
    for req_file in $REQ_FILES; do
        cat "$req_file" >> "$COMBINED_REQ" 2>/dev/null || true
    done

    # Separate VCS/URL lines and log them as warnings
    VCS_LINES=$(grep -E "^(git\+|https?://|svn\+|hg\+|-e )" "$COMBINED_REQ" 2>/dev/null || true)
    if [[ -n "$VCS_LINES" ]]; then
        echo "::warning::Skipping VCS/URL dependencies (cannot be audited):"
        echo "$VCS_LINES" | while read -r line; do
            echo "::warning::  $line"
        done
    fi

    # Remove duplicates, comments, VCS/URL lines, and packages with native build
    # dependencies that cannot be resolved in a bare Python container (e.g. Fiona
    # requires gdal-config, GDAL requires libgdal-dev).
    FIONA_GDAL=$(grep -iE "^(Fiona|GDAL)" "$COMBINED_REQ" 2>/dev/null || true)
    if [[ -n "$FIONA_GDAL" ]]; then
        echo "::warning::Fiona/GDAL excluded (require native GDAL/libgdal-dev build dependencies)"
    fi

    sort -u "$COMBINED_REQ" | grep -v "^#" | grep -v "^$" | grep -v "^git+" | grep -v "^-e " | grep -v "^https\?://" | grep -v "^svn+" | grep -v "^hg+" | grep -iv "^Fiona" | grep -iv "^GDAL" > "${COMBINED_REQ}.clean" || true
    mv "${COMBINED_REQ}.clean" "$COMBINED_REQ"

    # Extract Python dependencies from Odoo __manifest__.py files.
    # These declare dependencies via external_dependencies.python that
    # are not listed in requirements.txt files.
    MANIFEST_DEPS=$(python3 -c "
import ast, glob, sys
packages = set()
for path in glob.glob('$ROOT_DIR/**/__manifest__.py', recursive=True):
    try:
        with open(path) as f:
            manifest = ast.literal_eval(f.read())
        for pkg in manifest.get('external_dependencies', {}).get('python', []):
            packages.add(pkg)
    except Exception:
        pass
for pkg in sorted(packages):
    print(pkg)
" 2>/dev/null || true)

    if [[ -n "$MANIFEST_DEPS" ]]; then
        MANIFEST_COUNT=$(echo "$MANIFEST_DEPS" | wc -l | tr -d ' ')
        echo "Found $MANIFEST_COUNT Python packages declared in __manifest__.py files"
        echo "$MANIFEST_DEPS" >> "$COMBINED_REQ"
        # Re-dedup after adding manifest deps
        sort -u "$COMBINED_REQ" > "${COMBINED_REQ}.dedup" || true
        mv "${COMBINED_REQ}.dedup" "$COMBINED_REQ"
    fi

    PIP_AUDIT_EXIT=0
    docker run --rm \
        -v "$COMBINED_REQ:/requirements.txt:ro" \
        -v "$REPORT_DIR:/reports:rw" \
        python:3.12-slim \
        sh -c "
            pip install --quiet 'pip-audit==2.8.0' 2>/dev/null
            pip-audit -r /requirements.txt \
                --format json \
                --output /reports/pip-audit.json \
                $SARIF_FLAG \
                2>&1
            AUDIT_EXIT=\$?
            pip-audit -r /requirements.txt \
                --format columns \
                2>&1 || true
            exit \$AUDIT_EXIT
        " 2>&1 || PIP_AUDIT_EXIT=$?

    rm -f "$COMBINED_REQ"

    # Check for vulnerabilities
    if [[ "$PIP_AUDIT_EXIT" -ne 0 ]]; then
        echo "pip-audit found issues (exit code: $PIP_AUDIT_EXIT)"
        FOUND_VULNS=true
    elif [[ -f "$REPORT_DIR/pip-audit.json" ]]; then
        vuln_count=$(REPORT_DIR="$REPORT_DIR" python3 -c "import json,os; data=json.load(open(os.path.join(os.environ['REPORT_DIR'],'pip-audit.json'))); print(len([d for d in data.get('dependencies', []) if d.get('vulns')]))" 2>/dev/null || echo "0")
        if [[ "$vuln_count" -gt 0 ]]; then
            echo "Found $vuln_count Python packages with vulnerabilities"
            FOUND_VULNS=true
        else
            echo "No Python vulnerabilities found"
        fi
    fi
else
    echo "No requirements.txt files found"
fi

echo ""

# ===========================================
# JavaScript Dependencies (npm audit)
# ===========================================
echo "--- JavaScript Dependencies (npm audit) ---"

# Find package.json files (excluding node_modules)
PKG_FILES=$(find "$ROOT_DIR" -name "package.json" -not -path "*/node_modules/*" -not -path "*/\.*" 2>/dev/null || true)

if [[ -n "$PKG_FILES" ]]; then
    echo "Found package.json files:"
    echo "$PKG_FILES" | while read -r f; do echo "  - $f"; done
    echo ""

    # Process each package.json
    for pkg_file in $PKG_FILES; do
        pkg_dir=$(dirname "$pkg_file")
        pkg_name=$(basename "$pkg_dir")
        echo "Scanning: $pkg_name"

        # Check if package-lock.json exists
        if [[ -f "$pkg_dir/package-lock.json" ]]; then
            NPM_EXIT=0
            docker run --rm \
                -v "$pkg_dir:/app:ro" \
                -v "$REPORT_DIR:/reports:rw" \
                -w /app \
                node:20-slim \
                sh -c "
                    npm audit --json > /reports/npm-audit-${pkg_name}.json 2>&1
                    NPM_EXIT=\$?
                    npm audit 2>&1 | tee /reports/npm-audit-${pkg_name}.txt
                    exit \$NPM_EXIT
                " 2>&1 || NPM_EXIT=$?

            if [[ "$NPM_EXIT" -ne 0 ]]; then
                echo "  npm audit found issues in $pkg_name (exit code: $NPM_EXIT)"
                FOUND_VULNS=true
            fi
        else
            echo "  Skipping $pkg_name (no package-lock.json)"
        fi
    done
else
    echo "No package.json files found"
fi

echo ""
echo "============================================"
echo "Dependency scan complete!"
echo "============================================"
echo ""
echo "Reports:"
[[ -f "$REPORT_DIR/pip-audit.json" ]] && echo "  - Python: $REPORT_DIR/pip-audit.json"
[[ -f "$REPORT_DIR/pip-audit.txt" ]] && echo "  - Python: $REPORT_DIR/pip-audit.txt"
for f in "$REPORT_DIR"/npm-audit-*.json; do [[ -f "$f" ]] && echo "  - NPM: $f"; done

# CI mode: fail if vulnerabilities found
if [[ "$CI_MODE" == true ]] && [[ "$FOUND_VULNS" == true ]]; then
    echo ""
    echo "::error::Dependency vulnerabilities detected!"
    exit 1
fi
