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


def parse(path: str) -> Replay:
    with open(path, "rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def entity_kind(e):
    return e.WhichOneof("kind") or "unknown"


def trace(start, convs, cp, team) -> bool:
    cur = start
    visited = set()
    for _ in range(200):
        if cur in visited:
            return False
        visited.add(cur)
        if cp and abs(cur[0] - cp[0]) <= 1 and abs(cur[1] - cp[1]) <= 1:
            return True
        if cur not in convs or convs[cur]["team"] != team:
            return False
        cur = convs[cur]["out"]
    return False


def is_connected(hpos, conveyors, core_pos, team) -> bool:
    cp = core_pos.get(team)
    if not cp:
        return False
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            adj = (hpos[0] + dx, hpos[1] + dy)
            if adj in conveyors and trace(adj, conveyors, cp, team):
                return True
    return False


def analyze(r: Replay) -> None:
    core_pos = {}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    conveyors = {}
    harvesters = {0: {}, 1: {}}
    entities = {}
    entity_pos = {}
    harv_born = {0: {}, 1: {}}

    harv_state = {0: {}, 1: {}}
    harv_ever_connected = {0: set(), 1: set()}
    break_events = {0: [], 1: []}
    repair_events = {0: [], 1: []}

    # Destruction tracking
    destructions = {0: defaultdict(int), 1: defaultdict(int)}
    destruction_details = {0: [], 1: []}

    # Scale tracking
    scale_contrib = {0: defaultdict(float), 1: defaultdict(float)}
    scale_map = {
        "conveyor": 1,
        "road": 0.5,
        "harvester": 10,
        "builder_bot": 10,
        "foundry": 100,
        "barrier": 1,
        "splitter": 1,
        "bridge": 1,
        "armoured_conveyor": 1,
        "gunner": 10,
        "sentinel": 10,
        "breach": 10,
        "launcher": 10,
    }

    # Conveyor density around harvesters
    harv_adj_conveyors = {0: {}, 1: {}}

    for turn_idx, turn in enumerate(r.turns):
        hp_changes = {}

        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                entities[e.id] = (e.team, ek)
                entity_pos[e.id] = pos
                scale_contrib[e.team][ek] += scale_map.get(ek, 0)

                if ek in ("conveyor", "armoured_conveyor", "splitter", "bridge"):
                    if ek == "bridge":
                        target = e.bridge.target
                        out = (target.x, target.y)
                    else:
                        sub = getattr(e, ek)
                        d = sub.direction
                        dx, dy = DIR_DELTA.get(d, (0, 0))
                        out = (pos[0] + dx, pos[1] + dy)
                    conveyors[pos] = {
                        "team": e.team,
                        "out": out,
                        "id": e.id,
                    }
                elif ek == "harvester":
                    harvesters[e.team][pos] = e.id
                    harv_born[e.team][pos] = turn_idx

            elif k == "move_builder_bot":
                entity_pos[u.move_builder_bot.id] = (
                    u.move_builder_bot.to.x,
                    u.move_builder_bot.to.y,
                )

            elif k == "update_hp":
                hp_changes[u.update_hp.id] = u.update_hp.delta

            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek = entities[eid]
                    pos = entity_pos.get(eid)
                    scale_contrib[team][ek] -= scale_map.get(ek, 0)

                    if (
                        ek in ("conveyor", "armoured_conveyor", "splitter", "bridge")
                        and pos
                    ):
                        took_damage = eid in hp_changes and hp_changes[eid] < 0
                        attacker_team = None
                        for oid, (ot, oek) in entities.items():
                            if oek == "builder_bot" and entity_pos.get(oid) == pos:
                                attacker_team = ot
                        cause = (
                            "enemy_raid"
                            if took_damage and attacker_team != team
                            else "self_destroy"
                            if not took_damage
                            else "damage"
                        )
                        destructions[team][cause] += 1
                        destruction_details[team].append((turn_idx, pos, cause))
                        del conveyors[pos]

                    for t in (0, 1):
                        if pos in harvesters[t] and harvesters[t][pos] == eid:
                            del harvesters[t][pos]

        for t in (0, 1):
            for hpos in harvesters[t]:
                conn = is_connected(hpos, conveyors, core_pos, t)
                was = harv_state[t].get(hpos)
                if conn:
                    harv_ever_connected[t].add(hpos)
                if was is True and not conn:
                    break_events[t].append((turn_idx, hpos))
                elif was is False and conn:
                    repair_events[t].append((turn_idx, hpos))
                harv_state[t][hpos] = conn

    # Compute final harvester adjacency
    for t in (0, 1):
        for hpos in harvesters[t]:
            count = 0
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    adj = (hpos[0] + dx, hpos[1] + dy)
                    if adj in conveyors and conveyors[adj]["team"] == t:
                        count += 1
            harv_adj_conveyors[t][hpos] = count

    # Print
    for t in (0, 1):
        label = TEAM[t]
        print(f"--- Team {label} ---")

        print("  Chain Health:")
        print(f"    Breaks: {len(break_events[t])}")
        for turn, hpos in break_events[t][:5]:
            born = harv_born[t].get(hpos, "?")
            print(f"      t{turn}: H({hpos[0]},{hpos[1]}) born t{born}")
        print(f"    Repairs: {len(repair_events[t])}")
        for turn, hpos in repair_events[t][:5]:
            print(f"      t{turn}: H({hpos[0]},{hpos[1]})")
        never = sum(1 for h in harvesters[t] if h not in harv_ever_connected[t])
        broken_now = sum(1 for h in harvesters[t] if h in harv_ever_connected[t] and not harv_state[t].get(h, False))
        connected_now = sum(1 for h in harvesters[t] if harv_state[t].get(h, False))
        print(f"    Never connected: {never}/{len(harvesters[t])}")
        print(f"    Connected at end: {connected_now}/{len(harvesters[t])}")
        print(f"    Broken at end: {broken_now}/{len(harvesters[t])}")

        print("  Destruction Causes:")
        for cause, count in sorted(destructions[t].items(), key=lambda x: -x[1]):
            print(f"    {cause}: {count}")

        print("  Scale Breakdown (net):")
        total = 0
        for ek, val in sorted(scale_contrib[t].items(), key=lambda x: -x[1]):
            if val != 0:
                print(f"    {ek}: {val:+.0f}%")
                total += val
        print(f"    TOTAL: {total:+.0f}%")

        print("  Harvester Adjacency (conveyors around each harvester):")
        adj_counts = list(harv_adj_conveyors[t].values())
        if adj_counts:
            avg = sum(adj_counts) / len(adj_counts)
            excess = sum(max(0, c - 1) for c in adj_counts)
            print(f"    avg={avg:.1f} conveyors/harvester, {excess} excess (wasted)")
        print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    analyze(parse(path))


if __name__ == "__main__":
    main()
