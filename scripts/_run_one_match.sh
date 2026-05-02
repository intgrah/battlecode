#!/bin/zsh
# Internal: run one match. Args: MAP SIDE OUT SEED ROOT
set -e
m="$1"; side="$2"; OUT="$3"; SEED="$4"; ROOT="$5"
name=$(basename "$m" .map26)
if [ "$side" = "A" ]; then B1=v670; B2=okbot; else B1=okbot; B2=v670; fi
log="$OUT/${name}-${side}.log"
replay="$OUT/${name}-${side}.replay26"
cd "$ROOT"
VIRTUAL_ENV= uv run --project pkg/cambcpypy cambcpypy run \
    "bots/beacon/$B1" "bots/beacon/$B2" "$m" \
    --replay "$replay" --seed "$SEED" \
    > "$log" 2>&1 || true
