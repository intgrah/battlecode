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


def build_timeline(r: Replay) -> dict:
    w, h = r.map.width, r.map.height
    core_pos = {}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    snapshots = []
    conveyors = {}
    harvesters = {0: {}, 1: {}}
    builders = {}
    builder_pos = {}
    builder_team = {}
    all_entities = {}

    builder_actions = defaultdict(list)

    for turn_idx, turn in enumerate(r.turns):
        actions_this_turn = defaultdict(str)

        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                all_entities[e.id] = (e.team, ek, pos)

                if ek == "conveyor":
                    d = e.conveyor.direction
                    dx, dy = DIR_DELTA.get(d, (0, 0))
                    out = (pos[0] + dx, pos[1] + dy)
                    conveyors[pos] = {"team": e.team, "out": out, "id": e.id, "dir": d}
                elif ek == "harvester":
                    harvesters[e.team][pos] = {"id": e.id, "built_turn": turn_idx}
                elif ek == "builder_bot":
                    builders[e.id] = {"team": e.team, "born": turn_idx}
                    builder_pos[e.id] = pos
                    builder_team[e.id] = e.team
                    actions_this_turn[e.id] = "spawn"

            elif k == "move_builder_bot":
                mb = u.move_builder_bot
                builder_pos.get(mb.id)
                new = (mb.to.x, mb.to.y)
                builder_pos[mb.id] = new
                actions_this_turn[mb.id] = "move"

            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in all_entities:
                    _team, ek, pos = all_entities[eid]
                    if pos in conveyors and conveyors[pos]["id"] == eid:
                        del conveyors[pos]
                    for t in (0, 1):
                        if pos in harvesters[t] and harvesters[t][pos]["id"] == eid:
                            del harvesters[t][pos]
                    if eid in builders:
                        actions_this_turn[eid] = "die"

        for bid in builders:
            if bid in actions_this_turn:
                builder_actions[bid].append((turn_idx, actions_this_turn[bid]))
            else:
                builder_actions[bid].append((turn_idx, "idle"))

        if turn_idx % 100 == 0 or turn_idx == len(r.turns) - 1:
            snapshots.append({
                "turn": turn_idx,
                "conveyors": dict(conveyors),
                "harvesters": {t: dict(harvesters[t]) for t in (0, 1)},
            })

    return {
        "w": w, "h": h,
        "core_pos": core_pos,
        "snapshots": snapshots,
        "builder_actions": dict(builder_actions),
        "builder_team": dict(builder_team),
    }


# --- 1. Max flow analysis ---


def compute_max_flow(conveyors: dict, harvesters_t: dict, core_pos: tuple[int, int], team: int, w: int, h: int) -> dict:
    team_convs = {p: c for p, c in conveyors.items() if c["team"] == team}

    reverse_graph = defaultdict(list)
    for pos, c in team_convs.items():
        reverse_graph[c["out"]].append(pos)

    core_tiles = set()
    if core_pos:
        cx, cy = core_pos
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                core_tiles.add((cx + dx, cy + dy))

    results = {}
    for hpos in harvesters_t:
        starts = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                adj = (hpos[0] + dx, hpos[1] + dy)
                if adj in team_convs:
                    starts.append(adj)

        reached = False
        path_len = 0
        path = []

        for start in starts:
            visited = set()
            cur = start
            this_path = []
            for _ in range(200):
                if cur in visited:
                    break
                visited.add(cur)
                this_path.append(cur)
                if cur in core_tiles:
                    reached = True
                    break
                if cur not in team_convs:
                    break
                cur = team_convs[cur]["out"]

            if reached:
                path = this_path
                path_len = len(path)
                break

        if not reached:
            results[hpos] = {"connected": False, "path_len": 0, "bottleneck": None}
            continue

        in_deg = defaultdict(int)
        for pos, c in team_convs.items():
            in_deg[c["out"]] += 1

        max_in = 0
        bottleneck_tile = None
        for tile in path:
            if in_deg[tile] > max_in:
                max_in = in_deg[tile]
                bottleneck_tile = tile

        results[hpos] = {
            "connected": True,
            "path_len": path_len,
            "bottleneck": bottleneck_tile,
            "bottleneck_in_degree": max_in,
        }

    return results


# --- 2. Builder activity analysis ---


def analyze_builders(builder_actions: dict, builder_team: dict) -> tuple[dict, dict]:
    per_team = {0: defaultdict(int), 1: defaultdict(int)}
    per_team_total = {0: 0, 1: 0}

    for bid, actions in builder_actions.items():
        team = builder_team.get(bid, 0)
        for _, action in actions:
            per_team[team][action] += 1
            per_team_total[team] += 1

    return per_team, per_team_total


# --- 3. Raid impact analysis ---


def analyze_raids(r: Replay, core_pos: dict) -> list:
    _w, _h = r.map.width, r.map.height
    conveyors = {}
    harvesters = {0: {}, 1: {}}
    all_entities = {}

    raid_impacts = []

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                all_entities[e.id] = (e.team, ek)
                if ek == "conveyor":
                    d = e.conveyor.direction
                    dx, dy = DIR_DELTA.get(d, (0, 0))
                    out = (pos[0] + dx, pos[1] + dy)
                    conveyors[pos] = {"team": e.team, "out": out, "id": e.id}
                elif ek == "harvester":
                    harvesters[e.team][pos] = e.id

            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid not in all_entities:
                    continue
                team, ek = all_entities[eid]

                if ek == "conveyor":
                    destroyed_pos = None
                    for p, c in list(conveyors.items()):
                        if c["id"] == eid:
                            destroyed_pos = p
                            break
                    if destroyed_pos:
                        1 - team
                        cp = core_pos.get(team)
                        harv_cut = 0
                        if cp:
                            team_convs_after = {p: c for p, c in conveyors.items() if c["team"] == team and p != destroyed_pos}
                            for hpos in harvesters[team]:
                                connected = False
                                for dx in range(-1, 2):
                                    for dy in range(-1, 2):
                                        adj = (hpos[0] + dx, hpos[1] + dy)
                                        if adj in team_convs_after:
                                            cur = adj
                                            visited = set()
                                            for _ in range(200):
                                                if cur in visited:
                                                    break
                                                visited.add(cur)
                                                if abs(cur[0] - cp[0]) <= 1 and abs(cur[1] - cp[1]) <= 1:
                                                    connected = True
                                                    break
                                                if cur not in team_convs_after:
                                                    break
                                                cur = team_convs_after[cur]["out"]
                                            if connected:
                                                break
                                    if connected:
                                        break
                                if not connected:
                                    harv_cut += 1

                        raid_impacts.append({
                            "turn": turn_idx,
                            "pos": destroyed_pos,
                            "victim_team": team,
                            "harvesters_disconnected": harv_cut,
                        })

                        del conveyors[destroyed_pos]

                for t in (0, 1):
                    to_del = [p for p, hid in harvesters[t].items() if hid == eid]
                    for p in to_del:
                        del harvesters[t][p]

    return raid_impacts


# --- 4. Core entry analysis over time ---


def core_entry_timeline(r: Replay, core_pos: dict) -> dict:
    flow_per_turn = {0: defaultdict(int), 1: defaultdict(int)}

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            if u.WhichOneof("kind") == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    to = (mv.to.x, mv.to.y)
                    for t in (0, 1):
                        cp = core_pos.get(t)
                        if cp and abs(to[0] - cp[0]) <= 1 and abs(to[1] - cp[1]) <= 1:
                            flow_per_turn[t][turn_idx] += 1

    return flow_per_turn


# --- Main ---


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    r = parse(path)
    tl = build_timeline(r)

    core_pos = tl["core_pos"]
    w, h = tl["w"], tl["h"]

    print(f"Deep Analysis  |  Map {w}x{h}")
    print()

    for snap in tl["snapshots"]:
        turn = snap["turn"]
        for t in (0, 1):
            conveyors = snap["conveyors"]
            harv = snap["harvesters"][t]
            cp = core_pos.get(t)
            if not cp:
                continue

            flow = compute_max_flow(conveyors, harv, cp, t, w, h)
            connected = sum(1 for v in flow.values() if v["connected"])
            total = len(flow)
            avg_path = sum(v["path_len"] for v in flow.values() if v["connected"]) / max(connected, 1)

            bottlenecks = {}
            for v in flow.values():
                if v["connected"] and v["bottleneck"]:
                    bn = v["bottleneck"]
                    if bn not in bottlenecks:
                        bottlenecks[bn] = 0
                    bottlenecks[bn] += 1

            top_bn = sorted(bottlenecks.items(), key=lambda x: -x[1])[:3]
            bn_str = ", ".join(f"({b[0]},{b[1]})x{c}" for b, c in top_bn) if top_bn else "none"

            if total > 0:
                print(f"  t{turn} Team {TEAM[t]}: {connected}/{total}H connected, avg_path={avg_path:.0f}, bottlenecks=[{bn_str}]")

    print()

    print("Builder Activity:")
    per_team, per_team_total = analyze_builders(tl["builder_actions"], tl["builder_team"])
    for t in (0, 1):
        total = per_team_total[t]
        if total == 0:
            continue
        acts = per_team[t]
        idle_pct = 100 * acts.get("idle", 0) / total
        move_pct = 100 * acts.get("move", 0) / total
        die_pct = 100 * acts.get("die", 0) / total
        print(f"  Team {TEAM[t]}: {total} unit-turns, idle={idle_pct:.0f}% move={move_pct:.0f}% die={die_pct:.0f}%")

    print()

    print("Raid Impact:")
    impacts = analyze_raids(r, core_pos)
    team_impacts = {0: [], 1: []}
    for imp in impacts:
        team_impacts[imp["victim_team"]].append(imp)

    for t in (0, 1):
        imps = team_impacts[t]
        if not imps:
            continue
        total_cut = sum(i["harvesters_disconnected"] for i in imps)
        high_value = [i for i in imps if i["harvesters_disconnected"] >= 2]
        print(f"  Team {TEAM[t]} suffered {len(imps)} raids, {total_cut} total harvester-disconnections")
        if high_value:
            print("  High-value raids (2+ harvesters cut):")
            for i in high_value[:5]:
                print(f"    t{i['turn']} at ({i['pos'][0]},{i['pos'][1]}): cut {i['harvesters_disconnected']} harvesters")

    print()

    print("Core Delivery Timeline:")
    entry = core_entry_timeline(r, core_pos)
    for t in (0, 1):
        flows = entry[t]
        if not flows:
            print(f"  Team {TEAM[t]}: no deliveries")
            continue
        windows = [0, 200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800]
        buckets = []
        for i in range(len(windows) - 1):
            lo, hi = windows[i], windows[i + 1]
            count = sum(v for turn, v in flows.items() if lo <= turn < hi)
            rate = count / (hi - lo) if hi > lo else 0
            buckets.append(f"t{lo}-{hi}:{rate:.1f}/t")
        last_count = sum(v for turn, v in flows.items() if turn >= windows[-1])
        last_rate = last_count / (2000 - windows[-1]) if windows[-1] < 2000 else 0
        buckets.append(f"t{windows[-1]}+:{last_rate:.1f}/t")
        print(f"  Team {TEAM[t]}: {' | '.join(buckets)}")


if __name__ == "__main__":
    main()
