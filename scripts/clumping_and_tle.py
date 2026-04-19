"""Scan the replay corpus for:
  1. Core clumping: builder distance-from-core distribution over time.
  2. TLEs: which entity types and which matches produced them.

Usage:
    uv run --no-project python scripts/clumping_and_tle.py [--team test] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from proto import cambc_pb2  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
REPLAYS = ROOT / "replays_all"
INDEX = REPLAYS / "index.json"


def chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def team_idx(team_name: str, a: str, b: str) -> int | None:
    if team_name == a:
        return 0
    if team_name == b:
        return 1
    return None


def analyse(replay_path: Path, team_name: str, team_a: str, team_b: str) -> dict:
    t_idx = team_idx(team_name, team_a, team_b)
    if t_idx is None:
        return {}
    raw = replay_path.read_bytes()
    rep = cambc_pb2.Replay()
    rep.ParseFromString(raw)

    # Per-turn: positions of our BuilderBots.
    # Track core centre for our team from Map.cores.
    our_core: tuple[int, int] | None = None
    for c in rep.map.cores:
        if c.team == t_idx:
            our_core = (c.position.x, c.position.y)
            break
    if our_core is None:
        return {}

    # Maintain an entity table: id -> (kind, team, (x, y)).
    # Apply per-turn updates.
    entities: dict[int, dict] = {}
    # Metrics per turn bucket (every 25 turns to keep output small).
    bucket_size = 50
    buckets: dict[int, list[int]] = defaultdict(list)  # bucket -> list of distances
    # TLEs
    tle_rows: list[dict] = []
    tle_by_kind: Counter = Counter()
    # Unit count per turn bucket
    unit_count_buckets: dict[int, list[int]] = defaultdict(list)

    turn_idx = 0
    for turn in rep.turns:
        for upd in turn.updates:
            kind = upd.WhichOneof("kind")
            if kind == "place_entity":
                e = upd.place_entity.entity
                entities[e.id] = {
                    "kind": e.WhichOneof("kind"),
                    "team": e.team,
                    "pos": (e.position.x, e.position.y),
                }
            elif kind == "move_builder_bot":
                m = upd.move_builder_bot
                if m.id in entities:
                    entities[m.id]["pos"] = (m.to.x, m.to.y)
            elif kind == "remove_entity":
                entities.pop(upd.remove_entity.id, None)
            elif kind == "bot_output" and upd.bot_output.tled:
                bo = upd.bot_output
                ent = entities.get(bo.id, {})
                kind_name = ent.get("kind", "?")
                ent_team = ent.get("team", -1)
                if ent_team == t_idx:
                    tle_by_kind[kind_name] += 1
                    tle_rows.append({
                        "turn": turn_idx,
                        "id": bo.id,
                        "kind": kind_name,
                        "exec_us": bo.exec_time_us,
                        "stdout": bo.stdout[:200].replace("\n", " ")[:200],
                    })

        # End of turn: record our builder positions.
        bucket = turn_idx // bucket_size
        dists: list[int] = []
        our_unit_ct = 0
        for e in entities.values():
            if e["team"] != t_idx:
                continue
            if e["kind"] != "builder_bot":
                continue
            dists.append(chebyshev(e["pos"], our_core))
            our_unit_ct += 1
        buckets[bucket].extend(dists)
        unit_count_buckets[bucket].append(our_unit_ct)
        turn_idx += 1

    return {
        "replay": replay_path.name,
        "total_turns": turn_idx,
        "buckets": dict(buckets),
        "unit_count_buckets": dict(unit_count_buckets),
        "tle_by_kind": dict(tle_by_kind),
        "tle_rows": tle_rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="test")
    ap.add_argument("--limit", type=int, default=0, help="process only N replays (0 = all)")
    args = ap.parse_args()

    idx = json.loads(INDEX.read_text())
    entries = sorted(idx.items(), key=lambda kv: kv[1].get("completedAt", ""), reverse=True)
    if args.limit > 0:
        entries = entries[: args.limit]

    all_buckets: dict[int, list[int]] = defaultdict(list)
    all_unit_counts: dict[int, list[int]] = defaultdict(list)
    all_tle_by_kind: Counter = Counter()
    tle_rows_all: list[dict] = []
    replays_scanned = 0
    tle_matches: Counter = Counter()  # (teamA-teamB) -> tle count

    for key, meta in entries:
        path = REPLAYS / f"{key}.replay26"
        if not path.exists():
            continue
        try:
            res = analyse(path, args.team, meta["teamA"], meta["teamB"])
        except Exception as e:  # noqa: BLE001
            print(f"skip {path.name}: {e}", file=sys.stderr)
            continue
        if not res:
            continue
        replays_scanned += 1
        for b, dists in res["buckets"].items():
            all_buckets[b].extend(dists)
        for b, counts in res["unit_count_buckets"].items():
            all_unit_counts[b].extend(counts)
        all_tle_by_kind.update(res["tle_by_kind"])
        tle_rows_all.extend([{**row, "replay": key} for row in res["tle_rows"]])
        if sum(res["tle_by_kind"].values()) > 0:
            tle_matches[f"{meta['teamA']} vs {meta['teamB']}"] += sum(res["tle_by_kind"].values())

    print(f"scanned {replays_scanned} replays for team={args.team}")
    print()

    # Clumping: distance-from-core distribution per 50-turn bucket.
    print(f"{'turn':>8}  {'n':>5}  {'med':>5}  {'p25':>5}  {'p75':>5}  {'p90':>5}  {'max':>5}  {'units':>5}")
    for b in sorted(all_buckets):
        dists = all_buckets[b]
        if not dists:
            continue
        counts = all_unit_counts[b]
        dists_sorted = sorted(dists)
        n = len(dists)
        med = statistics.median(dists_sorted)
        p25 = dists_sorted[int(n * 0.25)]
        p75 = dists_sorted[int(n * 0.75)]
        p90 = dists_sorted[int(n * 0.90)]
        mx = dists_sorted[-1]
        mean_units = statistics.mean(counts) if counts else 0
        print(
            f"{b * 50:>8}  {n:>5}  {med:>5}  {p25:>5}  {p75:>5}  {p90:>5}  {mx:>5}  {mean_units:>5.1f}"
        )

    print()
    print("TLEs by entity kind (team {})".format(args.team))
    for kind, n in all_tle_by_kind.most_common():
        print(f"  {kind:>16}  {n}")

    print()
    print("TLEs by match ({} total TLEs in {} matches with TLEs):".format(
        sum(all_tle_by_kind.values()), len(tle_matches)
    ))
    for match, n in tle_matches.most_common(10):
        print(f"  {n:>4}  {match}")

    print()
    if tle_rows_all:
        print("Sample TLE events (most recent):")
        for row in tle_rows_all[:10]:
            print(f"  turn={row['turn']:>4} id={row['id']:>4} kind={row['kind']:>14} exec={row['exec_us']}us")
            if row["stdout"].strip():
                print(f"    stdout: {row['stdout']}")


if __name__ == "__main__":
    main()
