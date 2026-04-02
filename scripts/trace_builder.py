from __future__ import annotations

import sys

from scripts.replay import load_replay

DD = {
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
DN = {0: "C", 1: "N", 2: "NE", 3: "E", 4: "SE", 5: "S", 6: "SW", 7: "W", 8: "NW"}


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    team = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    max_turn = int(sys.argv[3]) if len(sys.argv) > 3 else 120

    r = load_replay(path)

    cores = {}
    for c in r.map.cores:
        cores[c.team] = (c.position.x, c.position.y)
    print(f"Map: {r.map.width}x{r.map.height}  Core[{team}]: {cores.get(team)}")

    entity_team = {}
    entity_type = {}
    bots = {}
    bot_pos = {}
    buildings = {}
    roads = set()
    harvesters = []
    ti = [1000, 1000]

    for i, turn in enumerate(r.turns):
        events = []
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = e.WhichOneof("kind") or "?"
                pos = (e.position.x, e.position.y)
                entity_team[e.id] = e.team
                entity_type[e.id] = ek
                if e.team != team:
                    continue
                if ek == "builder_bot":
                    bots[e.id] = True
                    bot_pos[e.id] = pos
                    events.append(f"  SPAWN bot#{e.id} at {pos}")
                elif ek == "conveyor":
                    d = e.conveyor.direction
                    dx, dy = DD[d]
                    out = (pos[0] + dx, pos[1] + dy)
                    buildings[pos] = ("conv", DN[d], out)
                    roads.discard(pos)
                    events.append(f"  CONV at {pos} dir={DN[d]} out={out}")
                elif ek == "road":
                    roads.add(pos)
                    events.append(f"  ROAD at {pos}")
                elif ek == "harvester":
                    harvesters.append(pos)
                    events.append(f"  HARV at {pos} [team={e.team}]")
            elif k == "move_builder_bot":
                m = u.move_builder_bot
                if m.id in bots:
                    old = bot_pos.get(m.id)
                    new = (m.to.x, m.to.y)
                    bot_pos[m.id] = new
                    events.append(f"  MOVE bot#{m.id} {old}->{new}")
            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in bots:
                    events.append(f"  DIED bot#{eid} at {bot_pos.get(eid)}")
                    del bots[eid]
                t = entity_team.get(eid)
                if t == team and entity_type.get(eid) == "conveyor":
                    events.append(f"  CONV DESTROYED eid={eid}")
            elif k == "update_resources":
                ur = u.update_resources
                ti[ur.team] = ur.titanium

        if events and i < max_turn:
            print(f"t{i}: [Ti={ti[team]}]")
            for e in events:
                print(e)

    cx, cy = cores.get(team, (0, 0))
    print(f"\n=== Final state (turn {len(r.turns)}) ===")
    print(f"Ti: {ti[team]}")
    print(f"Roads: {len(roads)}")
    print(f"Conveyors: {len([v for v in buildings.values() if v[0] == 'conv'])}")
    print(f"Harvesters: {len(harvesters)}")
    print(f"Bots alive: {len(bots)}")

    print("\n=== Chain connectivity ===")
    convs = {}
    for pos, val in buildings.items():
        if val[0] == "conv":
            convs[pos] = val[2]

    connected = 0
    disconnected = 0
    for hpos in harvesters:
        found_chain = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                adj = (hpos[0] + dx, hpos[1] + dy)
                if adj in convs:
                    chain = [adj]
                    cur = convs[adj]
                    seen = {adj}
                    while cur in convs and cur not in seen:
                        seen.add(cur)
                        chain.append(cur)
                        cur = convs[cur]
                    reached = abs(cur[0] - cx) <= 1 and abs(cur[1] - cy) <= 1
                    if reached:
                        connected += 1
                        print(f"  CONNECTED harv@{hpos} chain_len={len(chain)}")
                    else:
                        disconnected += 1
                        print(
                            f"  DEAD END  harv@{hpos} chain_len={len(chain)} ends_at={cur}",
                        )
                    found_chain = True
                    break
            if found_chain:
                break
        else:
            disconnected += 1
            print(f"  NO CHAIN  harv@{hpos}")

    print(f"\nConnected: {connected}/{connected + disconnected}")

    print("\n=== Oscillation detection ===")
    bot_history: dict[int, list[tuple[int, int]]] = {}

    for _i2, turn2 in enumerate(r.turns):
        for u in turn2.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                if e.team == team and e.WhichOneof("kind") == "builder_bot":
                    bot_history[e.id] = [(e.position.x, e.position.y)]
            elif k == "move_builder_bot":
                m = u.move_builder_bot
                if m.id in bot_history:
                    bot_history[m.id].append((m.to.x, m.to.y))
            elif k == "remove_entity":
                eid = u.remove_entity.id
                bot_history.pop(eid, None)

    total_osc_turns = 0
    total_bot_turns = 0
    for bid, hist in bot_history.items():
        total_bot_turns += len(hist)
        osc_turns = 0
        max_run = 0
        cur_run = 0
        worst_start = 0
        for j in range(4, len(hist)):
            window = hist[j - 4 : j + 1]
            positions = set(window)
            if len(positions) <= 2:
                cur_run += 1
                if cur_run > max_run:
                    max_run = cur_run
                    worst_start = j - cur_run
                osc_turns += 1
            else:
                cur_run = 0
        if max_run >= 10:
            pct = 100 * osc_turns / len(hist)
            pts = hist[worst_start] if worst_start < len(hist) else "?"
            print(
                f"  bot#{bid}: {osc_turns}/{len(hist)} turns oscillating ({pct:.0f}%), worst run={max_run} at turn ~{worst_start} near {pts}",
            )
        total_osc_turns += osc_turns

    if total_bot_turns > 0:
        pct = 100 * total_osc_turns / total_bot_turns
        print(
            f"\n  Total: {total_osc_turns}/{total_bot_turns} bot-turns oscillating ({pct:.1f}%)",
        )


if __name__ == "__main__":
    main()
