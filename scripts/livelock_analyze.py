import glob
import sys
from collections import defaultdict

files = sorted(glob.glob("/tmp/v39_b*.log"))
if not files:
    print("No log files found at /tmp/v39_b*.log")
    sys.exit(1)

WINDOW = 8

for path in files:
    eid = path.split("v39_b")[1].split(".")[0]
    entries: list[tuple[int, str, str]] = []
    for line in open(path):
        line = line.strip()
        if (
            not line or line.startswith((" ", "nav", "build", "fix_"))
        ):
            continue
        parts = line.split()
        try:
            rnd = int(parts[0])
        except ValueError:
            continue
        pos = parts[1]
        action = parts[2] if len(parts) > 2 else "unknown"
        entries.append((rnd, pos, action))

    total = len(entries)
    if total == 0:
        continue

    action_counts: dict[str, int] = defaultdict(int)
    oscillation_runs: list[tuple[int, int, int, str]] = []
    stuck_start = None
    stuck_positions: set[str] = set()

    for i, (rnd, pos, action) in enumerate(entries):
        action_counts[action] += 1

        lo = max(0, i - WINDOW + 1)
        window_positions = {entries[j][1] for j in range(lo, i + 1)}

        if i - lo + 1 >= WINDOW and len(window_positions) <= 2:
            if stuck_start is None:
                stuck_start = entries[lo][0]
                stuck_positions = window_positions
        elif stuck_start is not None:
            oscillation_runs.append(
                (
                    stuck_start,
                    entries[i - 1][0],
                    entries[i - 1][0] - stuck_start + 1,
                    " <-> ".join(sorted(stuck_positions)),
                ),
            )
            stuck_start = None
            stuck_positions = set()

    if stuck_start is not None:
        oscillation_runs.append(
            (
                stuck_start,
                entries[-1][0],
                entries[-1][0] - stuck_start + 1,
                " <-> ".join(sorted(stuck_positions)),
            ),
        )

    print(f"=== Builder {eid} ({total} turns) ===")
    for a, n in sorted(action_counts.items(), key=lambda x: -x[1]):
        pct = 100 * n / total
        bar = "#" * int(pct / 2)
        print(f"  {a:10s} {n:5d} ({pct:5.1f}%) {bar}")

    if oscillation_runs:
        osc_turns = sum(r[2] for r in oscillation_runs)
        print(
            f"  Oscillations: {len(oscillation_runs)} runs, {osc_turns} turns ({100 * osc_turns / total:.1f}%)",
        )
        for start, end, length, positions in oscillation_runs:
            if length >= 10:
                lo_i = next(i for i, e in enumerate(entries) if e[0] >= start)
                hi_i = next(i for i, e in enumerate(entries) if e[0] >= end)
                actions_in_run = defaultdict(int)
                for j in range(lo_i, hi_i + 1):
                    actions_in_run[entries[j][2]] += 1
                act_str = " ".join(
                    f"{a}={c}"
                    for a, c in sorted(actions_in_run.items(), key=lambda x: -x[1])
                )
                print(f"    t={start}-{end} ({length}t) {positions} [{act_str}]")
    else:
        print("  No oscillations detected.")

    bucket_size = 200
    max_rnd = entries[-1][0]
    print(f"  Timeline (per {bucket_size} turns):")
    for b_start in range(entries[0][0], max_rnd + 1, bucket_size):
        b_end = b_start + bucket_size
        bucket_actions: dict[str, int] = defaultdict(int)
        bucket_positions: set[str] = set()
        for rnd, pos, action in entries:
            if b_start <= rnd < b_end:
                bucket_actions[action] += 1
                bucket_positions.add(pos)
        if not bucket_actions:
            continue
        summary = " ".join(
            f"{a}={c}" for a, c in sorted(bucket_actions.items(), key=lambda x: -x[1])
        )
        uniq = len(bucket_positions)
        print(f"    t={b_start:4d}-{b_end:4d}: {summary} ({uniq} tiles)")
    print()
