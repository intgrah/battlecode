import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Replay

TEAM = {0: "A", 1: "B"}

DIR_DELTA = {
    0: (0, 0),
    1: (0, -1),
    2: (1, -1),
    3: (1, 0),
    4: (1, 1),
    5: (0, 1),
    6: (-1, 1),
    7: (-1, 0),
    8: (-1, -1),
}

SAMPLE_INTERVAL = 200


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def trace(start, conveyors, core_pos, team, max_hops=200):
    path = []
    cur = start
    visited = set()
    for _ in range(max_hops):
        if cur in visited:
            return path, "loop"
        visited.add(cur)
        if (
            core_pos
            and abs(cur[0] - core_pos[0]) <= 1
            and abs(cur[1] - core_pos[1]) <= 1
        ):
            return path, "core"
        path.append(cur)
        if cur not in conveyors or conveyors[cur]["team"] != team:
            return path, "dead"
        cur = conveyors[cur]["out"]
    return path, "long"


def find_harvester_chain_start(hpos, conveyors, team):
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            adj = (hpos[0] + dx, hpos[1] + dy)
            if adj in conveyors and conveyors[adj]["team"] == team:
                return adj
    return None


def analyze_snapshot(conveyors, harvesters_t, core_pos, team):
    if not core_pos:
        return None

    connected_harvs = []
    disconnected_harvs = []
    tile_flow = defaultdict(float)
    paths = {}

    for hpos in harvesters_t:
        start = find_harvester_chain_start(hpos, conveyors, team)
        if start is None:
            disconnected_harvs.append(hpos)
            continue
        path, result = trace(start, conveyors, core_pos, team)
        if result == "core":
            connected_harvs.append(hpos)
            paths[hpos] = path
            for tile in path:
                tile_flow[tile] += 0.25
        else:
            disconnected_harvs.append(hpos)

    congested = {t: f for t, f in tile_flow.items() if f > 1.0}
    bottleneck = max(tile_flow.items(), key=lambda x: x[1]) if tile_flow else (None, 0)
    total_income = len(connected_harvs) * 0.25

    team_convs = sum(1 for c in conveyors.values() if c["team"] == team)
    live_tiles = set()
    for p in paths.values():
        live_tiles.update(p)
    dead_tiles = team_convs - len(live_tiles)

    return {
        "connected": len(connected_harvs),
        "disconnected": len(disconnected_harvs),
        "total_harvesters": len(harvesters_t),
        "total_conveyors": team_convs,
        "live_tiles": len(live_tiles),
        "dead_tiles": dead_tiles,
        "income": total_income,
        "tile_flow": dict(tile_flow),
        "congested": congested,
        "bottleneck": bottleneck,
        "paths": paths,
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    r = parse(path)

    core_pos = {}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    conveyors = {}
    harvesters = {0: {}, 1: {}}
    entities = {}

    snapshots = {0: [], 1: []}

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = e.WhichOneof("kind") or "?"
                pos = (e.position.x, e.position.y)
                entities[e.id] = (e.team, ek, pos)
                if ek in ("conveyor", "armoured_conveyor", "splitter", "bridge"):
                    if ek == "bridge":
                        out = (e.bridge.target.x, e.bridge.target.y)
                    else:
                        sub = getattr(e, ek)
                        dx, dy = DIR_DELTA.get(sub.direction, (0, 0))
                        out = (pos[0] + dx, pos[1] + dy)
                    conveyors[pos] = {"team": e.team, "out": out, "id": e.id}
                elif ek == "harvester":
                    harvesters[e.team][pos] = e.id
            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    _, ek, pos = entities[eid]
                    if pos in conveyors and conveyors[pos]["id"] == eid:
                        del conveyors[pos]
                    for t in (0, 1):
                        if pos in harvesters[t] and harvesters[t][pos] == eid:
                            del harvesters[t][pos]

        if turn_idx > 0 and turn_idx % SAMPLE_INTERVAL == 0:
            for t in (0, 1):
                snap = analyze_snapshot(conveyors, harvesters[t], core_pos.get(t), t)
                if snap:
                    snap["turn"] = turn_idx
                    snapshots[t].append(snap)

    for t in (0, 1):
        snap = analyze_snapshot(conveyors, harvesters[t], core_pos.get(t), t)
        if snap:
            snap["turn"] = len(r.turns)
            snapshots[t].append(snap)

    for t in (0, 1):
        label = TEAM[t]
        cp = core_pos.get(t)
        if not cp:
            continue
        print(f"--- Team {label} (core {cp}) ---")

        print(
            f"  {'Turn':>6} {'Conn':>5} {'Disc':>5} {'Harv':>5} {'Conv':>5} {'Live':>5} {'Dead':>5} {'Income':>7} {'Bottleneck':>12} {'Congested':>10}",
        )
        for s in snapshots[t]:
            bn_pos, bn_flow = s["bottleneck"]
            bn_str = f"{bn_pos}={bn_flow:.2f}" if bn_pos else "-"
            cong = len(s["congested"])
            print(
                f"  t{s['turn']:>5} {s['connected']:>5} {s['disconnected']:>5} {s['total_harvesters']:>5} {s['total_conveyors']:>5} {s['live_tiles']:>5} {s['dead_tiles']:>5} {s['income']:>7.2f} {bn_str:>12} {cong:>10}",
            )

        last = snapshots[t][-1] if snapshots[t] else None
        if last and last["congested"]:
            print(f"\n  Congested tiles at t{last['turn']} (flow > 1.0 stacks/turn):")
            for pos, flow in sorted(last["congested"].items(), key=lambda x: -x[1])[
                :10
            ]:
                dist = max(abs(pos[0] - cp[0]), abs(pos[1] - cp[1]))
                print(
                    f"    ({pos[0]:>2},{pos[1]:>2}): flow={flow:.2f} dist_to_core={dist}",
                )

        if last and last["tile_flow"]:
            top = sorted(last["tile_flow"].items(), key=lambda x: -x[1])[:5]
            print(f"\n  Highest flow tiles at t{last['turn']}:")
            for pos, flow in top:
                dist = max(abs(pos[0] - cp[0]), abs(pos[1] - cp[1]))
                print(
                    f"    ({pos[0]:>2},{pos[1]:>2}): flow={flow:.2f} dist_to_core={dist}",
                )

        if last:
            print(f"\n  Chain lengths at t{last['turn']}:")
            for hpos, path in sorted(last["paths"].items(), key=lambda x: len(x[1])):
                print(f"    H({hpos[0]},{hpos[1]}): {len(path)} tiles")

        print()


if __name__ == "__main__":
    main()
