#!/bin/zsh
# Run v670 vs okbot on a standard 10-map pool, both sides per map.
# Usage: ./scripts/test_v670.sh [LABEL]
# Env: NMAPS=N (random sample), MAPS="m1 m2..." (override pool), SEED=1, JOBS=4
set -e
cd "$(dirname "$0")/.."

LABEL="${1:-iter}"
SEED="${SEED:-1}"
JOBS="${JOBS:-4}"
TS=$(date +%Y%m%d-%H%M%S)
OUT="/tmp/v670_test/${TS}-${LABEL}"
mkdir -p "$OUT"

if [ -z "$MAPS" ] && [ -z "$NMAPS" ]; then
    MAPS="maps/arena.map26 maps/default_medium1.map26 maps/default_large1.map26 maps/coffee.map26 maps/corridors.map26 maps/face.map26 maps/butterfly.map26 maps/cubes.map26 maps/squares.map26 maps/maimai.map26"
fi
if [ -n "$NMAPS" ]; then
    MAPS=$(ls maps/*.map26 | shuf -n "$NMAPS")
fi

NMAPS_ACTUAL=$(echo "$MAPS" | wc -w | tr -d ' ')
echo "=== v670 vs okbot — $LABEL ($NMAPS_ACTUAL maps × 2 sides, seed=$SEED, jobs=$JOBS) ===" | tee "$OUT/summary.txt"
echo "Output dir: $OUT" | tee -a "$OUT/summary.txt"

JOBLIST="$OUT/joblist.txt"
> "$JOBLIST"
for m in $(echo "$MAPS"); do
    for side in A B; do
        echo "$m $side" >> "$JOBLIST"
    done
done

ROOT="$PWD"
RUNNER="$ROOT/scripts/_run_one_match.sh"
chmod +x "$RUNNER"

# Bounded-parallel dispatch via shell job control.
ACTIVE=0
while IFS= read -r line; do
    set -- ${=line}
    "$RUNNER" "$1" "$2" "$OUT" "$SEED" "$ROOT" &
    ACTIVE=$((ACTIVE+1))
    if [ $ACTIVE -ge $JOBS ]; then
        wait -n 2>/dev/null || wait
        ACTIVE=$((ACTIVE-1))
    fi
done < "$JOBLIST"
wait

# Tally.
W670=0; WOK=0; OTHER=0
while IFS= read -r line; do
    set -- ${=line}
    m=$1; side=$2
    name=$(basename "$m" .map26)
    log="$OUT/${name}-${side}.log"
    winner=$(grep -E '^  Winner:' "$log" 2>/dev/null | head -1 | awk '{print $2}')
    if [ "$winner" = "v670" ]; then
        W670=$((W670+1)); res="v670"
    elif [ "$winner" = "okbot" ]; then
        WOK=$((WOK+1)); res="okbot"
    else
        OTHER=$((OTHER+1)); res="??? ($winner)"
    fi
    printf "  %-30s side=%s  →  %s\n" "$name" "$side" "$res" | tee -a "$OUT/summary.txt"
done < "$JOBLIST"

echo "" | tee -a "$OUT/summary.txt"
echo "RESULT: v670=$W670  okbot=$WOK  other=$OTHER  (out of $((NMAPS_ACTUAL*2)))" | tee -a "$OUT/summary.txt"
echo "Logs: $OUT" | tee -a "$OUT/summary.txt"
