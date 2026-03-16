import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Entity, Replay

TEAM = {0: "A", 1: "B"}

DIR_DELTA = {
    0: (0, 0), 1: (0, -1), 2: (1, -1), 3: (1, 0), 4: (1, 1),
    5: (0, 1), 6: (-1, 1), 7: (-1, 0), 8: (-1, -1),
}


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def build_graph(r: Replay) -> dict:
    w, h = r.map.width, r.map.height

    core_pos = {}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    entities = {}
    entity_pos = {}
    conveyors = {}
    harvesters = {0: {}, 1: {}}

    for turn in r.turns:
        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                entities[e.id] = (e.team, ek)
                entity_pos[e.id] = pos

                if ek == "conveyor":
                    d = e.conveyor.direction
                    dx, dy = DIR_DELTA.get(d, (0, 0))
                    output_pos = (pos[0] + dx, pos[1] + dy)
                    conveyors[pos] = {"team": e.team, "dir": d, "output": output_pos, "id": e.id}
                elif ek == "harvester":
                    harvesters[e.team][pos] = e.id
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entity_pos:
                    old_pos = entity_pos[eid]
                    if old_pos in conveyors and conveyors[old_pos]["id"] == eid:
                        del conveyors[old_pos]
                    for t in (0, 1):
                        if old_pos in harvesters[t] and harvesters[t][old_pos] == eid:
                            del harvesters[t][old_pos]

    return {
        "w": w, "h": h,
        "core_pos": core_pos,
        "conveyors": conveyors,
        "harvesters": harvesters,
    }


def trace_chain(start: tuple[int, int], conveyors: dict, core_pos: tuple[int, int], team: int, w: int, h: int) -> tuple[list, str, bool]:
    visited = set()
    path = [start]
    cur = start
    reached_core = False

    for _ in range(200):
        if cur in visited:
            return path, "loop", reached_core
        visited.add(cur)

        if cur not in conveyors:
            if core_pos:
                cx, cy = core_pos
                dx = abs(cur[0] - cx)
                dy = abs(cur[1] - cy)
                if dx <= 1 and dy <= 1:
                    reached_core = True
                    return path, "core", reached_core
            return path, "dead_end", reached_core

        c = conveyors[cur]
        if c["team"] != team:
            return path, "enemy", reached_core

        next_pos = c["output"]
        if next_pos[0] < 0 or next_pos[0] >= w or next_pos[1] < 0 or next_pos[1] >= h:
            return path, "out_of_bounds", reached_core

        if core_pos:
            cx, cy = core_pos
            dx = abs(next_pos[0] - cx)
            dy = abs(next_pos[1] - cy)
            if dx <= 1 and dy <= 1:
                path.append(next_pos)
                reached_core = True
                return path, "core", reached_core

        path.append(next_pos)
        cur = next_pos

    return path, "too_long", reached_core


def analyze_graph(g: dict) -> None:
    for t in (0, 1):
        label = TEAM[t]
        cp = g["core_pos"].get(t)
        team_conveyors = {pos: c for pos, c in g["conveyors"].items() if c["team"] == t}
        team_harvesters = g["harvesters"][t]

        print(f"--- Team {label} ---")
        print(f"  Core: {cp}")
        print(f"  Conveyors: {len(team_conveyors)}")
        print(f"  Harvesters: {len(team_harvesters)}")

        in_degree = defaultdict(int)
        for pos, c in team_conveyors.items():
            in_degree[c["output"]] += 1

        roots = [pos for pos in team_conveyors if in_degree[pos] == 0]
        leaves = [pos for pos, c in team_conveyors.items()
                  if c["output"] not in team_conveyors and not (
                      cp and abs(c["output"][0] - cp[0]) <= 1 and abs(c["output"][1] - cp[1]) <= 1
                  )]

        print(f"  Chain roots (no input): {len(roots)}")
        print(f"  Dead ends (output to nothing): {len(leaves)}")

        print()
        print("  Harvester chains:")
        total_hops = 0
        connected = 0
        disconnected = 0
        for hpos in team_harvesters:
            adjacent_conveyors = []
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    adj = (hpos[0] + dx, hpos[1] + dy)
                    if adj in team_conveyors:
                        adjacent_conveyors.append(adj)

            if not adjacent_conveyors:
                print(f"    H({hpos[0]},{hpos[1]}): NO ADJACENT CONVEYOR")
                disconnected += 1
                continue

            best_path = None
            best_result = None
            for adj in adjacent_conveyors:
                path, result, reached = trace_chain(adj, g["conveyors"], cp, t, g["w"], g["h"])
                if reached and (best_path is None or len(path) < len(best_path)):
                    best_path = path
                    best_result = result

            if best_path is None:
                path, result, reached = trace_chain(adjacent_conveyors[0], g["conveyors"], cp, t, g["w"], g["h"])
                best_path = path
                best_result = result

            hops = len(best_path)
            import math
            straight = math.sqrt((hpos[0] - cp[0]) ** 2 + (hpos[1] - cp[1]) ** 2) if cp else 0
            ratio = hops / max(straight, 1)
            reached = best_result == "core"

            status = "OK" if reached else f"BROKEN({best_result})"
            if reached:
                connected += 1
            else:
                disconnected += 1

            total_hops += hops
            last_tile = best_path[-1] if best_path else "?"
            print(f"    H({hpos[0]},{hpos[1]}): {hops} hops, straight={straight:.0f}, ratio={ratio:.1f}x, end={last_tile} {status}")

        print()
        print(f"  Connected: {connected}/{connected + disconnected}")
        if connected > 0:
            avg_hops = total_hops / (connected + disconnected)
            print(f"  Avg chain length: {avg_hops:.0f} hops")

        on_chain = set()
        for hpos in team_harvesters:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    adj = (hpos[0] + dx, hpos[1] + dy)
                    if adj in team_conveyors:
                        path, result, reached = trace_chain(adj, g["conveyors"], cp, t, g["w"], g["h"])
                        if reached:
                            on_chain.update(path)

        dead = len(team_conveyors) - len(on_chain & set(team_conveyors.keys()))
        print(f"  Conveyors on live chains: {len(on_chain & set(team_conveyors.keys()))}")
        print(f"  Dead conveyors: {dead} ({100 * dead // max(len(team_conveyors), 1)}%)")

        shared = defaultdict(int)
        for pos in on_chain:
            if pos in team_conveyors:
                shared[pos] += 1
        multi_use = sum(1 for v in shared.values() if v > 1)
        print(f"  Shared trunk tiles: {multi_use}")

        print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    r = parse(path)
    g = build_graph(r)
    analyze_graph(g)


if __name__ == "__main__":
    main()
