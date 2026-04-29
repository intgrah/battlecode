"""Decode the covert-channel message from bots/misc/covert exec timings.

Usage: uv run python -m scripts.covert_decode [replay_path] [team]
"""

import random
import sys

from scripts.replay import load_replay

SEED = 42
NUM_ROUNDS = 2000
BASE_US = 40
STEP_US = 10

MESSAGE: bytes = bytes(b & 0x7F for b in random.Random(SEED).randbytes(NUM_ROUNDS))


def decode_byte(exec_us: int) -> int:
    raw = (exec_us - BASE_US + STEP_US // 2) // STEP_US
    return max(0, min(127, raw))


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    r = load_replay(path)

    core_id_per_team: dict[int, int] = {c.team: c.id for c in r.map.cores}

    team = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if team not in core_id_per_team:
        teams = sorted(core_id_per_team)
        print(f"team {team} has no core; available: {teams}")
        return
    core_id = core_id_per_team[team]

    times: list[int] = []
    for turn in r.turns:
        for u in turn.updates:
            if u.HasField("bot_output") and u.bot_output.id == core_id:
                times.append(u.bot_output.exec_time_us)

    print(f"team={team} core_id={core_id} core_outputs={len(times)}")
    if not times:
        return

    decoded = bytes(decode_byte(t) for t in times)
    n = min(len(decoded), len(MESSAGE))
    matches = sum(1 for a, b in zip(decoded[:n], MESSAGE[:n], strict=False) if a == b)
    print(f"compared {n} bytes: {matches} match ({100 * matches / n:.2f}%)")

    deltas = [times[i] - (BASE_US + STEP_US * MESSAGE[i]) for i in range(n)]
    deltas.sort()
    m = len(deltas)
    print(
        f"exec_time - target (us): "
        f"min={deltas[0]} p10={deltas[m // 10]} p50={deltas[m // 2]} "
        f"p90={deltas[(9 * m) // 10]} max={deltas[-1]}"
    )

    mismatches = [
        (i, decoded[i], MESSAGE[i], times[i])
        for i in range(n)
        if decoded[i] != MESSAGE[i]
    ]
    print(f"byte mismatches: {len(mismatches)} / {n} rounds")
    for i, dec, exp, t in mismatches[:10]:
        print(f"  round_idx={i} exec_us={t} decoded={dec} expected={exp}")


if __name__ == "__main__":
    main()
