#!/usr/bin/env bash
# Run a match and parse the replay.
# Usage: ./run_test.sh [bot_a] [bot_b] [map]
# Defaults: bot_a=v5, bot_b=dummy, map=default_small1

set -e

BOT_A="${1:-v5}"
BOT_B="${2:-dummy}"
MAP="${3:-}"

cd "$(dirname "$0")"

echo "=== Running: $BOT_A vs $BOT_B ==="
if [ -n "$MAP" ]; then
    ./venv/bin/cambc run "$BOT_A" "$BOT_B" "maps/${MAP}.map26"
else
    ./venv/bin/cambc run "$BOT_A" "$BOT_B"
fi

echo ""
echo "=== Replay Analysis ==="
python3 parse_replay.py replay.replay26
