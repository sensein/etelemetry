#!/bin/bash
# Replace cron with systemd timers for etelemetry maintenance. Units run as root,
# so the scripts' sudo/IMDS-role calls work without a tty. Idempotent.
set -eu

echo "### revert cron (switching to systemd timers)"
crontab -r 2>/dev/null || true
sudo systemctl disable --now crond 2>/dev/null || true
sudo dnf remove -y cronie cronie-anacron 2>&1 | tail -1 || true

echo "### write unit files"
write() { echo "$2" | sudo tee "/etc/systemd/system/$1" >/dev/null; echo "  wrote $1"; }

write etelemetry-log-prune.service '[Unit]
Description=Prune old etelemetry app logs (out/logs)

[Service]
Type=oneshot
ExecStart=/home/ec2-user/src/prune-etelemetry-logs.sh'

write etelemetry-log-prune.timer '[Unit]
Description=Daily etelemetry log prune

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target'

write etelemetry-backup.service '[Unit]
Description=MongoDB (et) dump to S3

[Service]
Type=oneshot
ExecStart=/home/ec2-user/src/backup-mongo.sh'

write etelemetry-backup.timer '[Unit]
Description=Weekly etelemetry MongoDB backup

[Timer]
OnCalendar=Sun *-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target'

write etelemetry-cert-renew.service '[Unit]
Description=Renew Let'"'"'s Encrypt cert and re-import to ACM

[Service]
Type=oneshot
ExecStart=/home/ec2-user/src/renew-cert.sh'

write etelemetry-cert-renew.timer '[Unit]
Description=Daily Let'"'"'s Encrypt renew + ACM import (no-op until ~30d before expiry)

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target'

echo "### enable timers"
sudo systemctl daemon-reload
for t in etelemetry-log-prune etelemetry-backup etelemetry-cert-renew; do
  sudo systemctl enable --now "$t.timer"
done

echo "### timer status"
systemctl list-timers 'etelemetry-*' --all --no-pager
