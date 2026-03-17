import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Entity, Replay

TEAM = {0: "A", 1: "B"}


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def analyze_territory(r: Replay) -> None:
    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height
    vision_sq = 20

    ore_tiles = set()
    wall_tiles = set()
    for y, row in enumerate(r.map.rows):
        for x, env in enumerate(row.tiles):
            if env in (2, 3):
                ore_tiles.add((x, y))
            elif env == 1:
                wall_tiles.add((x, y))

    passable = w * h - len(wall_tiles)

    core_pos = {0: None, 1: None}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    entities = {}
    entity_pos = {}
    entity_team = {}
    builder_positions = {0: set(), 1: set()}
    all_buildings = {0: set(), 1: set()}

    explored = {0: set(), 1: set()}
    ore_seen = {0: set(), 1: set()}
    ore_harvested = {0: set(), 1: set()}

    snapshots = []
    sample_turns = {50, 100, 200, 500, 1000, 1500, 1999}

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                entities[e.id] = (e.team, ek)
                entity_pos[e.id] = pos
                entity_team[e.id] = e.team

                if ek == "builder_bot":
                    builder_positions[e.team].add(e.id)
                elif ek != "marker":
                    all_buildings[e.team].add(pos)
                if ek == "harvester":
                    ore_harvested[e.team].add(pos)

            elif k == "move_builder_bot":
                mb = u.move_builder_bot
                new = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new

            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek = entities[eid]
                    if ek == "builder_bot":
                        builder_positions[team].discard(eid)
                    pos = entity_pos.get(eid)
                    if pos and ek != "marker":
                        all_buildings[team].discard(pos)

        for t in (0, 1):
            for bid in builder_positions[t]:
                bp = entity_pos.get(bid)
                if not bp:
                    continue
                for ox in range(max(0, bp[0] - 4), min(w, bp[0] + 5)):
                    for oy in range(max(0, bp[1] - 4), min(h, bp[1] + 5)):
                        dx = ox - bp[0]
                        dy = oy - bp[1]
                        if (
                            dx * dx + dy * dy <= vision_sq
                            and (ox, oy) not in wall_tiles
                        ):
                            explored[t].add((ox, oy))
                            if (ox, oy) in ore_tiles:
                                ore_seen[t].add((ox, oy))

        if turn_idx in sample_turns:
            max_dist = {0: 0.0, 1: 0.0}
            for t in (0, 1):
                cp = core_pos[t]
                if not cp:
                    continue
                for pos in all_buildings[t]:
                    d = ((pos[0] - cp[0]) ** 2 + (pos[1] - cp[1]) ** 2) ** 0.5
                    max_dist[t] = max(max_dist[t], d)

            enemy_dist = {0: 999.0, 1: 999.0}
            for t in (0, 1):
                cp = core_pos[t]
                if not cp:
                    continue
                enemy = 1 - t
                for bid in builder_positions[enemy]:
                    bp = entity_pos.get(bid)
                    if bp:
                        d = ((bp[0] - cp[0]) ** 2 + (bp[1] - cp[1]) ** 2) ** 0.5
                        enemy_dist[t] = min(enemy_dist[t], d)

            snapshots.append(
                {
                    "turn": turn_idx,
                    "explored": {t: len(explored[t]) for t in (0, 1)},
                    "ore_seen": {t: len(ore_seen[t]) for t in (0, 1)},
                    "ore_harvested": {t: len(ore_harvested[t]) for t in (0, 1)},
                    "max_dist": dict(max_dist),
                    "enemy_dist": dict(enemy_dist),
                    "buildings": {t: len(all_buildings[t]) for t in (0, 1)},
                },
            )

    print(f"Territory Analysis  |  {total_turns} turns  |  {w}x{h}")
    print(f"  Passable tiles: {passable}  Ore tiles: {len(ore_tiles)}")
    print()

    for t in (0, 1):
        label = TEAM[t]
        print(f"--- Team {label} ---")

        exp = len(explored[t])
        exp_pct = 100 * exp / max(passable, 1)
        print(f"  Final exploration: {exp}/{passable} tiles ({exp_pct:.0f}%)")

        os = len(ore_seen[t])
        oh = len(ore_harvested[t])
        os_pct = 100 * os / max(len(ore_tiles), 1)
        oh_pct = 100 * oh / max(os, 1) if os > 0 else 0
        print(f"  Ore seen: {os}/{len(ore_tiles)} ({os_pct:.0f}%)")
        print(f"  Ore harvested: {oh}/{os} seen ({oh_pct:.0f}%)")
        print()

    print("  Timeline:")
    print(f"  {'Turn':>5}  ", end="")
    for t in (0, 1):
        label = TEAM[t]
        print(
            f"{'Expl%':>5} {'Ore%':>5} {'Bldg':>4} {'Reach':>5} {'Enemy':>5}  ",
            end="",
        )
    print()

    for snap in snapshots:
        turn = snap["turn"]
        print(f"  t{turn:>4}  ", end="")
        for t in (0, 1):
            exp_pct = 100 * snap["explored"][t] / max(passable, 1)
            ore_pct = 100 * snap["ore_seen"][t] / max(len(ore_tiles), 1)
            bldg = snap["buildings"][t]
            reach = snap["max_dist"][t]
            enemy = snap["enemy_dist"][t]
            enemy_str = f"{enemy:.0f}" if enemy < 999 else "-"
            print(
                f"{exp_pct:>5.0f} {ore_pct:>5.0f} {bldg:>4} {reach:>5.1f} {enemy_str:>5}  ",
                end="",
            )
        print()
    print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    analyze_territory(parse(path))


if __name__ == "__main__":
    main()
