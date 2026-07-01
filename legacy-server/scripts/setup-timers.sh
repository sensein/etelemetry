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

write etelemetry-backup-base.service '[Unit]
Description=MongoDB (et) FULL base dump to S3 (sets requests _id watermark)

[Service]
Type=oneshot
ExecStart=/home/ec2-user/src/backup-mongo.sh base'

write etelemetry-backup-base.timer '[Unit]
Description=Weekly etelemetry MongoDB full base backup

[Timer]
OnCalendar=Sun *-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target'

write etelemetry-backup-incr.service '[Unit]
Description=MongoDB (et) INCREMENTAL dump to S3 (new requests since watermark)

[Service]
Type=oneshot
ExecStart=/home/ec2-user/src/backup-mongo.sh incr'

write etelemetry-backup-incr.timer '[Unit]
Description=Daily etelemetry MongoDB incremental backup

[Timer]
OnCalendar=*-*-* 02:30:00
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

echo "### remove superseded single backup unit (if present)"
sudo systemctl disable --now etelemetry-backup.timer 2>/dev/null || true
sudo rm -f /etc/systemd/system/etelemetry-backup.service /etc/systemd/system/etelemetry-backup.timer

echo "### enable timers"
sudo systemctl daemon-reload
for t in etelemetry-log-prune etelemetry-backup-base etelemetry-backup-incr etelemetry-cert-renew; do
  sudo systemctl enable --now "$t.timer"
done

echo "### timer status"
systemctl list-timers 'etelemetry-*' --all --no-pager
