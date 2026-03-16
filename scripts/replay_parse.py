import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

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


def dist(a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def collect(r: Replay) -> dict:
    total_turns = len(r.turns)
    map_w, map_h = r.map.width, r.map.height

    placed = {0: Counter(), 1: Counter()}
    removed = {0: Counter(), 1: Counter()}
    entities = {}
    entity_pos = {}
    final_hp = {}
    moves = 0
    total_damage = {0: 0, 1: 0}
    kills = {0: 0, 1: 0}
    tle_count = {0: 0, 1: 0}
    resource_history = {0: [], 1: []}
    conveyor_moves_per_turn = []
    first_built = {0: {}, 1: {}}
    fire_count = {0: Counter(), 1: Counter()}
    exec_time_total = {0: 0, 1: 0}
    exec_time_samples = {0: 0, 1: 0}
    max_exec_time = {0: 0, 1: 0}
    pos_to_entity = {}

    core_positions = {0: None, 1: None}
    first_resource_turn = {0: None, 1: None}

    builder_positions_per_turn = {0: [], 1: []}
    builder_idle_turns = {0: 0, 1: 0}

    conveyor_flow_count = defaultdict(int)

    harvester_ids = {0: set(), 1: set()}
    harvesters_connected = {0: 0, 1: 0}

    builder_acted_this_turn = set()

    self_destructs = {0: 0, 1: 0}

    for turn_idx, turn in enumerate(r.turns):
        conveyor_moves_this_turn = 0
        builder_acted_this_turn.clear()
        turn_builder_positions = {0: [], 1: []}

        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                entities[e.id] = (e.team, ek, e.max_hp)
                entity_pos[e.id] = (e.position.x, e.position.y)
                pos_to_entity[(e.position.x, e.position.y)] = e.id
                final_hp[e.id] = e.hp
                placed[e.team][ek] += 1
                if ek not in first_built[e.team]:
                    first_built[e.team][ek] = turn_idx
                if ek == "core":
                    core_positions[e.team] = (e.position.x, e.position.y)
                if ek == "harvester":
                    harvester_ids[e.team].add(e.id)
                builder_acted_this_turn.add(e.id)
            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                old_pos = entity_pos.get(mb.id)
                if old_pos:
                    pos_to_entity.pop(old_pos, None)
                new_pos = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new_pos
                pos_to_entity[new_pos] = mb.id
                moves += 1
                builder_acted_this_turn.add(mb.id)
            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek, _ = entities[eid]
                    removed[team][ek] += 1
                    if final_hp.get(eid, 0) <= 0:
                        kills[1 - team] += 1
                    old_pos = entity_pos.pop(eid, None)
                    if old_pos:
                        pos_to_entity.pop(old_pos, None)
                    final_hp.pop(eid, None)
                    harvester_ids[team].discard(eid)
                    if ek == "builder_bot":
                        self_destructs[team] += 1
            elif kind == "update_hp":
                eid = u.update_hp.id
                if eid in final_hp:
                    final_hp[eid] += u.update_hp.delta
                if u.update_hp.delta < 0 and eid in entities:
                    victim_team = entities[eid][0]
                    attacker_team = 1 - victim_team
                    total_damage[attacker_team] += abs(u.update_hp.delta)
            elif kind == "fire_turret":
                f = u.fire_turret
                f_from = getattr(f, "from")
                fpos = (f_from.x, f_from.y)
                firer_id = pos_to_entity.get(fpos)
                if firer_id and firer_id in entities:
                    team, ek, _ = entities[firer_id]
                    fire_count[team][ek] += 1
            elif kind == "bot_output":
                bo = u.bot_output
                if bo.id in entities:
                    team = entities[bo.id][0]
                    if bo.tled:
                        tle_count[team] += 1
                    if bo.exec_time_us > 0:
                        exec_time_total[team] += bo.exec_time_us
                        exec_time_samples[team] += 1
                        max_exec_time[team] = max(max_exec_time[team], bo.exec_time_us)
            elif kind == "update_players":
                p = u.update_players.players
                resource_history[0].append(
                    (
                        turn_idx,
                        p.a.titanium,
                        p.a.axionite,
                        p.a.titanium_collected,
                        p.a.axionite_collected,
                    ),
                )
                resource_history[1].append(
                    (
                        turn_idx,
                        p.b.titanium,
                        p.b.axionite,
                        p.b.titanium_collected,
                        p.b.axionite_collected,
                    ),
                )
                for t in (0, 1):
                    rh = resource_history[t]
                    if first_resource_turn[t] is None and len(rh) >= 2:
                        prev_col = rh[-2][3] + rh[-2][4]
                        cur_col = rh[-1][3] + rh[-1][4]
                        if cur_col > prev_col:
                            first_resource_turn[t] = turn_idx
            elif kind == "distribute_resources":
                n_moves = len(u.distribute_resources.moves)
                conveyor_moves_this_turn += n_moves
                for mv in u.distribute_resources.moves:
                    key = (
                        (getattr(mv, "from").x, getattr(mv, "from").y),
                        (mv.to.x, mv.to.y),
                    )
                    conveyor_flow_count[key] += 1

        conveyor_moves_per_turn.append(conveyor_moves_this_turn)

        for eid, (team, ek, _) in entities.items():
            if ek == "builder_bot" and eid in entity_pos and eid in final_hp:
                turn_builder_positions[team].append(entity_pos[eid])
                if eid not in builder_acted_this_turn:
                    builder_idle_turns[team] += 1

        for t in (0, 1):
            builder_positions_per_turn[t].append(turn_builder_positions[t])

    alive = {0: Counter(), 1: Counter()}
    for eid, hp in final_hp.items():
        if eid in entities and hp > 0:
            team, ek, _ = entities[eid]
            alive[team][ek] += 1

    avg_builder_spread = {0: 0.0, 1: 0.0}
    for t in (0, 1):
        all_spreads = []
        for positions in builder_positions_per_turn[t]:
            if len(positions) >= 2:
                dists = [
                    dist(positions[i], positions[j])
                    for i in range(len(positions))
                    for j in range(i + 1, len(positions))
                ]
                all_spreads.append(sum(dists) / len(dists))
        if all_spreads:
            avg_builder_spread[t] = sum(all_spreads) / len(all_spreads)

    builder_active_turns = {0: 0, 1: 0}
    for t in (0, 1):
        for positions in builder_positions_per_turn[t]:
            builder_active_turns[t] += len(positions)

    for t in (0, 1):
        for hid in harvester_ids[t]:
            if hid not in entity_pos:
                continue
            hpos = entity_pos[hid]
            for (frm, _), count in conveyor_flow_count.items():
                if frm == hpos and count > 0:
                    harvesters_connected[t] += 1
                    break

    income_rate = {0: [], 1: []}
    for t in (0, 1):
        rh = resource_history[t]
        window = 100
        for i in range(window, len(rh)):
            dt = rh[i][0] - rh[i - window][0]
            if dt > 0:
                d_ti = rh[i][3] - rh[i - window][3]
                d_ax = rh[i][4] - rh[i - window][4]
                income_rate[t].append((rh[i][0], (d_ti + d_ax) / dt))

    flow_per_tile = {}
    for (frm, _), count in conveyor_flow_count.items():
        flow_per_tile[frm] = flow_per_tile.get(frm, 0) + count

    top_flow_tiles = sorted(flow_per_tile.items(), key=lambda x: -x[1])[:5]

    return {
        "winner": TEAM.get(r.winner, "?") if r.HasField("winner") else "draw",
        "total_turns": total_turns,
        "map_size": (map_w, map_h),
        "placed": placed,
        "removed": removed,
        "alive": alive,
        "moves": moves,
        "total_damage": total_damage,
        "kills": kills,
        "self_destructs": self_destructs,
        "tle_count": tle_count,
        "fire_count": fire_count,
        "resource_history": resource_history,
        "conveyor_moves_per_turn": conveyor_moves_per_turn,
        "first_built": first_built,
        "exec_time_total": exec_time_total,
        "exec_time_samples": exec_time_samples,
        "max_exec_time": max_exec_time,
        "core_positions": core_positions,
        "first_resource_turn": first_resource_turn,
        "avg_builder_spread": avg_builder_spread,
        "builder_idle_turns": builder_idle_turns,
        "builder_active_turns": builder_active_turns,
        "harvesters_connected": harvesters_connected,
        "harvester_count": {t: len(harvester_ids[t]) for t in (0, 1)},
        "income_rate": income_rate,
        "top_flow_tiles": top_flow_tiles,
    }
