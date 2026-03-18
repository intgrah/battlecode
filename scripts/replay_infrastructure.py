"""Track splitters, turrets, foundries, bridges, barriers over time."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Replay


def entity_kind(e):
    return e.WhichOneof("kind") or "unknown"


def analyze_infrastructure(path: str) -> None:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())

    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height
    print(f"Infrastructure Report  |  {total_turns} turns  |  {w}x{h}")

    building_types = {
        "conveyor",
        "armoured_conveyor",
        "splitter",
        "bridge",
        "harvester",
        "foundry",
        "gunner",
        "sentinel",
        "breach",
        "launcher",
        "road",
        "barrier",
        "marker",
    }

    alive = {0: defaultdict(int), 1: defaultdict(int)}
    built = {0: defaultdict(int), 1: defaultdict(int)}
    destroyed = {0: defaultdict(int), 1: defaultdict(int)}
    entity_info = {}
    timeline = {0: [], 1: []}

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                if ek in building_types:
                    alive[e.team][ek] += 1
                    built[e.team][ek] += 1
                    entity_info[e.id] = (e.team, ek)
            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in entity_info:
                    team, ek = entity_info[eid]
                    alive[team][ek] = max(0, alive[team][ek] - 1)
                    destroyed[team][ek] += 1

        if turn_idx % 200 == 199 or turn_idx == total_turns - 1:
            for team_id in (0, 1):
                timeline[team_id].append((turn_idx + 1, dict(alive[team_id])))

    for team_id in (0, 1):
        team_name = "A" if team_id == 0 else "B"
        if not built[team_id]:
            continue
        print(f"\n--- Team {team_name} ---")

        print("  Built totals:")
        for ek in sorted(built[team_id]):
            if ek == "marker":
                continue
            b = built[team_id][ek]
            d = destroyed[team_id][ek]
            a = alive[team_id][ek]
            print(f"    {ek}: {b} built, {d} destroyed, {a} alive")

        print("  Timeline (alive counts):")
        important = ["harvester", "conveyor", "splitter", "bridge", "foundry", "gunner", "sentinel", "breach", "road"]
        header_parts = ["  Turn"]
        for ek in important:
            if any(ek in snap for _, snap in timeline[team_id]):
                header_parts.append(f"{ek[:8]:>8}")
        print("  " + "".join(header_parts))
        for turn, snap in timeline[team_id]:
            parts = [f"  t{turn:>4}"]
            for ek in important:
                if any(ek in s for _, s in timeline[team_id]):
                    parts.append(f"{snap.get(ek, 0):>8}")
            print("  " + "".join(parts))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: replay_infrastructure.py <replay_path>")
        sys.exit(1)
    analyze_infrastructure(sys.argv[1])
