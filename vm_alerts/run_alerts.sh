#!/bin/bash
# One alert pass on the eugene-alerts VM (systemd timer, every 10 min).
# 1) refresh code from GitHub  2) run the checker  3) on ALERT email it; if the send fails, put the old state back
#    so the same alert is found and retried next run  4) heartbeat to GitHub only if this box can actually send.
set -u
APP=/opt/eugene-alerts; REPO=$APP/repo; DATA=/var/lib/eugene-alerts; LOGF=/var/log/eugene-alerts/run.log
mkdir -p "$DATA/out" /var/log/eugene-alerts
for f in /etc/eugene-alerts/op.env /etc/eugene-alerts/alerts.env; do [ -f "$f" ] && { set -a; . "$f"; set +a; }; done   # root-only files
export TZ=America/Los_Angeles MPLBACKEND=Agg FEED_TIMEOUT=20
export ALERT_STATE=$DATA/alert_state.json ALERT_LOG=/var/log/eugene-alerts/alert_check.log ALERT_REPORTS=$DATA/out ALERT_ATTACH=$DATA/out
log(){ echo "$(date '+%F %T %Z') $*" >> "$LOGF"; }
exec 9>"$DATA/.lock"; flock -n 9 || { log "previous run still going, skipping"; exit 0; }
timeout 60 git -C "$REPO" pull -q --ff-only 2>>"$LOGF" || log "git pull failed (using current copy)"
MODE=${1:-}
if [ "$MODE" = "--test" ]; then
  LINE=$(cd "$REPO/zip_tools" && python3 alert_check.py --test | tail -1)
  read -r _ MD HTML ATT <<< "$LINE"; python3 "$REPO/vm_alerts/send_alert.py" "$MD" "$HTML" "$ATT" --test >>"$LOGF" 2>&1; rc=$?; log "test send rc=$rc"; exit $rc
fi
[ -f "$ALERT_STATE" ] && cp -p "$ALERT_STATE" "$DATA/alert_state.prev.json"
LINE=$(cd "$REPO/zip_tools" && timeout 300 python3 alert_check.py | tail -1)
log "check: $LINE"
CAN_SEND=0; python3 "$REPO/vm_alerts/send_alert.py" --check >/dev/null 2>&1 && CAN_SEND=1
SEND_OK=1
if [[ "$LINE" == ALERT* ]]; then
  read -r _ MD HTML ATT <<< "$LINE"
  if [ $CAN_SEND = 1 ] && python3 "$REPO/vm_alerts/send_alert.py" "$MD" "$HTML" "$ATT" >>"$LOGF" 2>&1; then
    log "alert emailed"; mkdir -p "$DATA/sent"; cp "$MD" "$DATA/sent/$(date -u +%Y%m%dT%H%M%SZ).md"
  else
    SEND_OK=0; log "alert NOT sent (can_send=$CAN_SEND) - restoring previous state so it retries next run"
    [ -f "$DATA/alert_state.prev.json" ] && cp -p "$DATA/alert_state.prev.json" "$ALERT_STATE"
  fi
fi
if [ $CAN_SEND = 1 ] && [ $SEND_OK = 1 ]; then python3 "$REPO/vm_alerts/heartbeat.py" >>"$LOGF" 2>&1
else log "no heartbeat (cannot send) - GitHub backup stays in charge"; fi
exit 0
