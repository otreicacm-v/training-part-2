#!/bin/bash
# Bulk fix Command API tuples in custom modules
#
# This script applies automatic fixes for Odoo 19 Command API compatibility.
# It transforms old tuple patterns like (0, 0, {...}) to Command.create({...}).
#
# Usage:
#   ./scripts/fix-odoo19.sh                        # Fix all trn_* modules
#   ./scripts/fix-odoo19.sh trn_vocabulary       # Fix specific module
#   ./scripts/fix-odoo19.sh --dry-run              # Preview changes without applying
#   ./scripts/fix-odoo19.sh trn_vocabulary --dry-run

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

MODULE=""
DRY_RUN=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [module_name] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  module_name   Specific module to fix (e.g., trn_vocabulary)"
            echo "  --dry-run     Preview changes without applying them"
            echo ""
            echo "Examples:"
            echo "  $0                             # Fix all trn_* modules"
            echo "  $0 trn_vocabulary           # Fix specific module"
            echo "  $0 --dry-run                   # Preview all changes"
            echo "  $0 trn_vocabulary --dry-run # Preview specific module"
            exit 0
            ;;
        *)
            MODULE="$1"
            shift
            ;;
    esac
done

cd "$PROJECT_DIR"

if [ -n "$MODULE" ]; then
    # Fix specific module
    if [ ! -d "$MODULE" ]; then
        echo "Error: Module '$MODULE' not found"
        exit 1
    fi

    echo "Fixing Command API tuples in $MODULE..."

    # Find all Python files in models and wizard directories (excluding tests)
    # Use parentheses to group -o conditions due to operator precedence
    mapfile -t FILES < <(find "$MODULE" -name "*.py" \
        \( -path "*/models/*" -o -path "*/wizard/*" \) \
        2>/dev/null | grep -v "/tests/" || true)

    if [ ${#FILES[@]} -eq 0 ]; then
        echo "No Python files found in $MODULE/models or $MODULE/wizard"
        exit 0
    fi

    # shellcheck disable=SC2086
    python scripts/lint/check_odoo19.py --fix $DRY_RUN "${FILES[@]}"
else
    # Fix all trn_* modules (excluding tests and archived)
    echo "Fixing Command API tuples in all custom modules..."

    mapfile -t FILES < <(find trn_* -name "*.py" \
        \( -path "*/models/*" -o -path "*/wizard/*" \) \
        -not -path "*/tests/*" \
        -not -path "*archived*" \
        2>/dev/null || true)

    if [ ${#FILES[@]} -eq 0 ]; then
        echo "No Python files found"
        exit 0
    fi

    # shellcheck disable=SC2086
    python scripts/lint/check_odoo19.py --fix $DRY_RUN "${FILES[@]}"
fi

echo ""
echo "Done!"
if [ -n "$DRY_RUN" ]; then
    echo "Run without --dry-run to apply the fixes."
fi
