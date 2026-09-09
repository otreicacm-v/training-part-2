# Odoo 19 Project Template Makefile
#
# Local developer targets for security scanning.
# CI uses .github/workflows/security.yml directly.

.PHONY: help zap-scan trivy-scan gitleaks-scan dependency-scan

# Default target
help:
	@echo "Odoo 19 Project Development Commands"
	@echo ""
	@echo "Security Scanning (local use):"
	@echo "  make zap-scan             Run OWASP ZAP baseline scan (requires running Odoo)"
	@echo "  make trivy-scan           Run Trivy container image scan"
	@echo "  make gitleaks-scan        Run Gitleaks secret detection"
	@echo "  make dependency-scan      Run dependency vulnerability scan"

# ============================================
# Security Scanning - Individual Tools
# ============================================

zap-scan:
	@echo "Running OWASP ZAP baseline scan..."
	@chmod +x scripts/zap/run-baseline.sh
	./scripts/zap/run-baseline.sh

trivy-scan:
	@echo "Running Trivy container image scan..."
	@chmod +x scripts/trivy/run-trivy.sh
	./scripts/trivy/run-trivy.sh

gitleaks-scan:
	@echo "Running Gitleaks secret detection..."
	@chmod +x scripts/gitleaks/run-gitleaks.sh
	./scripts/gitleaks/run-gitleaks.sh

dependency-scan:
	@echo "Running dependency vulnerability scan..."
	@chmod +x scripts/dependency-scan.sh
	./scripts/dependency-scan.sh
