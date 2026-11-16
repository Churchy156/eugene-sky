#!/bin/bash
# Weekday Eugene daily outlook, built and emailed on the eugene-alerts VM (6:45 AM PT).
# Uses the same SMTP settings as ASAP alerts. Recipient is enforced in send_alert.py.
set -u
APP=/opt/eugene-alerts; REPO=$APP/repo; DATA=/var/lib/eugene-alerts; LOGF=/var/log/eugene-alerts/daily.log
mkdir -p "$DATA/out" /var/log/eugene-alerts
for f in /etc/eugene-alerts/op.env /etc/eugene-alerts/alerts.env; do [ -f "$f" ] && { set -a; . "$f"; set +a; }; done
export TZ=America/Los_Angeles MPLBACKEND=Agg FEED_TIMEOUT=20
export ALERT_ATTACH=$REPO/reports
log(){ echo "$(date '+%F %T %Z') $*" >> "$LOGF"; }
exec 9>"$DATA/.daily.lock"; flock -n 9 || { log "previous daily run still going, skipping"; exit 0; }
# Weekdays only (timer is also weekdays; this is a belt-and-suspenders check)
if [ "$(date +%u)" -ge 6 ]; then log "weekend, skip"; exit 0; fi
timeout 60 git -C "$REPO" pull -q --ff-only 2>>"$LOGF" || log "git pull failed (using current copy)"
cd "$REPO" || exit 1
if ! python3 "$REPO/vm_alerts/send_alert.py" --check >/dev/null 2>&1; then
  log "daily NOT sent (SMTP not configured)"
  exit 0
fi
if ! python3 daily_report.py >>"$LOGF" 2>&1; then
  log "daily_report.py failed"
  exit 1
fi
DAY=$(date +%F)
MD=$REPO/reports/email_${DAY}.md
[ -f "$MD" ] || MD=$REPO/reports/outlook_${DAY}.md
HTML=$REPO/reports/email_${DAY}.html
MAP=$REPO/reports/eq_map_${DAY}.png
ATT="-"
[ -f "$MAP" ] && ATT="$MAP"
if [ ! -f "$MD" ] || [ ! -f "$HTML" ]; then
  log "daily report files missing (md=$MD html=$HTML)"
  exit 1
fi
if python3 "$REPO/vm_alerts/send_alert.py" "$MD" "$HTML" "$ATT" >>"$LOGF" 2>&1; then
  log "daily emailed"
  mkdir -p "$DATA/sent"
  cp "$MD" "$DATA/sent/daily-${DAY}.md"
  exit 0
else
  log "daily NOT sent"
  exit 1
fi
