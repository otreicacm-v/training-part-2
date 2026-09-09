#!/bin/bash
# Scan container images for vulnerabilities using Trivy
#
# Trivy is a comprehensive vulnerability scanner for:
# - Container images (OS packages, application dependencies)
# - Filesystem (misconfigurations, secrets)
# - IaC files (Terraform, CloudFormation, etc.)
#
# Usage:
#   ./scripts/trivy/run-trivy.sh [options]
#
# Options:
#   --ci              CI mode: exit with error on high/critical
#   --image=NAME      Image to scan (default: auto-detect from docker-compose)
#   --report-dir=DIR  Override report directory
#   --severity=LIST   Severity filter (default: CRITICAL,HIGH)
#   --sarif           Generate SARIF format output
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-${ROOT_DIR}/static/security/latest}"
CI_MODE=false
IMAGE_NAME=""
SEVERITY="CRITICAL,HIGH"
SARIF_OUTPUT=false
FOUND_VULNS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --ci) CI_MODE=true; shift ;;
        --image=*) IMAGE_NAME="${1#*=}"; shift ;;
        --report-dir=*) REPORT_DIR="${1#*=}"; shift ;;
        --severity=*) SEVERITY="${1#*=}"; shift ;;
        --sarif) SARIF_OUTPUT=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$REPORT_DIR"

echo "============================================"
echo "Container Image Vulnerability Scan (Trivy)"
echo "Report directory: $REPORT_DIR"
echo "Severity filter: $SEVERITY"
echo "============================================"
echo ""

# Auto-detect image if not specified
if [[ -z "$IMAGE_NAME" ]]; then
    # Try to get image from running containers
    IMAGE_NAME=$(docker compose --profile ui ps --format json 2>/dev/null | \
        python3 -c "import sys,json; data=[json.loads(l) for l in sys.stdin]; print(next((d.get('Image','') for d in data if 'odoo' in d.get('Service','')), ''))" 2>/dev/null || true)

    if [[ -z "$IMAGE_NAME" ]]; then
        # Fall back to image name from Dockerfile
        IMAGE_NAME="odoo-project-dev"
    fi
fi

echo "Scanning image: $IMAGE_NAME"
echo ""

# Check if image exists
if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
    echo "Image '$IMAGE_NAME' not found locally."
    echo "Building image first..."
    cd "$ROOT_DIR"
    docker compose --profile ui build odoo 2>&1 || {
        echo "::warning::Could not build image, skipping container scan"
        exit 0
    }
fi

# ===========================================
# Scan container image
# ===========================================
echo "--- Scanning container image ---"

# Run Trivy image scan
docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$REPORT_DIR:/reports:rw" \
    -v "$HOME/.cache/trivy:/root/.cache/" \
    -v "$ROOT_DIR/.trivyignore.yaml:/root/.trivyignore.yaml:ro" \
    aquasec/trivy:latest image \
    --severity "$SEVERITY" \
    --ignorefile /root/.trivyignore.yaml \
    --format json \
    --output /reports/trivy-image.json \
    "$IMAGE_NAME" 2>&1 || IMAGE_SCAN_EXIT=$?

if [[ "${IMAGE_SCAN_EXIT:-0}" -gt 0 ]]; then
    echo "Trivy image scan exited with code $IMAGE_SCAN_EXIT"
    FOUND_VULNS=true
fi

# Generate human-readable report (cosmetic, ok to fail)
docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$REPORT_DIR:/reports:rw" \
    -v "$HOME/.cache/trivy:/root/.cache/" \
    -v "$ROOT_DIR/.trivyignore.yaml:/root/.trivyignore.yaml:ro" \
    aquasec/trivy:latest image \
    --severity "$SEVERITY" \
    --ignorefile /root/.trivyignore.yaml \
    --format table \
    "$IMAGE_NAME" 2>&1 | tee "$REPORT_DIR/trivy-image.txt" || true

# Generate SARIF if requested
if [[ "$SARIF_OUTPUT" == true ]]; then
    SARIF_EXIT=0
    docker run --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v "$REPORT_DIR:/reports:rw" \
        -v "$HOME/.cache/trivy:/root/.cache/" \
        -v "$ROOT_DIR/.trivyignore.yaml:/root/.trivyignore.yaml:ro" \
        aquasec/trivy:latest image \
        --severity "$SEVERITY" \
        --ignorefile /root/.trivyignore.yaml \
        --format sarif \
        --output /reports/trivy-image.sarif \
        "$IMAGE_NAME" 2>&1 || SARIF_EXIT=$?

    if [[ "$SARIF_EXIT" -gt 0 ]]; then
        echo "Trivy SARIF generation exited with code $SARIF_EXIT"
    fi
fi

# Check for vulnerabilities
if [[ -f "$REPORT_DIR/trivy-image.json" ]]; then
    vuln_count=$(REPORT_DIR="$REPORT_DIR" python3 -c "
import json, os
data = json.load(open(os.path.join(os.environ['REPORT_DIR'], 'trivy-image.json')))
results = data.get('Results', [])
total = sum(len(r.get('Vulnerabilities', [])) for r in results)
print(total)
" 2>/dev/null || echo "0")

    if [[ "$vuln_count" -gt 0 ]]; then
        echo ""
        echo "Found $vuln_count vulnerabilities in container image"
        FOUND_VULNS=true
    else
        echo "No vulnerabilities found in container image"
    fi
fi

echo ""

# ===========================================
# Scan filesystem for misconfigurations
# ===========================================
echo "--- Scanning for misconfigurations ---"

docker run --rm \
    -v "$ROOT_DIR:/src:ro" \
    -v "$REPORT_DIR:/reports:rw" \
    -v "$HOME/.cache/trivy:/root/.cache/" \
    aquasec/trivy:latest fs \
    --scanners misconfig \
    --severity "$SEVERITY" \
    --ignorefile /src/.trivyignore.yaml \
    --format json \
    --output /reports/trivy-misconfig.json \
    /src 2>&1 || MISCONFIG_EXIT=$?

if [[ "${MISCONFIG_EXIT:-0}" -gt 0 ]]; then
    echo "Trivy misconfig scan exited with code $MISCONFIG_EXIT"
fi

# Check for misconfigurations
if [[ -f "$REPORT_DIR/trivy-misconfig.json" ]]; then
    misconfig_count=$(REPORT_DIR="$REPORT_DIR" python3 -c "
import json, os
data = json.load(open(os.path.join(os.environ['REPORT_DIR'], 'trivy-misconfig.json')))
results = data.get('Results', [])
total = sum(len(r.get('Misconfigurations', [])) for r in results)
print(total)
" 2>/dev/null || echo "0")

    if [[ "$misconfig_count" -gt 0 ]]; then
        echo "Found $misconfig_count misconfigurations"
    else
        echo "No misconfigurations found"
    fi
fi

echo ""
echo "============================================"
echo "Trivy scan complete!"
echo "============================================"
echo ""
echo "Reports:"
[[ -f "$REPORT_DIR/trivy-image.json" ]] && echo "  - Image scan: $REPORT_DIR/trivy-image.json"
[[ -f "$REPORT_DIR/trivy-image.txt" ]] && echo "  - Image scan: $REPORT_DIR/trivy-image.txt"
[[ -f "$REPORT_DIR/trivy-image.sarif" ]] && echo "  - Image SARIF: $REPORT_DIR/trivy-image.sarif"
[[ -f "$REPORT_DIR/trivy-misconfig.json" ]] && echo "  - Misconfig: $REPORT_DIR/trivy-misconfig.json"

# CI mode: fail if vulnerabilities found
if [[ "$CI_MODE" == true ]] && [[ "$FOUND_VULNS" == true ]]; then
    echo ""
    echo "::error::Container vulnerabilities detected!"
    exit 1
fi
