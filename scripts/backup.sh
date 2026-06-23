#!/usr/bin/env bash
#
# Off-site backup of the PLC version-control data (per-project Git repos + the
# SQLite database) to DigitalOcean Spaces (S3-compatible). Run nightly via cron.
#
# Prerequisites on the droplet:
#   sudo apt-get install -y sqlite3 awscli     # or use rclone
#   aws configure                              # with your Spaces key/secret
#
# Required environment variables:
#   PLCVC_HOST_DATA_DIR   host data dir (default: /opt/plc-vcs/data)
#   BACKUP_BUCKET         e.g. s3://plc-vcs-backups
#   SPACES_ENDPOINT       e.g. https://nyc3.digitaloceanspaces.com
#
# Retention: set a lifecycle rule on the Spaces bucket to expire objects after
# N days. That is safer and simpler than deleting from this script.
#
set -euo pipefail

DATA_DIR="${PLCVC_HOST_DATA_DIR:-/opt/plc-vcs/data}"
: "${BACKUP_BUCKET:?set BACKUP_BUCKET, e.g. s3://plc-vcs-backups}"
: "${SPACES_ENDPOINT:?set SPACES_ENDPOINT, e.g. https://nyc3.digitaloceanspaces.com}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

sources=()

# 1) Consistent SQLite snapshot via the online backup API (no downtime).
if [ -f "$DATA_DIR/app.db" ]; then
	sqlite3 "$DATA_DIR/app.db" ".backup '$work/app.db'"
	sources+=( -C "$work" app.db )
fi

# 2) Every project's Git repo, tarred straight from the data dir.
if [ -d "$DATA_DIR/repos" ]; then
	sources+=( -C "$DATA_DIR" repos )
fi

if [ "${#sources[@]}" -eq 0 ]; then
	echo "nothing to back up in $DATA_DIR"
	exit 0
fi

# 3) Bundle and upload off-site.
archive="$work/plc-vcs-$stamp.tar.gz"
tar -czf "$archive" "${sources[@]}"
aws --endpoint-url "$SPACES_ENDPOINT" s3 cp "$archive" "$BACKUP_BUCKET/$stamp.tar.gz"

echo "backup uploaded: $BACKUP_BUCKET/$stamp.tar.gz"

# Cron (daily 02:30 UTC) — add via `crontab -e` as the deploy user:
#   30 2 * * * PLCVC_HOST_DATA_DIR=/opt/plc-vcs/data BACKUP_BUCKET=s3://plc-vcs-backups \
#     SPACES_ENDPOINT=https://nyc3.digitaloceanspaces.com \
#     /opt/plc-vcs/version-control/scripts/backup.sh >> /var/log/plc-backup.log 2>&1
