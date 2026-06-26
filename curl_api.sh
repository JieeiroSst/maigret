#!/usr/bin/env bash
# Example usage of api_server.py's JSON polling API.
#
# Usage:
#   ./curl_api.sh <username> [host:port]
#
# Requires api_server.py to already be running:
#   source .venv/bin/activate && python api_server.py

set -euo pipefail

USERNAME="${1:?Usage: $0 <username> [host:port]}"
HOST="${2:-127.0.0.1:5050}"

echo "Submitting search for '$USERNAME'..." >&2
SUBMIT_RESPONSE=$(curl -s -X POST "http://${HOST}/api/search" \
  -H 'Content-Type: application/json' \
  -d "{\"username\": \"${USERNAME}\"}")

JOB_ID=$(echo "$SUBMIT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB_ID" >&2

while true; do
  STATUS_RESPONSE=$(curl -s "http://${HOST}/api/status/${JOB_ID}")
  STATE=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "State: $STATE" >&2

  if [ "$STATE" = "completed" ] || [ "$STATE" = "failed" ]; then
    echo "$STATUS_RESPONSE" | python3 -m json.tool
    break
  fi

  sleep 2
done
