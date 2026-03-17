import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))
from cambc_pb2 import Entity, Replay

TEAM = {0: "A", 1: "B"}
TRANSPORT_KINDS = {"conveyor", "armoured_conveyor", "splitter", "bridge"}
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


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def get_output(e: Entity, ek: str, pos: tuple[int, int]) -> tuple[int, int]:
    if ek == "bridge":
        t = e.bridge.target
        return (t.x, t.y)
    sub = getattr(e, ek)
    d = sub.direction
    dx, dy = DIR_DELTA.get(d, (0, 0))
    return (pos[0] + dx, pos[1] + dy)


def analyze_throughput(r: Replay) -> None:
    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height

    core_pos = {0: None, 1: None}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    core_tiles = {0: set(), 1: set()}
    for t in (0, 1):
        cp = core_pos[t]
        if cp:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    core_tiles[t].add((cp[0] + dx, cp[1] + dy))

    conveyors = {}
    harvesters = {0: {}, 1: {}}
    harvester_born = {0: {}, 1: {}}
    entities = {}

    core_deliveries_per_turn = {0: defaultdict(int), 1: defaultdict(int)}
    harvester_output_per_turn = {0: defaultdict(int), 1: defaultdict(int)}
    first_delivery = {0: None, 1: None}

    for turn_idx, turn in enumerate(r.turns):
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                entities[e.id] = (e.team, ek)

                if ek in TRANSPORT_KINDS:
                    out = get_output(e, ek, pos)
                    conveyors[pos] = {"team": e.team, "out": out, "id": e.id}
                elif ek == "harvester":
                    harvesters[e.team][pos] = e.id
                    harvester_born[e.team][pos] = turn_idx

            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek = entities[eid]
                    for p, c in list(conveyors.items()):
                        if c["id"] == eid:
                            del conveyors[p]
                            break
                    for t in (0, 1):
                        for p, hid in list(harvesters[t].items()):
                            if hid == eid:
                                del harvesters[t][p]
                                break

            elif k == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    frm = (getattr(mv, "from").x, getattr(mv, "from").y)
                    to = (mv.to.x, mv.to.y)

                    for t in (0, 1):
                        if frm in harvesters[t]:
                            harvester_output_per_turn[t][turn_idx] += 1

                        if to in core_tiles[t]:
                            core_deliveries_per_turn[t][turn_idx] += 1
                            if first_delivery[t] is None:
                                first_delivery[t] = turn_idx

    print(f"Throughput Analysis  |  {total_turns} turns  |  {w}x{h}")
    print()

    for t in (0, 1):
        label = TEAM[t]
        cp = core_pos[t]
        if not cp:
            print(f"--- Team {label}: no core ---\n")
            continue

        print(f"--- Team {label} ---")

        fd = first_delivery[t]
        print(f"  First delivery to core: {'t' + str(fd) if fd else 'never'}")

        first_harv = min(harvester_born[t].values()) if harvester_born[t] else None
        if first_harv is not None and fd is not None:
            print(f"  First harvester -> first delivery: {fd - first_harv} turns")

        total_harvester_output = sum(harvester_output_per_turn[t].values())
        total_core_delivery = sum(core_deliveries_per_turn[t].values())
        loss = total_harvester_output - total_core_delivery
        loss_pct = 100 * loss / max(total_harvester_output, 1)
        print(f"  Harvester output: {total_harvester_output} stacks")
        print(f"  Core deliveries: {total_core_delivery} stacks")
        print(f"  Flow loss: {loss} stacks ({loss_pct:.0f}%)")

        harv_count = len(harvesters[t]) + len(harvester_born[t]) - len(harvesters[t])
        max_capacity = len(harvester_born[t])
        if max_capacity > 0:
            theoretical = max_capacity * (total_turns / 4)
            efficiency = 100 * total_core_delivery / max(theoretical, 1)
            print(f"  Delivery efficiency: {efficiency:.0f}% of theoretical max")

        windows = [(0, 200), (200, 500), (500, 1000), (1000, 1500), (1500, 2000)]
        rates = []
        for lo, hi in windows:
            count = sum(
                v for turn, v in core_deliveries_per_turn[t].items() if lo <= turn < hi
            )
            rate = count / (hi - lo) if hi > lo else 0
            rates.append(f"t{lo}-{hi}: {rate:.2f}/t")
        print(f"  Delivery rate: {' | '.join(rates)}")

        team_convs = {p: c for p, c in conveyors.items() if c["team"] == t}
        in_degree = defaultdict(int)
        for c in team_convs.values():
            in_degree[c["out"]] += 1

        saturated = []
        for pos, deg in in_degree.items():
            if deg >= 4:
                saturated.append((pos, deg))
        if saturated:
            saturated.sort(key=lambda x: -x[1])
            print("  Potentially saturated tiles (in-degree >= 4):")
            for pos, deg in saturated[:5]:
                print(f"    ({pos[0]},{pos[1]}): {deg} inputs")
        else:
            print("  No saturated tiles (max in-degree < 4)")

        chain_lengths = []
        for hpos in harvester_born[t]:
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    adj = (hpos[0] + dx, hpos[1] + dy)
                    if adj in team_convs:
                        length = 0
                        cur = adj
                        visited = set()
                        while cur in team_convs and cur not in visited:
                            visited.add(cur)
                            length += 1
                            if cur in core_tiles[t]:
                                chain_lengths.append(length)
                                break
                            cur = team_convs[cur]["out"]
                        else:
                            if cur in core_tiles[t]:
                                chain_lengths.append(length)
                        break
                else:
                    continue
                break

        if chain_lengths:
            avg_len = sum(chain_lengths) / len(chain_lengths)
            print(f"  Avg chain length (latency): {avg_len:.0f} turns")
            print(f"  Min/max chain: {min(chain_lengths)}/{max(chain_lengths)}")

        print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    analyze_throughput(parse(path))


if __name__ == "__main__":
    main()
