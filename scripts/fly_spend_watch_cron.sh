#!/usr/bin/env bash
# Weekly wrapper around fly_spend_watch.sh. Silent on OK; on DRIFT (a config change
# that could drive a surprise bill) POSTs to the Second Shift alerts webhook so it
# lands on the Alerts tile + ss-alerts-channel. Fly's own $50 budget alert (dashboard)
# is the dollar backstop; this catches the *cause* of a runaway bill early.
set -uo pipefail
WATCH="$(dirname "$0")/fly_spend_watch.sh"
ALERT_URL="${ALERT_URL:-http://localhost:8765/api/alerts/webhook}"
LOG=/home/mayorawesome/work/macu-pipeline/logs/fly_spend_watch.log
mkdir -p "$(dirname "$LOG")"

out="$("$WATCH" 2>&1)"; rc=$?
printf '%s  rc=%s\n%s\n\n' "$(date '+%F %T %Z')" "$rc" "$out" >>"$LOG"

if [ "$rc" -eq 2 ]; then
  msg="Fly cost drift detected: $(printf '%s' "$out" | tr '\n' ' ' | sed 's/  */ /g')"
  payload=$(jq -nc --arg sev warn --arg src fly-spend --arg msg "$msg" '{sev:$sev,src:$src,msg:$msg}')
  curl -fsS -o /dev/null --max-time 5 -X POST "$ALERT_URL" -H 'Content-Type: application/json' -d "$payload" || true
elif [ "$rc" -ne 0 ]; then
  # watcher itself errored (e.g. token/API) — flag once so it doesn't fail silently forever
  payload=$(jq -nc --arg sev warn --arg src fly-spend --arg msg "Fly spend watcher error (rc=$rc): $out" '{sev:$sev,src:$src,msg:$msg}')
  curl -fsS -o /dev/null --max-time 5 -X POST "$ALERT_URL" -H 'Content-Type: application/json' -d "$payload" || true
fi
