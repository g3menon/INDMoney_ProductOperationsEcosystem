#!/bin/sh
set -eu
apk add --no-cache curl >/dev/null

if [ -z "${SCHEDULER_SHARED_SECRET:-}" ]; then
  echo "pulse-scheduler: SCHEDULER_SHARED_SECRET is empty — weekly cron disabled (backend still runs)."
  exec sleep infinity
fi

log() {
  echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ") $*"
}

mkdir -p /var/log
touch /var/log/pulse-cron.log

# Monday 10:00 Asia/Kolkata == 04:30 UTC (IST is UTC+5:30 year-round).
cat <<CRON >/etc/crontabs/root
30 4 * * 1 /bin/sh /pulse_cron_trigger.sh >> /var/log/pulse-cron.log 2>&1
CRON

log "pulse-scheduler: crond active; weekly trigger at 04:30 UTC (Mon) -> POST /api/v1/internal/scheduler/pulse"
exec crond -f -l 8
