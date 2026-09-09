#!/bin/bash
# Wait for a URL to become available
# Usage: ./wait_for_url.sh [URL] [TIMEOUT_SECONDS]
#
# Returns 0 if URL is reachable within timeout, 1 otherwise
set -e

URL="${1:-http://localhost:8069/web/login}"
TIMEOUT="${2:-300}"  # 5 minutes default
INTERVAL=5

echo "Waiting for $URL to become available (timeout: ${TIMEOUT}s)..."

start_time=$(date +%s)
while true; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))

    if [[ $elapsed -ge $TIMEOUT ]]; then
        echo "ERROR: Timeout waiting for $URL after ${TIMEOUT}s"
        exit 1
    fi

    # Check if URL responds with 200 or 302 (redirect to login)
    http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null || echo "000")

    if [[ "$http_code" == "200" ]] || [[ "$http_code" == "302" ]] || [[ "$http_code" == "303" ]]; then
        echo "URL $URL is available (HTTP $http_code) after ${elapsed}s"
        exit 0
    fi

    echo "  Waiting... (${elapsed}s elapsed, HTTP status: $http_code)"
    sleep $INTERVAL
done
