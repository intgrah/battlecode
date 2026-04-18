#!/bin/sh
# Deploy the HITL service to the bc host. Idempotent.
set -eu

HOST="${1:-bc}"
REMOTE_DIR="/home/intgrah/hitl"

echo "==> Ensuring uv is installed on $HOST"
ssh "$HOST" 'command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh'

echo "==> Creating remote dirs"
ssh "$HOST" "mkdir -p $REMOTE_DIR/data"

echo "==> Syncing sources"
# Sync only pkg/hitl (not the whole monorepo). The hitl package must be
# self-contained (no workspace deps) so it can stand on its own on the server.
rsync -az --delete \
    --exclude 'data' --exclude '__pycache__' --exclude '*.egg-info' \
    --exclude '.venv' --exclude 'deploy' \
    "$(dirname "$0")/../" "$HOST:$REMOTE_DIR/src/"

echo "==> Installing deps"
ssh "$HOST" "cd $REMOTE_DIR/src && ~/.local/bin/uv sync"

echo "==> Installing systemd unit"
ssh "$HOST" "mkdir -p ~/.config/systemd/user"
scp "$(dirname "$0")/hitl.service" "$HOST:~/.config/systemd/user/hitl.service"

echo "==> Enabling + starting"
ssh "$HOST" "systemctl --user daemon-reload; systemctl --user enable --now hitl.service; sleep 1; systemctl --user status hitl.service --no-pager | head -12"

echo "==> Testing healthz"
ssh "$HOST" "curl -sf http://127.0.0.1:8080/healthz" || {
    echo "healthz failed"; exit 1;
}
echo
echo "OK. Forward port 8080 or configure tailscale to access."
