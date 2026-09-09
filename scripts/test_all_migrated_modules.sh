#!/bin/bash
# Test all successfully migrated Odoo modules for Odoo 19

MODULES=(
    "trn_vocabulary"
)

RESULTS_FILE="/tmp/odoo_test_results_$(date +%Y%m%d_%H%M%S).txt"

echo "=========================================="
echo "Testing All Migrated Odoo Modules"
echo "Date: $(date)"
echo "Results file: $RESULTS_FILE"
echo "=========================================="
echo ""

echo "Module,Total Tests,Passed,Failed,Errors,Status" > "$RESULTS_FILE"

for module in "${MODULES[@]}"; do
    echo "Testing: $module"

    LOG=$(bash ./scripts/test_single_module.sh "$module" 2>&1)

    PASSED=$(echo "$LOG" | grep "Tests Passed:" | awk '{print $3}')
    FAILED=$(echo "$LOG" | grep "Tests Failed:" | awk '{print $3}')
    ERRORS=$(echo "$LOG" | grep "Tests Error:" | awk '{print $3}')

    # Handle empty values
    PASSED=${PASSED:-0}
    FAILED=${FAILED:-0}
    ERRORS=${ERRORS:-0}

    TOTAL=$((PASSED + FAILED + ERRORS))

    if [ "$FAILED" -eq 0 ] && [ "$ERRORS" -eq 0 ]; then
        STATUS="✓ PASS"
    else
        STATUS="✗ FAIL"
    fi

    echo "$module,$TOTAL,$PASSED,$FAILED,$ERRORS,$STATUS" >> "$RESULTS_FILE"
    echo "  → $STATUS (Total: $TOTAL, Passed: $PASSED, Failed: $FAILED, Errors: $ERRORS)"
    echo ""
done

echo "=========================================="
echo "Test Summary"
echo "=========================================="
cat "$RESULTS_FILE"
echo ""
echo "Detailed results saved to: $RESULTS_FILE"
