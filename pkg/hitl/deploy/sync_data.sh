#!/bin/sh
# Sync the local hitl data (db + blobs + pngs) up to the server. Idempotent.
set -eu

HOST="${1:-bc}"
LOCAL_DATA="$(dirname "$0")/../data"
REMOTE_DATA="/home/intgrah/hitl/data"

echo "==> Stopping service (so the DB isn't being written to)"
ssh "$HOST" "systemctl --user stop hitl.service"

echo "==> Syncing data/"
rsync -az --delete "$LOCAL_DATA/" "$HOST:$REMOTE_DATA/"

echo "==> Starting service"
ssh "$HOST" "systemctl --user start hitl.service; sleep 2; curl -sf http://127.0.0.1:8080/stats || echo 'healthz failed'"
