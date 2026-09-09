#!/bin/bash
# Audit all Odoo modules for compliance with docs/principles/
# Uses Cursor CLI with composer-1 model for fast, cost-effective analysis
#
# Prerequisites:
#   curl https://cursor.com/install -fsSL | bash
#   export CURSOR_API_KEY=your_key
#
# Usage:
#   ./scripts/audit-modules.sh                   # Audit all modules (report only)
#   ./scripts/audit-modules.sh trn_api      # Audit single module
#   ./scripts/audit-modules.sh --fix             # Auto-fix simple issues
#   ./scripts/audit-modules.sh --commit          # Auto-fix and commit each module

set -euo pipefail

ROOT_DIR="$(pwd)"
REPORT_DIR="$ROOT_DIR/reports/compliance"
MODEL="composer-1"
FIX_MODE=""
SHOW_DETAILS=false
AUTO_COMMIT=false
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

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix) FIX_MODE="--force"; shift ;;
        --commit) AUTO_COMMIT=true; FIX_MODE="--force"; shift ;;
        --model) MODEL="$2"; shift 2 ;;
        --details) SHOW_DETAILS=true; shift ;;
        *) MODULES+=("$1"); shift ;;
    esac
done

mkdir -p "$REPORT_DIR"

if [[ -n "$FIX_MODE" ]]; then
    echo "Auto-fix mode: ON (the agent may modify module files; see auto_fixed[] in reports)"
else
    echo "Auto-fix mode: OFF (report-only; no files will be modified by the agent)"
fi

AUDIT_PROMPT='Audit this Odoo module for compliance with project principles.

You are given the full contents of the relevant docs/principles/*.md files inline below.
Use ONLY this inlined material for the principles; do not open or read any additional
documentation files from disk.

Check for:
1. Naming: module/model/field names follow trn_*/trn.* conventions
2. Security: ir.model.access.csv exists and is complete
3. No print() statements - should use _logger
4. No bare except: clauses
5. No cr.commit() in loops - should use queue_job
6. No PII (names, IDs, phone numbers) in log messages
7. Tests exist for core functionality
8. Logging must use lazy formatting - NO f-strings or % formatting in _logger calls
   BAD:  _logger.info(f"Processing {name}")
   BAD:  _logger.info("Processing %s" % name)
   GOOD: _logger.info("Processing %s", name)

OUTPUT REQUIREMENTS (CRITICAL):
- Return ONLY a single JSON object, with no markdown, no code fences, and no prose before or after it.
- The JSON MUST conform to this schema:
  {
    "module": "module_name",
    "status": "pass|fail|partial",
    "issues": [{"severity": "high|medium|low", "file": "path", "line": N, "message": "..."}],
    "auto_fixed": ["description of fix"],
    "summary": "one line summary"
  }
- Do NOT wrap the JSON in ``` fences.
- Do NOT include headings or narrative text outside the JSON object.'

DOC_FILES=(
    "$ROOT_DIR/docs/principles/naming-conventions.md"
    "$ROOT_DIR/docs/principles/access-rights.md"
    "$ROOT_DIR/docs/principles/module-architecture.md"
    "$ROOT_DIR/docs/principles/api-design.md"
    "$ROOT_DIR/docs/principles/performance-scalability.md"
    "$ROOT_DIR/docs/principles/testing.md"
    "$ROOT_DIR/docs/principles/approval-workflows.md"
    "$ROOT_DIR/docs/principles/error-handling.md"
    "$ROOT_DIR/docs/principles/audit-compliance.md"
)

audit_module() {
    local module_path=$1
    local module_name=$(basename "$module_path")
    local report_file="$REPORT_DIR/${module_name}.json"

    echo "[$module_name] Starting audit..."

    # Build a combined prompt that includes core instructions plus key docs
    local prompt_file
    prompt_file="$(mktemp "${REPORT_DIR}/${module_name}.prompt.XXXXXX")"
    {
        printf '%s\n\n' "$AUDIT_PROMPT"
        if [[ -n "$FIX_MODE" ]]; then
            printf '%s\n\n' "You are running in AUTO-FIX MODE. When you find clear, mechanical issues that can be safely corrected (e.g. logging style, missing security CSV entries, obvious PII in logs or tests), you may directly modify the module files. After making changes, describe each applied edit in the auto_fixed[] list with filenames and a short description. Do NOT make large refactors or behavior changes. Do NOT create separate audit report files (e.g. AUDIT_REPORT.json); only return the single JSON object described above."
        else
            printf '%s\n\n' "You are running in REPORT-ONLY MODE. Do NOT modify any files. Only report issues in the JSON output. Do NOT create any report files; only return the single JSON object described above."
        fi
        for doc in "${DOC_FILES[@]}"; do
            if [[ -f "$doc" ]]; then
                printf '===== FILE: %s =====\n\n' "${doc#$ROOT_DIR/}"
                cat "$doc"
                printf '\n\n'
            fi
        done
    } > "$prompt_file"

    # Run AI agent from within the module directory:
    # - cd into the module so relative paths work
    # - Write JSON response to the module report file
    # - Leave stderr on the terminal so failures are visible to the user
    if [[ -z "$AI_AGENT" ]]; then
        echo "[$module_name] No AI agent available (install 'cursor-agent' or 'claude', or set AI_AGENT_CMD)"
        echo '{"module": "'"$module_name"'", "status": "error", "issues": [], "auto_fixed": [], "summary": "Audit skipped: no AI agent available"}' > "$report_file"
        rm -f "$prompt_file"
        return 0
    fi

    if (
        cd "$module_path" && \
        $AI_AGENT -p \
            --output-format json \
            --model "$MODEL" \
            $FIX_MODE \
            "$(cat "$prompt_file")"
    ) > "$report_file"; then

        # Normalize cursor-agent output into a simple audit JSON schema
        # If the file already has a top-level "status", keep it.
        # Otherwise, derive "status" heuristically from the "result" text.
        if ! jq -e '.status' "$report_file" >/dev/null 2>&1; then
            local tmp_file="${report_file}.tmp"
            if jq --arg module "$module_name" '
                def infer_status:
                  if (.result // "" | test("Status:\\s*PASS"; "i")) then "pass"
                  elif (.result // "" | test("Status:\\s*PARTIAL"; "i")) then "partial"
                  elif (.result // "" | test("Status:\\s*FAIL"; "i")) then "fail"
                  # If the model did not return an explicit status line, treat this as a partial audit
                  else "partial" end;
                {
                  module: $module,
                  status: infer_status,
                  issues: [],
                  auto_fixed: [],
                  summary: "Audit status (inferred): " + (infer_status),
                  inferred_status: true,
                  raw_result: (.result // "")
                }
            ' "$report_file" > "$tmp_file"; then
                mv "$tmp_file" "$report_file"
            else
                rm -f "$tmp_file"
            fi
        fi

        local status summary issue_count high_count inferred auto_fixed_count
        status=$(jq -r '.status // "unknown"' "$report_file" 2>/dev/null || echo "error")
        summary=$(jq -r '.summary // "No summary provided"' "$report_file" 2>/dev/null || echo "")
        issue_count=$(jq -r '.issues | length' "$report_file" 2>/dev/null || echo "0")
        high_count=$(jq -r '[.issues[]? | select(.severity == "high")] | length' "$report_file" 2>/dev/null || echo "0")
        inferred=$(jq -r '.inferred_status // false' "$report_file" 2>/dev/null || echo "false")
        auto_fixed_count=$(jq -r '.auto_fixed | length' "$report_file" 2>/dev/null || echo "0")

        if [[ "$inferred" == "true" ]]; then
            echo "[$module_name] Done: $status (issues: $issue_count, high: $high_count, auto_fixed: $auto_fixed_count, inferred from model output)"
            # Optional verbose explanation from the model, controlled by --details
            if [[ "$SHOW_DETAILS" == true ]]; then
                local raw_preview
                raw_preview=$(jq -r '.raw_result // ""' "$report_file" 2>/dev/null || echo "")
                if [[ -n "$raw_preview" ]]; then
                    echo "[$module_name] Details (from model):"
                    # Show the first ~40 lines to avoid flooding the terminal
                    printf '%s\n' "$raw_preview" | head -n 40 | sed 's/^/  /'
                fi
            fi
        else
            echo "[$module_name] Done: $status (issues: $issue_count, high: $high_count, auto_fixed: $auto_fixed_count)"
        fi
        if [[ -n "$summary" ]]; then
            echo "[$module_name] Summary: $summary"
        fi

        # Auto-commit fixes if --commit flag was passed and fixes were made
        if [[ "$AUTO_COMMIT" == true && "$auto_fixed_count" -gt 0 ]]; then
            echo "[$module_name] Committing fixes..."
            if (cd "$module_path" && git add -A && git diff --cached --quiet); then
                echo "[$module_name] No changes to commit"
            else
                local commit_msg="fix($module_name): auto-fix compliance issues

Auto-fixed by audit-modules.sh:
$(jq -r '.auto_fixed[]? // empty' "$report_file" | sed 's/^/- /')"
                if (cd "$module_path" && git commit -m "$commit_msg"); then
                    echo "[$module_name] Committed fixes"
                else
                    echo "[$module_name] Failed to commit fixes"
                fi
            fi
        fi
    else
        echo "[$module_name] Error: audit failed"
        echo '{"module": "'"$module_name"'", "status": "error", "issues": [], "summary": "Audit failed"}' > "$report_file"
    fi

    # Clean up temporary prompt file and any stray audit reports the agent might have written
    rm -f "$prompt_file"
    rm -f "$module_path"/AUDIT_REPORT.json "$module_path"/audit_report.json 2>/dev/null || true
}

# Get modules to audit
if [[ ${#MODULES[@]} -eq 0 ]]; then
    mapfile -t MODULES < <(find . -maxdepth 1 -type d -print | while IFS= read -r d; do
        [[ -f "$d/__manifest__.py" ]] && echo "$d"
    done | sort)
fi

echo "Auditing ${#MODULES[@]} modules with agent=${AI_AGENT:-none} model=$MODEL"
echo "Reports will be saved to $REPORT_DIR/"
echo ""

# Run audits sequentially
for module in "${MODULES[@]}"; do
    audit_module "$module"
done

# Generate summary report
echo ""
echo "Generating summary..."

jq -s '{
    timestamp: now | todate,
    total: length,
    passed: [.[] | select(.status == "pass")] | length,
    failed: [.[] | select(.status == "fail")] | length,
    partial: [.[] | select(.status == "partial")] | length,
    errors: [.[] | select(.status == "error")] | length,
    high_severity_issues: [.[].issues[]? | select(.severity == "high")] | length,
    modules: [.[] | {module, status, summary, issue_count: (.issues | length)}]
}' "$REPORT_DIR"/*.json > "$REPORT_DIR/summary.json"

# Print summary
echo ""
echo "=== AUDIT SUMMARY ==="
jq -r '"Total: \(.total) | Passed: \(.passed) | Failed: \(.failed) | Partial: \(.partial) | Errors: \(.errors)"' "$REPORT_DIR/summary.json"
jq -r '"High severity issues: \(.high_severity_issues)"' "$REPORT_DIR/summary.json"
echo ""
echo "Failed modules:"
jq -r '.modules[] | select(.status == "fail") | "  - \(.module): \(.summary)"' "$REPORT_DIR/summary.json"
echo ""
echo "Full report: $REPORT_DIR/summary.json"
