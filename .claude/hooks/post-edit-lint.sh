#!/bin/bash
# Post-edit linting hook for Claude Code
#
# This hook runs automatically after Edit or Write operations to lint
# the modified file. It runs appropriate linters based on file extension.
#
# Configured in .claude/settings.json as a PostToolUse hook.

set -e

# Ensure CLAUDE_PROJECT_DIR is set
if [ -z "$CLAUDE_PROJECT_DIR" ]; then
    exit 0
fi

# Read JSON input from stdin
INPUT=$(cat)

# Extract file path from tool_input (handles both Edit and Write tools)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json
import sys
data = json.load(sys.stdin)
tool_input = data.get('tool_input', {})
# Write tool uses 'file_path', Edit tool also uses 'file_path'
print(tool_input.get('file_path', ''))
" 2>/dev/null || true)

if [ -z "$FILE_PATH" ]; then
    # No file path found, exit silently
    exit 0
fi

# Get absolute path if needed
if [[ ! "$FILE_PATH" = /* ]]; then
    FILE_PATH="$CLAUDE_PROJECT_DIR/$FILE_PATH"
fi

# Check if file exists
if [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

# Run linters based on file extension
case "$FILE_PATH" in
    *.py)
        # Python file - run ruff, ruff-format, and Odoo 19 check
        cd "$CLAUDE_PROJECT_DIR"
        pre-commit run ruff --files "$FILE_PATH" 2>/dev/null || true
        pre-commit run ruff-format --files "$FILE_PATH" 2>/dev/null || true

        # Run Odoo 19 compatibility check (skip tests)
        if [[ ! "$FILE_PATH" =~ /tests/ ]]; then
            python scripts/lint/check_odoo19.py "$FILE_PATH" 2>/dev/null || true
        fi
        ;;
    *.xml)
        # XML file - run prettier and Odoo 19 check
        cd "$CLAUDE_PROJECT_DIR"
        pre-commit run prettier --files "$FILE_PATH" 2>/dev/null || true

        # Run Odoo 19 XML check (skip data/demo)
        if [[ ! "$FILE_PATH" =~ /(data|demo)/ ]]; then
            python scripts/lint/check_odoo19.py --xml "$FILE_PATH" 2>/dev/null || true
        fi
        ;;
    *.json|*.yml|*.yaml|*.md|*.js|*.css)
        # Other files - run prettier only
        cd "$CLAUDE_PROJECT_DIR"
        pre-commit run prettier --files "$FILE_PATH" 2>/dev/null || true
        ;;
esac

exit 0
