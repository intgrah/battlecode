import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Replay

TEAM = {0: "A", 1: "B"}

DIR_DELTA = {
    0: (0, 0), 1: (0, -1), 2: (1, -1), 3: (1, 0), 4: (1, 1),
    5: (0, 1), 6: (-1, 1), 7: (-1, 0), 8: (-1, -1),
}


def parse(path: str) -> Replay:
    with open(path, "rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def entity_kind(e):
    return e.WhichOneof("kind") or "unknown"


def build_network(r: Replay):
    w, h = r.map.width, r.map.height
    core_pos = {}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    conveyors = {}
    harvesters = {0: {}, 1: {}}
    all_buildings = {}

    for turn in r.turns:
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                all_buildings[e.id] = (e.team, ek, pos)
                if ek == "conveyor":
                    d = e.conveyor.direction
                    dx, dy = DIR_DELTA.get(d, (0, 0))
                    out = (pos[0] + dx, pos[1] + dy)
                    conveyors[pos] = {"team": e.team, "out": out, "id": e.id, "dir": d}
                elif ek == "harvester":
                    harvesters[e.team][pos] = e.id
            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in all_buildings:
                    _, ek, pos = all_buildings[eid]
                    if pos in conveyors and conveyors[pos]["id"] == eid:
                        del conveyors[pos]
                    for t in (0, 1):
                        if pos in harvesters[t] and harvesters[t][pos] == eid:
                            del harvesters[t][pos]

    actual_flow = defaultdict(int)
    for turn in r.turns:
        for u in turn.updates:
            if u.WhichOneof("kind") == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    frm = (getattr(mv, "from").x, getattr(mv, "from").y)
                    actual_flow[frm] += 1

    return {
        "w": w, "h": h,
        "core_pos": core_pos,
        "conveyors": conveyors,
        "harvesters": harvesters,
        "actual_flow": actual_flow,
    }


def trace_to_core(start, conveyors, core_pos, team, w, h, max_hops=200):
    path = []
    cur = start
    visited = set()
    for _ in range(max_hops):
        if cur in visited:
            return path, "loop"
        visited.add(cur)
        path.append(cur)
        if core_pos:
            cx, cy = core_pos
            if abs(cur[0] - cx) <= 1 and abs(cur[1] - cy) <= 1:
                return path, "core"
        if cur not in conveyors or conveyors[cur]["team"] != team:
            return path, "dead"
        cur = conveyors[cur]["out"]
    return path, "long"


def compute_in_degree(conveyors, team):
    in_deg = defaultdict(int)
    for pos, c in conveyors.items():
        if c["team"] == team:
            in_deg[c["out"]] += 1
    return in_deg


def find_branches(conveyors, team, core_pos, w, h):
    team_convs = {p: c for p, c in conveyors.items() if c["team"] == team}
    in_deg = compute_in_degree(conveyors, team)

    roots = [p for p in team_convs if in_deg[p] == 0]

    branches = []
    for root in roots:
        path, result = trace_to_core(root, conveyors, core_pos, team, w, h)
        branches.append({"root": root, "path": path, "result": result, "len": len(path)})
    return branches


def find_convergence_points(conveyors, team):
    in_deg = compute_in_degree(conveyors, team)
    return {p: d for p, d in in_deg.items() if d >= 2 and p in conveyors and conveyors[p]["team"] == team}


def find_leak_points(conveyors, team, core_pos, w, h, actual_flow):
    team_convs = {p: c for p, c in conveyors.items() if c["team"] == team}

    on_live_chain = set()
    dead_ends = set()

    for pos, c in team_convs.items():
        path, result = trace_to_core(pos, conveyors, core_pos, team, w, h)
        if result == "core":
            on_live_chain.update(path)
        else:
            dead_ends.add(pos)

    leaks = []
    for dead_pos in dead_ends:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                adj = (dead_pos[0] + dx, dead_pos[1] + dy)
                if adj in on_live_chain and adj in team_convs:
                    c = team_convs[adj]
                    if c["out"] == dead_pos:
                        continue
                    out_dir = c["out"]
                    for ddx in range(-1, 2):
                        for ddy in range(-1, 2):
                            inp = (adj[0] + ddx, adj[1] + ddy)
                            if inp == dead_pos and (ddx, ddy) != DIR_DELTA.get(c["dir"], (0, 0)):
                                flow_on_dead = actual_flow.get(dead_pos, 0)
                                if flow_on_dead > 0:
                                    leaks.append({
                                        "dead": dead_pos,
                                        "live_adj": adj,
                                        "flow_leaked": flow_on_dead,
                                    })
    return leaks


def compute_betweenness(conveyors, harvesters_t, core_pos, team, w, h):
    tile_usage = defaultdict(int)
    for hpos in harvesters_t:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                adj = (hpos[0] + dx, hpos[1] + dy)
                if adj in conveyors and conveyors[adj]["team"] == team:
                    path, result = trace_to_core(adj, conveyors, core_pos, team, w, h)
                    if result == "core":
                        for tile in path:
                            tile_usage[tile] += 1
                        break
    return tile_usage


def analyze(net):
    for t in (0, 1):
        label = TEAM[t]
        cp = net["core_pos"].get(t)
        team_convs = {p: c for p, c in net["conveyors"].items() if c["team"] == t}
        team_harv = net["harvesters"][t]
        w, h = net["w"], net["h"]

        if not cp:
            print(f"--- Team {label}: no core ---\n")
            continue

        print(f"--- Team {label} (core {cp}) ---")
        print(f"  Conveyors: {len(team_convs)}  Harvesters: {len(team_harv)}")

        # Connectivity
        connected = 0
        disconnected = 0
        chain_lengths = []
        for hpos in team_harv:
            found = False
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    adj = (hpos[0] + dx, hpos[1] + dy)
                    if adj in team_convs:
                        path, result = trace_to_core(adj, net["conveyors"], cp, t, w, h)
                        if result == "core":
                            connected += 1
                            chain_lengths.append(len(path))
                            found = True
                            break
                if found:
                    break
            if not found:
                disconnected += 1

        print(f"  Connectivity: {connected}/{connected + disconnected}")
        if chain_lengths:
            print(f"  Chain lengths: min={min(chain_lengths)} avg={sum(chain_lengths)/len(chain_lengths):.0f} max={max(chain_lengths)}")

        # Convergence points (where chains merge)
        convergence = find_convergence_points(net["conveyors"], t)
        print(f"  Convergence points (in-degree >= 2): {len(convergence)}")
        if convergence:
            top = sorted(convergence.items(), key=lambda x: -x[1])[:5]
            for pos, deg in top:
                core_dist = math.sqrt((pos[0] - cp[0]) ** 2 + (pos[1] - cp[1]) ** 2)
                flow = net["actual_flow"].get(pos, 0)
                print(f"    ({pos[0]},{pos[1]}): in-degree={deg} flow={flow} dist_to_core={core_dist:.0f}")

        # Betweenness centrality
        between = compute_betweenness(net["conveyors"], team_harv, cp, t, w, h)
        if between:
            top_central = sorted(between.items(), key=lambda x: -x[1])[:5]
            print("  Most critical tiles (betweenness):")
            for pos, usage in top_central:
                flow = net["actual_flow"].get(pos, 0)
                print(f"    ({pos[0]},{pos[1]}): serves {usage} harvesters, flow={flow}")

        # Dead branches
        branches = find_branches(net["conveyors"], t, cp, w, h)
        live_branches = [b for b in branches if b["result"] == "core"]
        dead_branches = [b for b in branches if b["result"] != "core"]
        dead_conv_count = sum(b["len"] for b in dead_branches)
        live_conv_count = sum(b["len"] for b in live_branches)
        print(f"  Branches: {len(live_branches)} live ({live_conv_count} tiles), {len(dead_branches)} dead ({dead_conv_count} tiles)")

        # Flow leaking into dead branches
        dead_with_flow = 0
        total_leaked = 0
        for b in dead_branches:
            for tile in b["path"]:
                f = net["actual_flow"].get(tile, 0)
                if f > 0:
                    dead_with_flow += 1
                    total_leaked += f
        print(f"  Dead tiles with flow: {dead_with_flow} ({total_leaked} total leaked transfers)")

        # Throughput analysis near core
        core_input_tiles = []
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                p = (cp[0] + dx, cp[1] + dy)
                f = net["actual_flow"].get(p, 0)
                if f > 0:
                    core_input_tiles.append((p, f))
        core_input_tiles.sort(key=lambda x: -x[1])
        total_core_flow = sum(f for _, f in core_input_tiles)
        print(f"  Core input: {len(core_input_tiles)} tiles, {total_core_flow} total flow ({total_core_flow/20:.1f}/turn)")

        # Theoretical vs actual throughput
        theoretical_max = connected * 500  # 1 stack per 4 turns over 2000 turns
        actual_harvester_flow = sum(net["actual_flow"].get(h, 0) for h in team_harv)
        delivery_rate = total_core_flow / max(theoretical_max, 1) * 100
        print(f"  Harvester output: {actual_harvester_flow} stacks")
        print(f"  Core delivery: {total_core_flow} stacks ({delivery_rate:.0f}% of theoretical)")
        if actual_harvester_flow > 0:
            loss_rate = (actual_harvester_flow - total_core_flow) / actual_harvester_flow * 100
            print(f"  Flow loss: {loss_rate:.0f}% (produced but not delivered)")

        print()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    r = parse(path)
    net = build_network(r)
    analyze(net)


if __name__ == "__main__":
    main()
