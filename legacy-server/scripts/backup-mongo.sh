#!/bin/sh
# Backup the 'et' MongoDB to S3. Relies on the EC2 instance IAM role for AWS creds
# (no static keys). Keeps the most recent LOCAL_KEEP archives locally; S3 retention
# is handled by a bucket lifecycle rule.
set -eu

HOME_DIR=/home/ec2-user
BACKUP_DIR="$HOME_DIR/out/backup"
LOG="$HOME_DIR/out/logs/backup.log"
BUCKET=s3://etelemetry-backup
LOCAL_KEEP=2

ts=$(date --iso-8601=seconds -u)
filename="$BACKUP_DIR/et.archive.${ts}.gz"

mkdir -p "$BACKUP_DIR"
# Remove the (partial) dump on any early/failed exit; cleared on success below.
trap 'rm -f "$filename" 2>/dev/null' EXIT
echo "Started: $(date -u)" >> "$LOG"

# Fail early if the root filesystem is critically low (<1GB) to avoid corrupt 0-byte dumps.
avail_kb=$(df -Pk / | awk 'NR==2 {print $4}')
if [ "$avail_kb" -lt 1048576 ]; then
  echo "ABORT: only ${avail_kb}KB free on / — refusing to dump" >> "$LOG"
  exit 1
fi

# Dump (gzip archive) straight to a local file.
sudo docker exec mongo sh -c 'exec mongodump -d et --gzip --archive' > "$filename"

# Sanity check: archive must be non-trivial.
size=$(stat -c%s "$filename")
if [ "$size" -lt 1000000 ]; then
  echo "ABORT: dump suspiciously small (${size} bytes) — not uploading, removing" >> "$LOG"
  rm -f "$filename"
  exit 1
fi

# Upload to S3 (instance role provides creds).
aws s3 cp "$filename" "$BUCKET/$(basename "$filename")"

# Keep a stable 'latest' pointer object too.
aws s3 cp "$filename" "$BUCKET/et.archive.latest.gz"

# Success: keep this archive (cancel the cleanup trap), then prune old LOCAL archives.
trap - EXIT
ls -1t "$BACKUP_DIR"/et.archive.*.gz 2>/dev/null | tail -n +$((LOCAL_KEEP + 1)) | xargs -r rm -f

echo "Finished: $(date -u)  size=${size}  file=$(basename "$filename")" >> "$LOG"
