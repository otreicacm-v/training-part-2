#!/bin/bash
# Run key linters (based on .pre-commit-config.yaml) for one or more Odoo modules.
# If linters report remaining issues, call an AI agent to help fix them.
#
# Usage:
#   ./scripts/fix-lint.sh trn_vocabulary
#   ./scripts/fix-lint.sh trn_vocabulary trn_inventory
#   ./scripts/fix-lint.sh --model composer-1 --details trn_vocabulary
#   ./scripts/fix-lint.sh --lint-only trn_vocabulary  # Skip AI fixing
#
# Environment variables:
#   AI_AGENT_CMD - Command to run AI agent (default: cursor-agent or claude if found)
#   AI_AGENT_MODEL - Default model to use (can be overridden with --model)
#
# Notes:
# - This script focuses on Python + JS/TS linters (ruff, pylint-odoo, eslint, prettier).
# - It does NOT run full pre-commit (no OCA meta-hooks, gitleaks, etc.).

set -euo pipefail

ROOT_DIR="$(pwd)"
LINT_REPORT_DIR="$ROOT_DIR/reports/lint"
MODEL="${AI_AGENT_MODEL:-composer-1}"
SHOW_DETAILS=false
LINT_ONLY=false
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

while [[ $# -gt 0 ]]; do
    case $1 in
        --model) MODEL="$2"; shift 2 ;;
        --details) SHOW_DETAILS=true; shift ;;
        --lint-only) LINT_ONLY=true; shift ;;
        *)
            # Accept any directory that contains a __manifest__.py (i.e. any Odoo module)
            if [[ -d "${1%/}" && -f "${1%/}/__manifest__.py" ]]; then
                MODULES+=("${1%/}")
            elif [[ -d "$ROOT_DIR/${1%/}" && -f "$ROOT_DIR/${1%/}/__manifest__.py" ]]; then
                MODULES+=("${1%/}")
            else
                echo "Unknown option or module not found: $1"
                echo "Usage: $0 [--model MODEL] [--details] [--lint-only] <module> [...]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ ${#MODULES[@]} -eq 0 ]]; then
    echo "No modules specified. Usage: $0 [--model MODEL] [--details] [--lint-only] <module> [...]"
    exit 1
fi

mkdir -p "$LINT_REPORT_DIR"

echo "Lint fix script for modules: ${MODULES[*]}"
if [[ "$LINT_ONLY" == true ]]; then
    echo "Mode: lint-only (no AI fixing)"
else
    echo "AI Agent: ${AI_AGENT:-none}"
    echo "Model: $MODEL"
fi
echo "Details: $SHOW_DETAILS"
echo ""

lint_module() {
    local module_path=$1
    local module_name
    module_name=$(basename "$module_path")
    local lint_report_file="$LINT_REPORT_DIR/${module_name}.log"

    echo "[$module_name] Running linters..."

    local lint_failed=false
    local lint_output=""

    # Collect tracked files under this module
    local tracked_files
    tracked_files=$(git -C "$ROOT_DIR" ls-files "$module_path" 2>/dev/null || true)
    if [[ -z "$tracked_files" ]]; then
        echo "[$module_name] No tracked files; skipping linters."
        return 0
    fi

    # Exclude migration folders from linting (they often contain legacy or auto-generated code)
    local filtered_files
    filtered_files=$(printf '%s\n' "$tracked_files" | grep -Ev '/migration[s]?/' || true)

    # Python files
    py_files=($(printf '%s\n' "$filtered_files" | grep -E '\.py$' || true))
    # JS/TS and related
    js_files=($(printf '%s\n' "$filtered_files" | grep -E '\.(js|jsx|ts|tsx)$' || true))
    prettier_files=($(printf '%s\n' "$filtered_files" | grep -E '\.(css|htm|html|js|json|jsx|less|md|scss|toml|ts|xml|yaml|yml)$' || true))

    # Helper to append command output
    run_lint_cmd() {
        local description=$1
        shift
        local cmd_output
        if ! cmd_output="$("$@" 2>&1)"; then
            lint_failed=true
            lint_output+=$'\n'"# ${description}"$'\n'"${cmd_output}"$'\n'
        else
            lint_output+=$'\n'"# ${description} (success)"$'\n'
            if [[ -n "$cmd_output" ]]; then
                lint_output+="${cmd_output}"$'\n'
            else
                lint_output+="(no output)"$'\n'
            fi
        fi
    }

    # Ruff + ruff-format, preferring system ruff, then pre-commit's ruff hook
    if [[ ${#py_files[@]} -gt 0 ]]; then
        if command -v ruff >/dev/null 2>&1; then
            echo "[$module_name] Ruff on ${#py_files[@]} Python files..."
            run_lint_cmd "ruff --fix --exit-non-zero-on-fix" ruff check --fix --exit-non-zero-on-fix "${py_files[@]}"
            echo "[$module_name] Ruff format..."
            run_lint_cmd "ruff format" ruff format "${py_files[@]}"
        elif command -v pre-commit >/dev/null 2>&1; then
            echo "[$module_name] Using pre-commit ruff hook on ${#py_files[@]} Python files..."
            run_lint_cmd "pre-commit run ruff --files" \
                pre-commit run ruff --config "$ROOT_DIR/.pre-commit-config.yaml" --files "${py_files[@]}"
        else
            echo "[$module_name] Ruff not available (no ruff binary and no pre-commit); skipping ruff checks."
        fi

        # Pylint-odoo (prefer system pylint, then pre-commit hook)
        if command -v pylint >/dev/null 2>&1; then
            if [[ -f "$ROOT_DIR/.pylintrc" ]]; then
                echo "[$module_name] pylint (optional checks)..."
                run_lint_cmd "pylint --rcfile=.pylintrc" pylint --rcfile="$ROOT_DIR/.pylintrc" "${py_files[@]}"
            else
                echo "[$module_name] .pylintrc not found; skipping optional pylint checks."
            fi
            if [[ -f "$ROOT_DIR/.pylintrc-mandatory" ]]; then
                echo "[$module_name] pylint (mandatory checks)..."
                run_lint_cmd "pylint --rcfile=.pylintrc-mandatory" pylint --rcfile="$ROOT_DIR/.pylintrc-mandatory" "${py_files[@]}"
            else
                echo "[$module_name] .pylintrc-mandatory not found; skipping mandatory pylint checks."
            fi
        elif command -v pre-commit >/dev/null 2>&1; then
            echo "[$module_name] Using pre-commit pylint_odoo hook on ${#py_files[@]} Python files..."
            run_lint_cmd "pre-commit run pylint_odoo --files" \
                pre-commit run pylint_odoo --config "$ROOT_DIR/.pre-commit-config.yaml" --files "${py_files[@]}"
        else
            echo "[$module_name] pylint not available (no pylint binary and no pre-commit); skipping pylint-odoo checks."
        fi
    fi

    # Prettier
    if [[ ${#prettier_files[@]} -gt 0 ]] && command -v prettier >/dev/null 2>&1; then
        echo "[$module_name] prettier on ${#prettier_files[@]} files..."
        run_lint_cmd "prettier --write" prettier --write --list-different --ignore-unknown "${prettier_files[@]}"
    fi

    # ESLint
    if [[ ${#js_files[@]} -gt 0 ]] && command -v eslint >/dev/null 2>&1; then
        echo "[$module_name] eslint on ${#js_files[@]} files..."
        run_lint_cmd "eslint --fix" eslint --color --fix "${js_files[@]}"
    fi

    # Write initial lint output
    if [[ -n "$lint_output" ]]; then
        printf '%s\n' "$lint_output" > "$lint_report_file"
    else
        : > "$lint_report_file"
    fi

    # If linters passed, we're done
    if [[ "$lint_failed" == false ]]; then
        echo "[$module_name] Linters completed without remaining errors."
        if [[ "$SHOW_DETAILS" == true && -s "$lint_report_file" ]]; then
            echo "[$module_name] Linter output:"
            sed 's/^/  /' "$lint_report_file"
        fi
        return 0
    fi

    # If lint-only mode or no AI agent, stop here
    if [[ "$LINT_ONLY" == true ]]; then
        echo "[$module_name] Linters reported issues (lint-only mode); see $lint_report_file"
        if [[ "$SHOW_DETAILS" == true && -s "$lint_report_file" ]]; then
            echo "[$module_name] Linter output:"
            sed 's/^/  /' "$lint_report_file"
        fi
        return 1
    fi

    if [[ -z "$AI_AGENT" ]]; then
        echo "[$module_name] Linters reported issues but no AI agent available; see $lint_report_file"
        echo "[$module_name] Install 'cursor-agent' or 'claude', or set AI_AGENT_CMD environment variable."
        return 1
    fi

    # Helper to run AI agent + re-lint loop up to N times
    local max_rounds=2
    local round

    for round in $(seq 1 "$max_rounds"); do
        echo "[$module_name] Linters reported issues; invoking $AI_AGENT to help fix them (round $round/$max_rounds)..."
        echo "[$module_name] Lint report saved to: $lint_report_file"

        # Build a prompt including linter output
        local prompt
        prompt=$(
            cat <<EOF
You are an Odoo 19 code assistant.

Goal: Fix the linting issues reported for this module while preserving behavior.

Context:
- Module path: $module_path
- Linters run: ruff (check+format), pylint (if available), prettier/eslint for JS/TS.

Instructions:
- Read the linter output below and update the code in this module to resolve the issues.
      - Prefer minimal, mechanical changes that satisfy the linters (style, imports, minor refactors).
      - Do NOT change business logic or external behavior.
      - Follow OCA Python and JS/TS style conventions, especially using lazy logging (_logger.info("X %s", value)) and avoiding PII in logs.
      - After edits, the linters should pass for this module.

Linter output:

$(cat "$lint_report_file")
EOF
        )

        # Run AI agent from within the module directory
        if (
            cd "$module_path" && \
            $AI_AGENT -p \
                --model "$MODEL" \
                "$prompt"
        ); then
            echo "[$module_name] $AI_AGENT completed for round $round. Re-running linters..."

            # Reset lint state and re-run linters for next round
            lint_failed=false
            lint_output=""

            # Python: ruff + pylint-odoo
            if [[ ${#py_files[@]} -gt 0 ]]; then
                if command -v ruff >/dev/null 2>&1; then
                    run_lint_cmd "ruff --fix --exit-non-zero-on-fix (round $round post-fix)" \
                        ruff check --fix --exit-non-zero-on-fix "${py_files[@]}"
                    run_lint_cmd "ruff format (round $round post-fix)" ruff format "${py_files[@]}"
                elif command -v pre-commit >/dev/null 2>&1; then
                    run_lint_cmd "pre-commit run ruff --files (round $round post-fix)" \
                        pre-commit run ruff --config "$ROOT_DIR/.pre-commit-config.yaml" --files "${py_files[@]}"
                fi

                if command -v pylint >/dev/null 2>&1; then
                    if [[ -f "$ROOT_DIR/.pylintrc" ]]; then
                        run_lint_cmd "pylint --rcfile=.pylintrc (round $round post-fix)" \
                            pylint --rcfile="$ROOT_DIR/.pylintrc" "${py_files[@]}"
                    fi
                    if [[ -f "$ROOT_DIR/.pylintrc-mandatory" ]]; then
                        run_lint_cmd "pylint --rcfile=.pylintrc-mandatory (round $round post-fix)" \
                            pylint --rcfile="$ROOT_DIR/.pylintrc-mandatory" "${py_files[@]}"
                    fi
                elif command -v pre-commit >/dev/null 2>&1; then
                    run_lint_cmd "pre-commit run pylint_odoo --files (round $round post-fix)" \
                        pre-commit run pylint_odoo --config "$ROOT_DIR/.pre-commit-config.yaml" --files "${py_files[@]}"
                fi
            fi

            # Prettier
            if [[ ${#prettier_files[@]} -gt 0 ]] && command -v prettier >/dev/null 2>&1; then
                run_lint_cmd "prettier --write (round $round post-fix)" \
                    prettier --write --list-different --ignore-unknown "${prettier_files[@]}"
            fi

            # ESLint
            if [[ ${#js_files[@]} -gt 0 ]] && command -v eslint >/dev/null 2>&1; then
                run_lint_cmd "eslint --fix (round $round post-fix)" \
                    eslint --color --fix "${js_files[@]}"
            fi
        else
            echo "[$module_name] $AI_AGENT reported an error in round $round; stopping further attempts."
            break
        fi
    done

    if [[ "$lint_failed" == true ]]; then
        echo "[$module_name] Linters still report issues after $max_rounds $AI_AGENT rounds; see $lint_report_file."
    fi

    if [[ "$SHOW_DETAILS" == true && -s "$lint_report_file" ]]; then
        echo "[$module_name] Final linter output:"
        sed 's/^/  /' "$lint_report_file"
    fi
}

for module in "${MODULES[@]}"; do
    lint_module "$module"
done
