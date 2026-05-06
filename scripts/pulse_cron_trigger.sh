#!/bin/sh
set -eu
URL="${BACKEND_URL:-http://backend:8080}/api/v1/internal/scheduler/pulse"
curl -fsS -X POST \
  -H "Authorization: Bearer ${SCHEDULER_SHARED_SECRET}" \
  -H "Content-Type: application/json" \
  "$URL"
