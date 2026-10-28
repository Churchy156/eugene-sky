# eugene-alerts VM (main alert sender)
Debian 12 VM `eugene-alerts` on the GROKBOTS Hyper-V host. A systemd timer runs `run_alerts.sh` every 10 min:
checker -> email over SMTP (no bot) -> heartbeat to repo variable `ALERT_PRIMARY_HEARTBEAT`.
`.github/workflows/alerts.yml` is the backup: it keeps running the checker, but only POSTs to the bot webhook
when the heartbeat is missing or older than 30 minutes. Settings: `/etc/eugene-alerts/alerts.env` (see example).
Logs: /var/log/eugene-alerts/ (logrotate weekly, 8 kept). State: /var/lib/eugene-alerts/alert_state.json.
Test email: `sudo /opt/eugene-alerts/repo/vm_alerts/run_alerts.sh --test`.
