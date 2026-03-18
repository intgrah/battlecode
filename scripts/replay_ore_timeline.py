"""Track ore discovery, claiming, and harvester placement timeline."""

import sys
from pathlib import Path

from proto.cambc_pb2 import Replay


def entity_kind(e):
    return e.WhichOneof("kind") or "unknown"


def analyze_ore(path: str) -> None:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())

    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height

    ore_tiles = set()
    for y, row in enumerate(r.map.rows):
        for x, t in enumerate(row.tiles):
            if t in (2, 3):
                ore_tiles.add((x, y))

    ore_type = {}
    for y, row in enumerate(r.map.rows):
        for x, t in enumerate(row.tiles):
            if t == 2:
                ore_type[(x, y)] = "Ti"
            elif t == 3:
                ore_type[(x, y)] = "Ax"

    print(f"Ore Timeline  |  {total_turns} turns  |  {w}x{h}")
    print(
        f"Total ore tiles: {len(ore_tiles)} ({sum(1 for v in ore_type.values() if v == 'Ti')} Ti, {sum(1 for v in ore_type.values() if v == 'Ax')} Ax)",
    )

    entities = {}
    builder_pos = {}

    first_seen = {0: {}, 1: {}}
    harvester_turn = {0: {}, 1: {}}

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                entities[e.id] = (e.team, ek)
                pos = (e.position.x, e.position.y)
                if ek == "builder_bot":
                    builder_pos[e.id] = pos
                elif ek == "harvester":
                    if pos in ore_tiles and pos not in harvester_turn[e.team]:
                        harvester_turn[e.team][pos] = turn_idx
            elif k == "move_builder_bot":
                m = u.move_builder_bot
                eid = m.id
                if eid in entities:
                    team = entities[eid][0]
                    builder_pos[eid] = (m.to.x, m.to.y)

        for bid, (team, kind) in entities.items():
            if kind != "builder_bot" or bid not in builder_pos:
                continue
            bx, by = builder_pos[bid]
            for ox, oy in ore_tiles:
                if (ox - bx) ** 2 + (oy - by) ** 2 <= 20:
                    if (ox, oy) not in first_seen[team]:
                        first_seen[team][(ox, oy)] = turn_idx

    for team_id in (0, 1):
        team_name = "A" if team_id == 0 else "B"
        seen = first_seen[team_id]
        harvested = harvester_turn[team_id]
        if not seen and not harvested:
            continue

        print(f"\n--- Team {team_name} ---")
        print(f"  Ore tiles seen: {len(seen)}/{len(ore_tiles)}")
        print(f"  Harvesters placed: {len(harvested)}/{len(ore_tiles)}")

        if seen:
            avg_seen = sum(seen.values()) / len(seen)
            print(f"  Avg first-seen turn: {avg_seen:.0f}")
            print(f"  Last ore seen at: t{max(seen.values())}")

        if harvested:
            avg_harv = sum(harvested.values()) / len(harvested)
            print(f"  Avg harvester turn: {avg_harv:.0f}")
            print(f"  Last harvester at: t{max(harvested.values())}")

        print("\n  Per-ore detail:")
        all_ore = sorted(ore_tiles)
        for ox, oy in all_ore:
            ot = ore_type.get((ox, oy), "?")
            s = seen.get((ox, oy), None)
            h = harvested.get((ox, oy), None)
            seen_str = f"seen t{s}" if s is not None else "unseen"
            harv_str = f"harvested t{h}" if h is not None else "unharvested"
            gap = ""
            if s is not None and h is not None:
                gap = f" (gap={h - s})"
            print(f"    ({ox:>2},{oy:>2}) {ot}: {seen_str}, {harv_str}{gap}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: replay_ore_timeline.py <replay_path>")
        sys.exit(1)
    analyze_ore(sys.argv[1])
