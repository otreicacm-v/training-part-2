#!/bin/bash
# Fix access rights compliance issues in Odoo modules
# Embeds audit logic directly to avoid subprocess parsing issues.
#
# Usage:
#   ./scripts/fix-security.sh trn_api                    # Fix single module
#   ./scripts/fix-security.sh trn_api trn_vocabulary # Fix multiple modules
#   ./scripts/fix-security.sh --all                            # Fix all modules with issues
#   ./scripts/fix-security.sh --dry-run trn_api          # Show what would be fixed
#   ./scripts/fix-security.sh --mechanical-only trn_api  # Only do mechanical fixes (no AI)
#   ./scripts/fix-security.sh --details trn_api          # Show detailed output

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="$ROOT_DIR/reports/security"
FIX_REPORT_DIR="$ROOT_DIR/reports/security-fixes"
MODEL="composer-1"
DRY_RUN=false
MECHANICAL_ONLY=false
FIX_ALL=false
SHOW_DETAILS=false
MODULES=()

# Find AI agent command (prefer cursor-agent, then claude)
find_ai_agent() {
    if [[ -n "${AI_AGENT_CMD:-}" ]]; then
        echo "$AI_AGENT_CMD"
    elif command -v cursor-agent >/dev/null 2>&1; then
        echo "cursor-agent"
    elif command -v claude >/dev/null 2>&1; then
        echo "claude"
    else
        echo ""
    fi
}

AI_AGENT=$(find_ai_agent)

# Colors
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --mechanical-only) MECHANICAL_ONLY=true; shift ;;
        --all) FIX_ALL=true; shift ;;
        --model) MODEL="$2"; shift 2 ;;
        --details) SHOW_DETAILS=true; shift ;;
        *) MODULES+=("${1%/}"); shift ;;  # Accept any module name; strip trailing slash
    esac
done

mkdir -p "$FIX_REPORT_DIR" "$REPORT_DIR"

# ============================================================================
# EMBEDDED AUDIT LOGIC (from audit-security.sh)
# ============================================================================

# Module-level counters (reset per module)
AUDIT_ERRORS=0
AUDIT_WARNINGS=0
AUDIT_OUTPUT=""

reset_audit_counters() {
    AUDIT_ERRORS=0
    AUDIT_WARNINGS=0
    AUDIT_OUTPUT=""
}

log_audit_issue() {
    local severity=$1
    local check=$2
    local file=$3
    local message=$4

    if [[ "$severity" == "ERROR" ]]; then
        AUDIT_ERRORS=$(( AUDIT_ERRORS + 1 ))
        AUDIT_OUTPUT+="  [ERROR] $check: $message"$'\n'
    else
        AUDIT_WARNINGS=$(( AUDIT_WARNINGS + 1 ))
        AUDIT_OUTPUT+="  [WARN] $check: $message"$'\n'
    fi
    if [[ -n "$file" && "$file" != "-" ]]; then
        AUDIT_OUTPUT+="         File: $file"$'\n'
    fi
}

audit_acl_files() {
    local module=$1
    local module_path="$ROOT_DIR/$module"
    local acl_file="$module_path/security/ir.model.access.csv"

    if [[ ! -f "$acl_file" ]]; then
        local has_models=false
        if grep -rq "_name = ['\"]tpl\." "$module_path"/*.py 2>/dev/null || \
           grep -rq "_name = ['\"]tpl\." "$module_path"/models/*.py 2>/dev/null; then
            has_models=true
        fi
        if [[ "$has_models" == true ]]; then
            log_audit_issue "WARNING" "ACL" "-" "Module defines models but has no ir.model.access.csv"
        fi
        return
    fi

    while IFS=, read -r id name model_id group_id perm_read perm_write perm_create perm_unlink; do
        [[ "$id" == "id" || -z "$id" ]] && continue
        if [[ ! "$id" =~ ^access_ ]]; then
            log_audit_issue "WARNING" "ACL-NAMING" "$acl_file" "Entry '$id' doesn't follow 'access_{model}_{group}' pattern"
        fi
    done < "$acl_file"
}

audit_record_rules() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    for xml_file in "$module_path"/security/*.xml; do
        [[ -f "$xml_file" ]] || continue

        if grep -q 'model="ir.rule"' "$xml_file"; then
            if ! grep -q 'noupdate="1"' "$xml_file" && ! grep -q "noupdate='1'" "$xml_file"; then
                log_audit_issue "WARNING" "RULES-NOUPDATE" "$xml_file" "Record rules should be wrapped in <data noupdate=\"1\">"
            fi
        fi

        if grep -q 'domain_force.*\[\]' "$xml_file" || grep -q "domain_force.*\[\s*\]" "$xml_file"; then
            if grep -q 'perm_write.*1' "$xml_file" || grep -q 'perm_create.*1' "$xml_file" || grep -q 'perm_unlink.*1' "$xml_file"; then
                log_audit_issue "ERROR" "RULES-EMPTY-DOMAIN" "$xml_file" "Empty domain_force [] with write/create/unlink is forbidden"
            fi
        fi

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
                        log_audit_issue "WARNING" "RULES-NO-GROUP" "$xml_file" "Rule '$rule_id' has no groups and is not global"
                    fi
                    in_rule=false
                fi
            fi
        done < "$xml_file"
    done
}

audit_security_groups() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    for xml_file in "$module_path"/security/*.xml; do
        [[ -f "$xml_file" ]] || continue

        local in_group=false
        local group_id=""

        while IFS= read -r line; do
            if [[ "$line" =~ \<record.*model=\"res.groups\" ]] && [[ ! "$line" =~ model=\"res.groups.privilege\" ]]; then
                in_group=true
                group_id=$(echo "$line" | sed -n 's/.*id="\([^"]*\)".*/\1/p')
                [[ -z "$group_id" ]] && group_id="unknown"
            elif [[ "$in_group" == true ]]; then
                if [[ "$line" =~ \<field.*name=\"category_id\" ]]; then
                    log_audit_issue "ERROR" "GROUPS-CATEGORY" "$xml_file" "Group '$group_id' uses category_id (Odoo 19 violation)"
                fi
                if [[ "$line" =~ \</record\> ]]; then
                    in_group=false
                fi
            fi
        done < "$xml_file"

        if grep -q 'name="users"' "$xml_file" && grep -q 'model="res.groups"' "$xml_file"; then
            log_audit_issue "ERROR" "GROUPS-USERS-FIELD" "$xml_file" "Uses 'users' field instead of 'user_ids' (Odoo 19)"
        fi

        if grep -qE '\(4,\s*ref\(' "$xml_file" || grep -qE '\[\s*\(4,' "$xml_file"; then
            log_audit_issue "ERROR" "GROUPS-TUPLE-SYNTAX" "$xml_file" "Uses old tuple syntax (4, ref()) - should use Command.link()"
        fi

        if grep -q 'name="groups_id"' "$xml_file"; then
            log_audit_issue "ERROR" "MENU-GROUPS-FIELD" "$xml_file" "Uses 'groups_id' instead of 'group_ids' (Odoo 19)"
        fi

        # Replace trn_security with your project's security module name
        if [[ "$module" != "trn_security" ]]; then
            if grep -q 'model="ir.module.category"' "$xml_file"; then
                log_audit_issue "WARNING" "GROUPS-CATEGORY-DEF" "$xml_file" "Defines ir.module.category (should only be in trn_security)"
            fi
        fi
    done

    local manifest="$module_path/__manifest__.py"
    # Replace trn_security with your project's security module name
    if [[ -f "$manifest" && "$module" != "trn_security" ]]; then
        if ! grep -q "trn_security" "$manifest"; then
            if ls "$module_path"/security/*.xml 2>/dev/null | head -1 | grep -q .; then
                log_audit_issue "WARNING" "GROUPS-DEPENDENCY" "$manifest" "Has security files but doesn't depend on trn_security"
            fi
        fi
    fi

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
                    if [[ "$has_name" == true && "$has_privilege" == false ]]; then
                        if [[ ! "$group_id" =~ _(read|write|create|delete)$ ]] && \
                           [[ ! "$group_name" =~ :\ (Read|Write|Create|Delete) ]] && \
                           [[ ! "$group_name" =~ \(Deprecated\) ]] && \
                           [[ ! "$group_id" =~ deprecated ]] && \
                           [[ ! "$group_id" =~ \. ]]; then
                            log_audit_issue "WARNING" "GROUPS-PRIVILEGE" "$xml_file" "Group '$group_id' may be user-facing but lacks privilege_id"
                        fi
                    fi
                    in_group=false
                fi
            fi
        done < "$xml_file"
    done
}

audit_legacy_patterns() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    for xml_file in "$module_path"/security/*.xml; do
        [[ -f "$xml_file" ]] || continue
        if grep -q 'id="base.group_erp_manager"' "$xml_file"; then
            log_audit_issue "WARNING" "LEGACY-BASE-GROUP" "$xml_file" "Modifies base.group_erp_manager"
        fi
    done
}

audit_odoo19_compat() {
    local module=$1
    local module_path="$ROOT_DIR/$module"

    while IFS= read -r -d '' xml_file; do
        [[ "$xml_file" =~ /migration ]] && continue
        if grep -qE '\(6,\s*0,\s*\[' "$xml_file"; then
            log_audit_issue "WARNING" "ODOO19-TUPLE" "$xml_file" "Uses (6, 0, []) tuple syntax - should use Command.set()"
        fi
    done < <(find "$module_path" -name "*.xml" -type f -print0 2>/dev/null)
}

run_audit() {
    local module=$1
    reset_audit_counters
    audit_acl_files "$module"
    audit_record_rules "$module"
    audit_security_groups "$module"
    audit_legacy_patterns "$module"
    audit_odoo19_compat "$module"
}

# ============================================================================
# MECHANICAL FIXES (No AI required)
# ============================================================================
fix_tuple_syntax() {
    local file=$1

    if [[ "$DRY_RUN" == true ]]; then
        echo "    [DRY-RUN] Would fix tuple syntax in $file"
        return 0
    fi

    sed -i.bak -E "s/\(4,\s*ref\((['\"][^'\"]+['\"])\)\)/Command.link(ref(\1))/g" "$file"
    sed -i.bak -E "s/\[\(4,\s*ref\((['\"][^'\"]+['\"])\)\)\]/[Command.link(ref(\1))]/g" "$file"
    sed -i.bak -E "s/\(6,\s*0,\s*\[([^\]]*)\]\)/Command.set([\1])/g" "$file"

    rm -f "$file.bak"
    echo "    Fixed tuple syntax in $file"
    return 0
}

fix_users_to_user_ids() {
    local file=$1

    if [[ "$DRY_RUN" == true ]]; then
        echo "    [DRY-RUN] Would fix users -> user_ids in $file"
        return 0
    fi

    sed -i.bak 's/name="users"/name="user_ids"/g' "$file"
    rm -f "$file.bak"
    echo "    Fixed users -> user_ids in $file"
    return 0
}

fix_groups_id_to_group_ids() {
    local file=$1

    if [[ "$DRY_RUN" == true ]]; then
        echo "    [DRY-RUN] Would fix groups_id -> group_ids in $file"
        return 0
    fi

    sed -i.bak 's/name="groups_id"/name="group_ids"/g' "$file"
    rm -f "$file.bak"
    echo "    Fixed groups_id -> group_ids in $file"
    return 0
}


# ============================================================================
# BUILD PROMPT FOR CURSOR-AGENT
# ============================================================================
build_prompt() {
    local module=$1
    local module_path=$2
    local audit_output=$3

    cat <<'PROMPT_EOF'
You are an Odoo 19 security expert.

Goal: Fix the access rights compliance issues reported for this module while preserving behavior.

## V2 Access Rights Principles

### Three-Tier Architecture
```
TIER 1: ROLES (Composite)           ← Cross-domain, optional
├── role_trn_field_officer
└── role_trn_supervisor

TIER 2: FUNCTIONAL PRIVILEGES       ← User-facing, per domain
├── group_{domain}_viewer
├── group_{domain}_officer
└── group_{domain}_manager

TIER 3: BASE PERMISSIONS            ← Technical, granular
├── group_{domain}_read
├── group_{domain}_write
└── group_{domain}_create
```

### Odoo 19 Requirements
- Use `privilege_id` on user-facing res.groups (NOT category_id)
- Use `user_ids` not `users` field on res.groups
- Use `group_ids` not `groups_id` on menus
- Use `Command.link(ref('...'))` not `(4, ref('...'))`
- Use `Command.set([...])` not `(6, 0, [...])`

### ACL Entry ID Naming Convention
ACL entry IDs MUST follow the pattern: `access_{model}_{group}`
- `{model}` - Model name with underscores (e.g., `trn_program`, `res_partner`)
- `{group}` - Short group identifier (e.g., `viewer`, `officer`, `manager`, `admin`)

Examples:
```csv
access_trn_{domain}_officer,trn.{domain} officer,trn_{domain}.model_trn_{domain},group_{domain}_officer,1,1,1,0
access_res_partner_{domain}_viewer,res.partner viewer,base.model_res_partner,group_{domain}_viewer,1,0,0,0
```

Anti-patterns to fix:
- `user_access_trn_api_log` → `access_trn_api_log_user` (no prefix)
- `trn_area_admin` → `access_trn_area_admin`
- `attendance_subscriber_manager` → `access_trn_attendance_subscriber_manager`

### Record Rules Requirements
1. Never use empty domains `[]` with write/create/unlink permissions
2. Always specify `groups` field OR use `global="True"`
3. Use explicit "see all" pattern: `[(1, '=', 1)]` not `[]`
4. Wrap ir.rule records in `<data noupdate="1">`

### Namespace Requirements
- All XML IDs must use `trn_*` prefix
- All model references must use `trn.*`

## Instructions

1. Read the audit output below and fix ALL issues in this module
2. For ACL naming violations:
   - Rename the entry ID to follow `access_{model}_{group}` pattern
   - Keep the same permissions and group reference
   - The `name` field (display name) can stay descriptive
3. For groups missing privilege_id:
   - If this is a user-facing group (not technical _read/_write), add privilege_id
   - You may need to create a res.groups.privilege record first
4. For record rules issues:
   - Add noupdate wrapper if missing
   - Add explicit groups or global="True"
   - Replace empty domains with [(1, '=', 1)] if needed
5. Make minimal changes - do NOT refactor unrelated code
6. Preserve all existing permissions and business logic

## Common Pitfalls (IMPORTANT)

### ACL Renaming
- ACL entry IDs are rarely referenced by other modules, so renaming is usually safe
- However, SEARCH the codebase for the old ID before renaming: `grep -r "old_acl_id" --include="*.xml" --include="*.py"`
- If found, you must update those references too (may be in other modules)

### Group ID Changes
- Group IDs ARE frequently referenced across modules in:
  - `implied_ids` fields (group inheritance)
  - `group_id:id` in ACL CSV files
  - `groups` attribute on menu items
  - `groups` field on ir.rule records
  - Python code: `self.env.ref('module.group_id')`
- Before renaming a group ID, search: `grep -r "group_id_name" --include="*.xml" --include="*.csv" --include="*.py"`
- If cross-module references exist, DO NOT rename - just add the fix (like privilege_id) to existing ID

### Adding privilege_id
- You must first create a `res.groups.privilege` record before referencing it
- Pattern:
  ```xml
  <record id="privilege_module_officer" model="res.groups.privilege">
      <field name="name">Module Officer</field>
      <field name="category_id" ref="trn_security.module_category_tpl"/>
  </record>
  <record id="group_module_officer" model="res.groups">
      <field name="name">Officer</field>
      <field name="privilege_id" ref="privilege_module_officer"/>
  </record>
  ```
- The privilege should be in the same file, BEFORE the group that references it

### Record Rules
- Adding `global="True"` means ALL users get this rule (even without groups)
- If a rule should only apply to specific groups, use `groups` field instead
- When adding noupdate wrapper, wrap ONLY the ir.rule records, not the whole file

## Verification Checklist (for reviewer)

After AI makes changes, verify:

1. [ ] **No broken references**: Search for old IDs in other modules
   ```bash
   grep -r "OLD_ID" ../ --include="*.xml" --include="*.csv" --include="*.py"
   ```

2. [ ] **Privilege records exist**: If privilege_id was added, check the privilege record exists

3. [ ] **ACL permissions unchanged**: Compare old vs new CSV - same read/write/create/unlink values

4. [ ] **Group inheritance intact**: Check implied_ids weren't accidentally removed

5. [ ] **Record rule security**: Verify rules don't accidentally grant broader access
   - `global="True"` + `perm_write=1` is dangerous unless domain restricts it

6. [ ] **XML syntax valid**: Run `python -c "import xml.etree.ElementTree as ET; ET.parse('file.xml')"`

7. [ ] **Module installs**: If possible, test module installation in Odoo

PROMPT_EOF

    echo ""
    echo "## Module Information"
    echo ""
    echo "- Module: $module"
    echo "- Path: $module_path"
    echo ""
    echo "## Audit Output"
    echo ""
    echo '```'
    echo "$audit_output"
    echo '```'
}

# ============================================================================
# FIX MODULE
# ============================================================================
fix_module() {
    local module="${1%/}"  # Strip trailing slash
    local module_path="$ROOT_DIR/$module"
    local fixes_made=0
    local fix_log="$FIX_REPORT_DIR/${module}.log"
    local audit_report="$REPORT_DIR/${module}-audit.txt"

    [[ -d "$module_path" ]] || return 0

    echo -e "${BLUE}[$module]${NC} Running audit..."
    : > "$fix_log"

    # Run embedded audit
    run_audit "$module"
    local error_count=$AUDIT_ERRORS
    local warning_count=$AUDIT_WARNINGS
    local audit_output="$AUDIT_OUTPUT"

    # Save audit output
    echo "$audit_output" > "$audit_report"

    if [[ $error_count -eq 0 && $warning_count -eq 0 ]]; then
        echo -e "${GREEN}[$module]${NC} No issues found"
        return 0
    fi

    echo -e "${YELLOW}[$module]${NC} Found $error_count errors, $warning_count warnings"

    # Apply mechanical fixes first
    if [[ "$DRY_RUN" == false ]]; then
        echo "[$module] Applying mechanical fixes..."

        # Fix 1: Tuple syntax (4, ref()) -> Command.link()
        for xml_file in "$module_path"/security/*.xml "$module_path"/views/*.xml; do
            [[ -f "$xml_file" ]] || continue
            if grep -qE '\(4,\s*ref\(' "$xml_file" || grep -qE '\(6,\s*0,\s*\[' "$xml_file"; then
                if fix_tuple_syntax "$xml_file"; then
                    ((fixes_made++)) || true
                    echo "  - Fixed tuple syntax: $xml_file" >> "$fix_log"
                fi
            fi
        done

        # Fix 2: users -> user_ids
        for xml_file in "$module_path"/security/*.xml; do
            [[ -f "$xml_file" ]] || continue
            if grep -q 'name="users"' "$xml_file" && grep -q 'model="res.groups"' "$xml_file"; then
                if fix_users_to_user_ids "$xml_file"; then
                    ((fixes_made++)) || true
                    echo "  - Fixed users -> user_ids: $xml_file" >> "$fix_log"
                fi
            fi
        done

        # Fix 3: groups_id -> group_ids
        for xml_file in "$module_path"/**/*.xml; do
            [[ -f "$xml_file" ]] || continue
            if grep -q 'name="groups_id"' "$xml_file"; then
                if fix_groups_id_to_group_ids "$xml_file"; then
                    ((fixes_made++)) || true
                    echo "  - Fixed groups_id -> group_ids: $xml_file" >> "$fix_log"
                fi
            fi
        done

        if [[ $fixes_made -gt 0 ]]; then
            echo -e "${GREEN}[$module]${NC} Applied $fixes_made mechanical fixes"
        fi
    fi

    # Re-run audit after mechanical fixes
    if [[ "$DRY_RUN" == false && $fixes_made -gt 0 ]]; then
        run_audit "$module"
        error_count=$AUDIT_ERRORS
        warning_count=$AUDIT_WARNINGS
        audit_output="$AUDIT_OUTPUT"
        echo "$audit_output" > "$audit_report"

        if [[ $error_count -eq 0 && $warning_count -eq 0 ]]; then
            echo -e "${GREEN}[$module]${NC} All issues fixed by mechanical fixes"
            return 0
        fi
        echo -e "${YELLOW}[$module]${NC} After mechanical fixes: $error_count errors, $warning_count warnings remain"
    fi

    # Skip AI fixes if mechanical-only mode
    if [[ "$MECHANICAL_ONLY" == true ]]; then
        echo "[$module] Skipping AI fixes (--mechanical-only)"
        if [[ "$SHOW_DETAILS" == true ]]; then
            echo "[$module] Remaining issues:"
            echo "$audit_output" | sed 's/^/  /'
        fi
        return 0
    fi

    # Skip if dry run
    if [[ "$DRY_RUN" == true ]]; then
        echo "[$module] [DRY-RUN] Would invoke ${AI_AGENT:-AI agent} to fix remaining issues"
        return 0
    fi

    # Check if an AI agent is available
    if [[ -z "$AI_AGENT" ]]; then
        echo -e "${YELLOW}[$module]${NC} No AI agent available - skipping AI fixes"
        echo "         Install 'cursor-agent' or 'claude', or set AI_AGENT_CMD environment variable."
        if [[ "$SHOW_DETAILS" == true ]]; then
            echo "[$module] Remaining issues:"
            echo "$audit_output" | sed 's/^/  /'
        fi
        return 0
    fi

    # AI-assisted fixes with retry loop (similar to fix-lint.sh)
    local max_rounds=2
    local round

    for round in $(seq 1 "$max_rounds"); do
        echo -e "${BLUE}[$module]${NC} Invoking $AI_AGENT (round $round/$max_rounds)..."

        # Build the prompt
        local prompt
        prompt=$(build_prompt "$module" "$module_path" "$audit_output")

        # Save prompt for debugging
        echo "$prompt" > "$FIX_REPORT_DIR/${module}-prompt-round${round}.md"

        # Run AI agent from within the module directory
        if (
            cd "$module_path" && \
            $AI_AGENT -p \
                --model "$MODEL" \
                --force \
                "$prompt"
        ) >> "$fix_log" 2>&1; then
            echo "[$module] $AI_AGENT completed for round $round. Re-running audit..."

            # Re-run embedded audit
            run_audit "$module"
            error_count=$AUDIT_ERRORS
            warning_count=$AUDIT_WARNINGS
            audit_output="$AUDIT_OUTPUT"
            echo "$audit_output" > "$audit_report"

            if [[ $error_count -eq 0 && $warning_count -eq 0 ]]; then
                echo -e "${GREEN}[$module]${NC} All issues fixed after $AI_AGENT round $round"
                return 0
            fi

            echo -e "${YELLOW}[$module]${NC} After round $round: $error_count errors, $warning_count warnings remain"
        else
            echo -e "${RED}[$module]${NC} $AI_AGENT failed in round $round; see $fix_log"
            break
        fi
    done

    # Final status
    if [[ $error_count -gt 0 || $warning_count -gt 0 ]]; then
        echo -e "${YELLOW}[$module]${NC} Issues remain after $max_rounds rounds; manual review needed"
        echo "         Audit report: $audit_report"
        echo "         Fix log: $fix_log"
        if [[ "$SHOW_DETAILS" == true ]]; then
            echo "[$module] Remaining issues:"
            echo "$audit_output" | sed 's/^/  /'
        fi
    fi
}

# ============================================================================
# MAIN
# ============================================================================

# If --all, run audit on all modules and pick those with issues
if [[ "$FIX_ALL" == true ]]; then
    echo "Scanning for modules with issues..."
    while IFS= read -r -d '' module_dir; do
        module=$(basename "$module_dir")
        run_audit "$module"
        if [[ $AUDIT_ERRORS -gt 0 || $AUDIT_WARNINGS -gt 0 ]]; then
            MODULES+=("$module")
        fi
    done < <(find "$ROOT_DIR" -maxdepth 1 -type d -print0 2>/dev/null | while IFS= read -r -d '' d; do
        [[ -f "$d/__manifest__.py" ]] && printf '%s\0' "$d"
    done)
    echo "Found ${#MODULES[@]} modules with issues"
fi

if [[ ${#MODULES[@]} -eq 0 ]]; then
    echo "No modules specified. Usage: $0 [--all | --dry-run | --mechanical-only | --details] <module> [...]"
    exit 1
fi

echo "========================================"
echo "Odoo Security Fixer - V2 Compliance"
echo "========================================"
echo "Modules to fix: ${#MODULES[@]}"
echo "Dry run: $DRY_RUN"
echo "Mechanical only: $MECHANICAL_ONLY"
echo "AI Agent: ${AI_AGENT:-none}"
echo "Model: $MODEL"
echo ""

for module in "${MODULES[@]}"; do
    fix_module "$module"
    echo ""
done

echo "========================================"
echo "Fix Summary"
echo "========================================"
echo "Modules processed: ${#MODULES[@]}"
echo "Fix logs saved to: $FIX_REPORT_DIR/"
echo ""
echo "Run './scripts/audit-security.sh' to verify remaining issues"
