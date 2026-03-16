import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Replay

TEAM = {0: "A", 1: "B"}
ORE_ENVS = {2, 3}


def entity_kind(e):
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with open(path, "rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def analyze_network(r: Replay):
    w, h = r.map.width, r.map.height

    ore_tiles = set()
    for y, row in enumerate(r.map.rows):
        for x, env in enumerate(row.tiles):
            if env in ORE_ENVS:
                ore_tiles.add((x, y))

    entities = {}
    entity_pos = {}
    entity_team = {}
    harvester_ids = {0: set(), 1: set()}
    core_pos = {0: None, 1: None}
    builder_positions_over_time = {0: defaultdict(set), 1: defaultdict(set)}
    conveyor_flow = defaultdict(int)
    conveyors_placed = {0: set(), 1: set()}
    ore_with_building = set()

    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                entities[e.id] = (e.team, ek)
                pos = (e.position.x, e.position.y)
                entity_pos[e.id] = pos
                entity_team[e.id] = e.team
                if ek == "core":
                    core_pos[e.team] = pos
                elif ek == "harvester":
                    harvester_ids[e.team].add(e.id)
                elif ek in ("conveyor", "armoured_conveyor"):
                    conveyors_placed[e.team].add(pos)
                if pos in ore_tiles and ek != "harvester":
                    ore_with_building.add(pos)
            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                new = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new
                if mb.id in entity_team:
                    builder_positions_over_time[entity_team[mb.id]][new].add(turn_idx)
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                entity_pos.pop(eid, None)
            elif kind == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    frm = (getattr(mv, "from").x, getattr(mv, "from").y)
                    conveyor_flow[frm] += 1

    for t in (0, 1):
        label = TEAM[t]
        cp = core_pos[t]
        if cp is None:
            print(f"--- Team {label}: no core ---\n")
            continue

        print(f"--- Team {label} ---")

        total_ore = len(ore_tiles)
        harvested = len(harvester_ids[t])
        ore_blocked = len(ore_with_building & conveyors_placed[t])
        print(f"  Ore tiles on map: {total_ore}")
        print(
            f"  Harvesters built: {harvested} ({100 * harvested // max(total_ore, 1)}% of ore)",
        )
        if ore_blocked:
            print(f"  Ore blocked by conveyors: {ore_blocked}")

        ore_seen = set()
        vision_sq = 20
        for pos in builder_positions_over_time[t]:
            for ox, oy in ore_tiles:
                dx = pos[0] - ox
                dy = pos[1] - oy
                if dx * dx + dy * dy <= vision_sq:
                    ore_seen.add((ox, oy))

        harvested_positions = {
            entity_pos[hid] for hid in harvester_ids[t] if hid in entity_pos
        }
        ore_seen_not_harvested = ore_seen - harvested_positions - ore_with_building
        print(f"  Ore seen by builders: {len(ore_seen)}/{total_ore}")
        print(f"  Ore seen but unharvested: {len(ore_seen_not_harvested)}")

        total_conv = len(conveyors_placed[t])
        active_conv = len(
            {pos for pos in conveyors_placed[t] if conveyor_flow.get(pos, 0) > 0},
        )
        dead_conv = total_conv - active_conv
        dead_pct = 100 * dead_conv // max(total_conv, 1)
        print(
            f"  Conveyors: {total_conv} total, {active_conv} active, {dead_conv} dead ({dead_pct}%)",
        )

        print("  Chain analysis:")
        for hid in harvester_ids[t]:
            if hid not in entity_pos:
                continue
            hpos = entity_pos[hid]
            flow = conveyor_flow.get(hpos, 0)
            straight = math.sqrt((hpos[0] - cp[0]) ** 2 + (hpos[1] - cp[1]) ** 2)
            connected = flow > 0
            print(
                f"    Harvester ({hpos[0]},{hpos[1]}): dist={straight:.0f} flow={flow} {'OK' if connected else 'DISCONNECTED'}",
            )

        if conveyor_flow:
            peak_tile = max(conveyor_flow, key=conveyor_flow.get)
            peak_flow = conveyor_flow[peak_tile]
            print(
                f"  Bottleneck: ({peak_tile[0]},{peak_tile[1]}) with {peak_flow} transfers",
            )

        max_theoretical = harvested * 2.5
        actual_rate = sum(
            1 for pos in conveyors_placed[t] if conveyor_flow.get(pos, 0) > 0
        )
        print(
            f"  Theoretical max income: {max_theoretical:.1f}/t (from {harvested} harvesters)",
        )
        print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    analyze_network(parse(path))


if __name__ == "__main__":
    main()
