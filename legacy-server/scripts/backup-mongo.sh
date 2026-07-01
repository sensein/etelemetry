#!/bin/sh
# Incremental MongoDB backup for the 'et' DB, uploaded to S3 (instance IAM role for creds).
#
#   backup-mongo.sh base   -> full dump of the whole DB; records the requests _id watermark
#   backup-mongo.sh incr   -> dumps ONLY requests with _id in (watermark, now]; fast/small
#   backup-mongo.sh        -> defaults to 'incr'
#
# The et.requests collection is append-only, so incremental-by-_id is exact: increments are
# non-overlapping and only contain new inserts. Restore = latest base, then every newer
# increment in timestamp order (see legacy-server/README.md). Small collections (v1, geo)
# are captured by the weekly base.
set -eu

MODE="${1:-incr}"
HOME_DIR=/home/ec2-user
BACKUP_DIR="$HOME_DIR/out/backup"
LOG="$HOME_DIR/out/logs/backup.log"
BUCKET=s3://etelemetry-backup/incremental
WM_LOCAL="$BACKUP_DIR/.requests.watermark"     # last backed-up requests _id (hex)
WM_S3="$BUCKET/requests.watermark"
LOCAL_KEEP=4

mkdir -p "$BACKUP_DIR"
ts=$(date --iso-8601=seconds -u)
log() { echo "$(date -u) [$MODE] $*" >> "$LOG"; }

# Refuse to run on a nearly-full disk (avoids corrupt/partial dumps).
avail_kb=$(df -Pk / | awk 'NR==2 {print $4}')
[ "$avail_kb" -ge 524288 ] || { log "ABORT: only ${avail_kb}KB free on /"; exit 1; }

# Current max requests _id (hex) — captured BEFORE dumping so anything inserted mid-dump
# is picked up by the next run rather than skipped.
hi=$(sudo docker exec mongo mongo et --quiet --eval \
  'var c=db.requests.find({},{_id:1}).sort({_id:-1}).limit(1).toArray(); print(c.length?c[0]._id.str:"")' \
  2>>"$LOG" | tr -d "[:space:]")
[ -n "$hi" ] || { log "ABORT: could not read max requests _id (mongo unreachable?)"; exit 1; }

if [ "$MODE" = base ]; then
  file="$BACKUP_DIR/et.base.${ts}.gz"
  trap 'rm -f "$file" 2>/dev/null' EXIT
  log "start full base dump"
  sudo docker exec mongo sh -c 'exec mongodump -d et --gzip --archive' > "$file"
  size=$(stat -c%s "$file")
  [ "$size" -ge 1000000 ] || { log "ABORT: base dump too small (${size}B)"; exit 1; }
  aws s3 cp "$file" "$BUCKET/$(basename "$file")"
  printf '%s' "$hi" | tee "$WM_LOCAL" | aws s3 cp - "$WM_S3"
  trap - EXIT
  log "base done size=${size} watermark=${hi} file=$(basename "$file")"
else
  # incremental: requests inserted since the watermark
  prev=$(cat "$WM_LOCAL" 2>/dev/null || aws s3 cp "$WM_S3" - 2>/dev/null || echo "")
  [ -n "$prev" ] || { log "ABORT: no watermark; run 'backup-mongo.sh base' first"; exit 1; }
  if [ "$prev" = "$hi" ]; then log "no new requests since ${prev}; nothing to do"; exit 0; fi
  query='{"_id":{"$gt":{"$oid":"'"$prev"'"},"$lte":{"$oid":"'"$hi"'"}}}'
  file="$BACKUP_DIR/et.incr.${ts}.gz"
  trap 'rm -f "$file" 2>/dev/null' EXIT
  log "start incr dump range (${prev}, ${hi}]"
  sudo docker exec mongo sh -c "exec mongodump -d et -c requests --gzip --archive --query '$query'" > "$file"
  size=$(stat -c%s "$file")
  [ "$size" -ge 20 ] || { log "ABORT: incr dump empty/failed (${size}B)"; exit 1; }
  aws s3 cp "$file" "$BUCKET/$(basename "$file")"
  printf '%s' "$hi" | tee "$WM_LOCAL" | aws s3 cp - "$WM_S3"
  trap - EXIT
  log "incr done size=${size} watermark=${hi} file=$(basename "$file")"
fi

# Keep only the newest $LOCAL_KEEP local archives (S3 keeps the full history).
ls -1t "$BACKUP_DIR"/et.base.*.gz "$BACKUP_DIR"/et.incr.*.gz 2>/dev/null \
  | tail -n +$((LOCAL_KEEP + 1)) | xargs -r rm -f
