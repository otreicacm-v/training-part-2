#!/bin/bash
# Audit all Odoo modules for access rights compliance with V2 principles
# This script runs locally without requiring any external AI service
#
# Usage:
#   ./scripts/audit-security.sh                      # Audit all modules
#   ./scripts/audit-security.sh trn_api         # Audit single module
#   ./scripts/audit-security.sh --summary            # Show summary only
#   ./scripts/audit-security.sh --json               # Output as JSON
#   ./scripts/audit-security.sh --check=acl          # Check only ACL files
#   ./scripts/audit-security.sh --check=rules        # Check only record rules
#   ./scripts/audit-security.sh --check=groups       # Check only security groups
#   ./scripts/audit-security.sh --check=legacy       # Check only legacy patterns
#   ./scripts/audit-security.sh --check=odoo19       # Check only Odoo 19 compat
#   ./scripts/audit-security.sh --no-color           # Disable color output (for parsing)
#   ./scripts/audit-security.sh --counts-only        # Output only "ERRORS WARNINGS" (for scripts)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="$ROOT_DIR/reports/security"
SUMMARY_ONLY=false
JSON_OUTPUT=false
COUNTS_ONLY=false
CHECK_TYPE="all"
NO_COLOR=false
MODULES=()

# Colors for terminal output (may be disabled with --no-color)
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --summary) SUMMARY_ONLY=true; shift ;;
        --json) JSON_OUTPUT=true; shift ;;
        --no-color) NO_COLOR=true; shift ;;
        --counts-only) COUNTS_ONLY=true; NO_COLOR=true; shift ;;
        --check=*) CHECK_TYPE="${1#*=}"; shift ;;
        *) MODULES+=("$1"); shift ;;
    esac
done

# Disable colors if requested or counts-only mode
if [[ "$NO_COLOR" == true ]]; then
    RED=''
    YELLOW=''
    GREEN=''
    BLUE=''
    NC=''
fi

mkdir -p "$REPORT_DIR"

# Get modules to audit
if [[ ${#MODULES[@]} -eq 0 ]]; then
    while IFS= read -r module; do
        MODULES+=("$module")
    done < <(find "$ROOT_DIR" -maxdepth 1 -type d -print | while IFS= read -r d; do
        [[ -f "$d/__manifest__.py" ]] && basename "$d"
    done | sort)
fi

# Initialize counters
declare -A MODULE_ERRORS
declare -A MODULE_WARNINGS
TOTAL_ERRORS=0
TOTAL_WARNINGS=0

# Temporary files for collecting issues
ISSUES_FILE=$(mktemp)
trap "rm -f $ISSUES_FILE" EXIT

log_issue() {
    local severity=$1
    local module=$2
    local check=$3
    local file=$4
    local message=$5

    echo "$severity|$module|$check|$file|$message" >> "$ISSUES_FILE"

    if [[ "$severity" == "ERROR" ]]; then
        MODULE_ERRORS[$module]=$(( ${MODULE_ERRORS[$module]:-0} + 1 ))
        TOTAL_ERRORS=$(( TOTAL_ERRORS + 1 ))
    else
        MODULE_WARNINGS[$module]=$(( ${MODULE_WARNINGS[$module]:-0} + 1 ))
        TOTAL_WARNINGS=$(( TOTAL_WARNINGS + 1 ))
    fi

    if [[ "$SUMMARY_ONLY" == false && "$JSON_OUTPUT" == false && "$COUNTS_ONLY" == false ]]; then
        if [[ "$severity" == "ERROR" ]]; then
            echo -e "  ${RED}[ERROR]${NC} $check: $message"
        else
            echo -e "  ${YELLOW}[WARN]${NC} $check: $message"
        fi
        if [[ -n "$file" && "$file" != "-" ]]; then
            echo "         File: $file"
        fi
    fi
}

# ============================================================================
# CHECK 1: ACL Files (ir.model.access.csv)
# ============================================================================
check_acl_files() {
    local module=$1
    local module_path="$ROOT_DIR/$module"
    local acl_file="$module_path/security/ir.model.access.csv"

    # Check if ACL file exists
    if [[ ! -f "$acl_file" ]]; then
        # Check if module defines any models
        local has_models=false
        if grep -rq "_name = ['\"]tpl\." "$module_path"/*.py 2>/dev/null || \
           grep -rq "_name = ['\"]tpl\." "$module_path"/models/*.py 2>/dev/null; then
            has_models=true
        fi

        if [[ "$has_models" == true ]]; then
            log_issue "WARNING" "$module" "ACL" "-" "Module defines models but has no ir.model.access.csv"
        fi
        return
    fi

    # Check ACL naming conventions
    while IFS=, read -r id name model_id group_id perm_read perm_write perm_create perm_unlink; do
        # Skip header and empty lines
        [[ "$id" == "id" || -z "$id" ]] && continue

        # Check naming pattern: access_{model}_{group}
        if [[ ! "$id" =~ ^access_ ]]; then
            log_issue "WARNING" "$module" "ACL-NAMING" "$acl_file" "Entry '$id' doesn't follow 'access_{model}_{group}' pattern"
        fi

        # Check for invalid group references (basic check - group should exist in module or dependencies)
        if [[ -n "$group_id" && "$group_id" != "group_id:id" ]]; then
            local group_ref="${group_id##*:}"  # Remove "group_id:" prefix if present
            # If it's a local reference (no module prefix), check if it exists in this module
            if [[ ! "$group_ref" =~ \. ]]; then
                if ! grep -rq "id=\"$group_ref\"" "$module_path/security/"*.xml 2>/dev/null; then
                    # Could be defined in a dependency - just warn
                    :
                fi
            fi
        fi
    done < "$acl_file"
}

# ============================================================================
# CHECK 2: Record Rules (ir.rule)
# ============================================================================
check_record_rules() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    # Find all XML files with ir.rule definitions
    for xml_file in "$module_path"/security/*.xml; do
        [[ -f "$xml_file" ]] || continue

        # Check for noupdate wrapper
        if grep -q 'model="ir.rule"' "$xml_file"; then
            if ! grep -q 'noupdate="1"' "$xml_file" && ! grep -q "noupdate='1'" "$xml_file"; then
                log_issue "WARNING" "$module" "RULES-NOUPDATE" "$xml_file" "Record rules should be wrapped in <data noupdate=\"1\">"
            fi
        fi

        # Check for empty domain_force with write permissions
        # This is a simplified check - a proper XML parser would be better
        if grep -q 'domain_force.*\[\]' "$xml_file" || grep -q "domain_force.*\[\s*\]" "$xml_file"; then
            if grep -q 'perm_write.*1' "$xml_file" || grep -q 'perm_create.*1' "$xml_file" || grep -q 'perm_unlink.*1' "$xml_file"; then
                log_issue "ERROR" "$module" "RULES-EMPTY-DOMAIN" "$xml_file" "Empty domain_force [] with write/create/unlink is forbidden"
            fi
        fi

        # Check for rules missing groups AND not global
        # Extract ir.rule records and check each one
        local in_rule=false
        local has_groups=false
        local has_global=false
        local rule_id=""

        while IFS= read -r line; do
            if [[ "$line" =~ \<record.*model=\"ir.rule\" ]]; then
                in_rule=true
                has_groups=false
                has_global=false
                rule_id=$(echo "$line" | sed -n 's/.*id="\([^"]*\)".*/\1/p')
            elif [[ "$in_rule" == true ]]; then
                if [[ "$line" =~ \<field.*name=\"groups\" ]]; then
                    has_groups=true
                fi
                if [[ "$line" =~ \<field.*name=\"global\" ]] && [[ "$line" =~ True || "$line" =~ 1 ]]; then
                    has_global=true
                fi
                if [[ "$line" =~ \</record\> ]]; then
                    if [[ "$has_groups" == false && "$has_global" == false ]]; then
                        log_issue "WARNING" "$module" "RULES-NO-GROUP" "$xml_file" "Rule '$rule_id' has no groups and is not global (applies to all users)"
                    fi
                    in_rule=false
                fi
            fi
        done < "$xml_file"
    done
}

# ============================================================================
# CHECK 3: Security Groups V2 Compliance
# ============================================================================
check_security_groups() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    for xml_file in "$module_path"/security/*.xml; do
        [[ -f "$xml_file" ]] || continue

        # Check for category_id on res.groups (should only be on res.groups.privilege)
        # This is the Odoo 19 violation
        local in_group=false
        local group_id=""

        while IFS= read -r line; do
            if [[ "$line" =~ \<record.*model=\"res.groups\" ]] && [[ ! "$line" =~ model=\"res.groups.privilege\" ]]; then
                in_group=true
                group_id=$(echo "$line" | sed -n 's/.*id="\([^"]*\)".*/\1/p')
                [[ -z "$group_id" ]] && group_id="unknown"
            elif [[ "$in_group" == true ]]; then
                if [[ "$line" =~ \<field.*name=\"category_id\" ]]; then
                    log_issue "ERROR" "$module" "GROUPS-CATEGORY" "$xml_file" "Group '$group_id' uses category_id (Odoo 19 violation - use privilege_id instead)"
                fi
                if [[ "$line" =~ \</record\> ]]; then
                    in_group=false
                fi
            fi
        done < "$xml_file"

        # Check for old 'users' field (should be 'user_ids')
        if grep -q 'name="users"' "$xml_file" && grep -q 'model="res.groups"' "$xml_file"; then
            log_issue "ERROR" "$module" "GROUPS-USERS-FIELD" "$xml_file" "Uses 'users' field instead of 'user_ids' (Odoo 19)"
        fi

        # Check for old tuple syntax (4, ref()) instead of Command.link()
        if grep -qE '\(4,\s*ref\(' "$xml_file" || grep -qE '\[\s*\(4,' "$xml_file"; then
            log_issue "ERROR" "$module" "GROUPS-TUPLE-SYNTAX" "$xml_file" "Uses old tuple syntax (4, ref()) - should use Command.link()"
        fi

        # Check for groups_id instead of group_ids on menus
        if grep -q 'name="groups_id"' "$xml_file"; then
            log_issue "ERROR" "$module" "MENU-GROUPS-FIELD" "$xml_file" "Uses 'groups_id' instead of 'group_ids' (Odoo 19)"
        fi

        # Check if module defines ir.module.category (should only be in the project's security module)
        # Replace trn_security with your project's security module name
        if [[ "$module" != "trn_security" ]]; then
            if grep -q 'model="ir.module.category"' "$xml_file"; then
                log_issue "WARNING" "$module" "GROUPS-CATEGORY-DEF" "$xml_file" "Defines ir.module.category (should only be in trn_security)"
            fi
        fi
    done

    # Check if module depends on the project's security module
    # Replace trn_security with your project's security module name
    local manifest="$module_path/__manifest__.py"
    if [[ -f "$manifest" ]]; then
        if [[ "$module" != "trn_security" ]]; then
            if ! grep -q "trn_security" "$manifest"; then
                # Check if it has security files
                if ls "$module_path"/security/*.xml 2>/dev/null | head -1 | grep -q .; then
                    log_issue "WARNING" "$module" "GROUPS-DEPENDENCY" "$manifest" "Has security files but doesn't depend on trn_security"
                fi
            fi
        fi
    fi

    # Check for user-facing groups missing privilege_id
    for xml_file in "$module_path"/security/*.xml; do
        [[ -f "$xml_file" ]] || continue

        local in_group=false
        local has_privilege=false
        local has_name=false
        local group_id=""
        local group_name=""

        while IFS= read -r line; do
            if [[ "$line" =~ \<record.*model=\"res.groups\" ]] && [[ ! "$line" =~ model=\"res.groups.privilege\" ]]; then
                in_group=true
                has_privilege=false
                has_name=false
                group_id=$(echo "$line" | sed -n 's/.*id="\([^"]*\)".*/\1/p')
                [[ -z "$group_id" ]] && group_id="unknown"
                group_name=""
            elif [[ "$in_group" == true ]]; then
                if [[ "$line" =~ \<field.*name=\"privilege_id\" ]]; then
                    has_privilege=true
                fi
                if [[ "$line" =~ \<field.*name=\"name\" ]]; then
                    has_name=true
                    group_name=$(echo "$line" | sed -n 's/.*>\([^<]*\)<.*/\1/p')
                fi
                if [[ "$line" =~ \</record\> ]]; then
                    # Only check groups being DEFINED in this module (have a name field)
                    # Skip groups that are just being updated (e.g., adding implied_ids to another module's group)
                    if [[ "$has_name" == true && "$has_privilege" == false ]]; then
                        # Check if this looks like a user-facing group (not technical)
                        # Technical groups usually have names like "Registry: Read" or end with _read/_write
                        if [[ ! "$group_id" =~ _(read|write|create|delete)$ ]] && \
                           [[ ! "$group_name" =~ :\ (Read|Write|Create|Delete) ]] && \
                           [[ ! "$group_name" =~ \(Deprecated\) ]] && \
                           [[ ! "$group_id" =~ deprecated ]] && \
                           [[ ! "$group_id" =~ \. ]]; then  # Skip refs to other modules (e.g. module.group_name)
                            # This might be a user-facing group without privilege_id
                            log_issue "WARNING" "$module" "GROUPS-PRIVILEGE" "$xml_file" "Group '$group_id' may be user-facing but lacks privilege_id"
                        fi
                    fi
                    in_group=false
                fi
            fi
        done < "$xml_file"
    done
}

# ============================================================================
# CHECK 4: Legacy Patterns
# ============================================================================
check_legacy_patterns() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    # Check for modifications to base.group_user or base.group_erp_manager
    for xml_file in "$module_path"/security/*.xml; do
        [[ -f "$xml_file" ]] || continue

        # Check if modifying base groups (adding implied_ids is usually OK for linking)
        if grep -q 'id="base.group_erp_manager"' "$xml_file"; then
            log_issue "WARNING" "$module" "LEGACY-BASE-GROUP" "$xml_file" "Modifies base.group_erp_manager"
        fi
    done
}

# ============================================================================
# CHECK 5: Odoo 19 Compatibility
# ============================================================================
check_odoo19_compat() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    # Most Odoo 19 checks are already in check_security_groups
    # Add any additional checks here - use find for speed
    while IFS= read -r -d '' xml_file; do
        [[ "$xml_file" =~ /migration ]] && continue

        # Check for (6, 0, []) tuple syntax
        if grep -qE '\(6,\s*0,\s*\[' "$xml_file"; then
            log_issue "WARNING" "$module" "ODOO19-TUPLE" "$xml_file" "Uses (6, 0, []) tuple syntax - should use Command.set()"
        fi
    done < <(find "$module_path" -name "*.xml" -type f -print0 2>/dev/null)
}

# ============================================================================
# MAIN AUDIT LOOP
# ============================================================================
if [[ "$JSON_OUTPUT" == false && "$SUMMARY_ONLY" == false && "$COUNTS_ONLY" == false ]]; then
    echo "========================================"
    echo "Odoo Security Audit - V2 Compliance"
    echo "========================================"
    echo "Modules to audit: ${#MODULES[@]}"
    echo "Check type: $CHECK_TYPE"
    echo ""
fi

for module in "${MODULES[@]}"; do
    module_path="$ROOT_DIR/$module"

    [[ -d "$module_path" ]] || continue

    MODULE_ERRORS[$module]=0
    MODULE_WARNINGS[$module]=0

    if [[ "$JSON_OUTPUT" == false && "$SUMMARY_ONLY" == false && "$COUNTS_ONLY" == false ]]; then
        echo -e "${BLUE}[$module]${NC} Auditing..."
    fi

    case "$CHECK_TYPE" in
        all)
            check_acl_files "$module"
            check_record_rules "$module"
            check_security_groups "$module"
            check_legacy_patterns "$module"
            check_odoo19_compat "$module"
            ;;
        acl)
            check_acl_files "$module"
            ;;
        rules)
            check_record_rules "$module"
            ;;
        groups)
            check_security_groups "$module"
            ;;
        legacy)
            check_legacy_patterns "$module"
            ;;
        odoo19)
            check_security_groups "$module"
            check_odoo19_compat "$module"
            ;;
    esac

    if [[ "$JSON_OUTPUT" == false && "$SUMMARY_ONLY" == false && "$COUNTS_ONLY" == false ]]; then
        errors=${MODULE_ERRORS[$module]:-0}
        warnings=${MODULE_WARNINGS[$module]:-0}
        if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
            echo -e "${GREEN}[$module]${NC} OK"
        else
            echo -e "[$module] Errors: $errors, Warnings: $warnings"
        fi
        echo ""
    fi
done

# ============================================================================
# OUTPUT RESULTS
# ============================================================================

# Counts-only mode: just output "ERRORS WARNINGS" for easy parsing by scripts
if [[ "$COUNTS_ONLY" == true ]]; then
    echo "$TOTAL_ERRORS $TOTAL_WARNINGS"
    exit 0
fi

if [[ "$JSON_OUTPUT" == true ]]; then
    # Output as JSON
    echo "{"
    echo "  \"timestamp\": \"$(date -Iseconds)\","
    echo "  \"total_modules\": ${#MODULES[@]},"
    echo "  \"total_errors\": $TOTAL_ERRORS,"
    echo "  \"total_warnings\": $TOTAL_WARNINGS,"
    echo "  \"modules\": {"

    first=true
    for module in "${MODULES[@]}"; do
        errors=${MODULE_ERRORS[$module]:-0}
        warnings=${MODULE_WARNINGS[$module]:-0}

        if [[ "$first" == true ]]; then
            first=false
        else
            echo ","
        fi
        echo -n "    \"$module\": {\"errors\": $errors, \"warnings\": $warnings}"
    done

    echo ""
    echo "  },"
    echo "  \"issues\": ["

    first=true
    while IFS='|' read -r severity module check file message; do
        if [[ "$first" == true ]]; then
            first=false
        else
            echo ","
        fi
        echo -n "    {\"severity\": \"$severity\", \"module\": \"$module\", \"check\": \"$check\", \"file\": \"$file\", \"message\": \"$message\"}"
    done < "$ISSUES_FILE"

    echo ""
    echo "  ]"
    echo "}"
else
    # Print summary
    echo "========================================"
    echo "AUDIT SUMMARY"
    echo "========================================"
    echo "Total modules: ${#MODULES[@]}"
    echo -e "Total errors:   ${RED}$TOTAL_ERRORS${NC}"
    echo -e "Total warnings: ${YELLOW}$TOTAL_WARNINGS${NC}"
    echo ""

    # List modules with issues
    if [[ $TOTAL_ERRORS -gt 0 || $TOTAL_WARNINGS -gt 0 ]]; then
        echo "Modules with issues:"
        for module in "${MODULES[@]}"; do
            errors=${MODULE_ERRORS[$module]:-0}
            warnings=${MODULE_WARNINGS[$module]:-0}
            if [[ $errors -gt 0 || $warnings -gt 0 ]]; then
                echo -e "  $module: ${RED}$errors errors${NC}, ${YELLOW}$warnings warnings${NC}"
            fi
        done
        echo ""
    fi

    # Save detailed report
    {
        echo "# Odoo Security Audit Report"
        echo "Generated: $(date)"
        echo ""
        echo "## Summary"
        echo "- Total modules: ${#MODULES[@]}"
        echo "- Total errors: $TOTAL_ERRORS"
        echo "- Total warnings: $TOTAL_WARNINGS"
        echo ""
        echo "## Issues by Module"
        echo ""

        current_module=""
        while IFS='|' read -r severity module check file message; do
            if [[ "$module" != "$current_module" ]]; then
                current_module="$module"
                echo "### $module"
                echo ""
            fi
            echo "- **[$severity]** $check: $message"
            if [[ -n "$file" && "$file" != "-" ]]; then
                echo "  - File: \`$file\`"
            fi
        done < "$ISSUES_FILE"
    } > "$REPORT_DIR/audit-report.md"

    echo "Detailed report saved to: $REPORT_DIR/audit-report.md"
fi

# Exit with error if there are any errors
if [[ $TOTAL_ERRORS -gt 0 ]]; then
    exit 1
fi
