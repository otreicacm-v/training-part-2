#!/bin/bash
# Show the URL for the dev profile Odoo instance
# Usage: ./scripts/dev-url.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Get the port from docker compose
PORT=$(docker compose --profile dev ps --format json 2>/dev/null | \
    jq -r 'select(.Service == "odoo-dev") | .Publishers[] | select(.TargetPort == 8069) | .PublishedPort' 2>/dev/null)

if [ -z "$PORT" ] || [ "$PORT" = "null" ]; then
    echo "Dev profile is not running." >&2
    echo "Start it with: docker compose --profile dev up -d" >&2
    exit 1
fi

URL="http://localhost:$PORT"
echo "$URL"

# If on macOS, offer to open in browser
if [ "$1" = "--open" ] || [ "$1" = "-o" ]; then
    if command -v open &> /dev/null; then
        open "$URL"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$URL"
    fi
fi
