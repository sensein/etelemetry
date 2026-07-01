#!/bin/sh
# Prune old etelemetry app logs so out/logs cannot fill the disk again.
# The app rotates console.log/access.log weekly but never deletes them.
# Keep rotations from the last KEEP_DAYS days; current console.log/access.log are untouched.
set -eu

LOGDIR=/home/ec2-user/out/logs
KEEP_DAYS=21

find "$LOGDIR" -maxdepth 1 -type f \
  \( -name 'console.log.*' -o -name 'access.log.*' \) \
  -mtime +"$KEEP_DAYS" -delete
