"""Analyze marker usage: writes, reads, overwrites, destruction."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Replay


def entity_kind(e):
    return e.WhichOneof("kind") or "unknown"


def analyze_markers(path: str) -> None:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())

    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height
    print(f"Marker Analysis  |  {total_turns} turns  |  {w}x{h}")

    markers_alive = {}
    stats = {0: defaultdict(int), 1: defaultdict(int)}

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                if ek == "marker":
                    if pos in markers_alive:
                        old_team = markers_alive[pos]
                        stats[old_team]["overwritten"] += 1
                    markers_alive[pos] = e.team
                    stats[e.team]["placed"] += 1
                elif pos in markers_alive:
                    old_team = markers_alive[pos]
                    stats[old_team]["destroyed_by_build"] += 1
                    if e.team != old_team:
                        stats[old_team]["destroyed_by_enemy"] += 1
                    del markers_alive[pos]
            elif k == "remove_entity":
                eid = u.remove_entity.id

    for team_id in (0, 1):
        team_name = "A" if team_id == 0 else "B"
        s = stats[team_id]
        if s["placed"] == 0:
            continue
        print(f"\n--- Team {team_name} ---")
        print(f"  Markers placed: {s['placed']}")
        print(f"  Overwritten (by self): {s['overwritten']}")
        print(f"  Destroyed by building: {s['destroyed_by_build']}")
        print(f"  Destroyed by enemy: {s['destroyed_by_enemy']}")
        alive = sum(1 for t, team in markers_alive.items() if team == team_id)
        print(f"  Alive at end: {alive}")
        rate = s["placed"] / total_turns if total_turns > 0 else 0
        print(f"  Write rate: {rate:.2f}/turn")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: replay_markers.py <replay_path>")
        sys.exit(1)
    analyze_markers(sys.argv[1])
