from __future__ import annotations

from collections import Counter, defaultdict

from .constants import CONVEYOR_KINDS, TEAM_LABEL, TURRET_KINDS, Pos
from .snapshot import core_tiles, entity_kind
from .types import DamageEvent, MapMeta, ResourceSnapshot, ScanData


def scan_replay(replay: object, meta: MapMeta) -> ScanData:
    all_turns = replay.turns  # type: ignore[attr-defined]
    total_turns = len(all_turns)

    winner_raw = replay.winner if replay.HasField("winner") else None  # type: ignore[attr-defined]
    winner = TEAM_LABEL.get(winner_raw, "draw") if winner_raw is not None else "draw"

    placed: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    removed: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    entities: dict[int, tuple[int, str, int]] = {}
    entity_pos: dict[int, Pos] = {}
    building_at: dict[Pos, int] = {}
    final_hp: dict[int, int] = {}

    moves: dict[int, int] = {0: 0, 1: 0}
    total_damage: dict[int, int] = {0: 0, 1: 0}
    entity_kills: dict[int, int] = {0: 0, 1: 0}
    builder_kills_count: dict[int, int] = {0: 0, 1: 0}
    self_destructs_count: dict[int, int] = {0: 0, 1: 0}
    self_destruct_turn_list: dict[int, list[int]] = {0: [], 1: []}
    tle_count: dict[int, int] = {0: 0, 1: 0}
    exec_time_total: dict[int, int] = {0: 0, 1: 0}
    exec_time_samples: dict[int, int] = {0: 0, 1: 0}
    max_exec_time: dict[int, int] = {0: 0, 1: 0}
    fire_count: dict[int, dict[str, int]] = {0: defaultdict(int), 1: defaultdict(int)}

    resource_history: dict[int, list[ResourceSnapshot]] = {0: [], 1: []}
    first_resource_turn: dict[int, int | None] = {0: None, 1: None}
    first_built: dict[int, dict[str, int]] = {0: {}, 1: {}}

    conveyor_moves_per_turn: list[int] = []
    conveyor_flow_count: dict[tuple[Pos, Pos], int] = defaultdict(int)

    core_tile_sets = {t: core_tiles(meta.core_pos, t) for t in (0, 1)}
    core_hp: dict[int, int] = {0: 500, 1: 500}
    core_hp_timeline: dict[int, list[tuple[int, int]]] = {0: [], 1: []}
    core_entity_ids: dict[int, int] = {}

    damage_events: dict[int, list[DamageEvent]] = {0: [], 1: []}
    damage_by_victim: dict[int, dict[str, int]] = {
        0: defaultdict(int),
        1: defaultdict(int),
    }
    buildings_destroyed: dict[int, dict[str, int]] = {
        0: defaultdict(int),
        1: defaultdict(int),
    }
    builder_losses: dict[int, int] = {0: 0, 1: 0}
    turrets_built: dict[int, dict[str, int]] = {
        0: defaultdict(int),
        1: defaultdict(int),
    }
    turret_shots: dict[int, dict[str, int]] = {0: defaultdict(int), 1: defaultdict(int)}
    raid_arrivals: dict[int, list[int]] = {0: [], 1: []}

    core_deliveries_per_turn: dict[int, dict[int, int]] = {
        0: defaultdict(int),
        1: defaultdict(int),
    }
    harvester_output_per_turn: dict[int, dict[int, int]] = {
        0: defaultdict(int),
        1: defaultdict(int),
    }
    first_delivery_turn: dict[int, int | None] = {0: None, 1: None}
    first_conveyor_killed_turn: dict[int, int | None] = {0: None, 1: None}
    harvester_ids: dict[int, set[int]] = {0: set(), 1: set()}
    harvester_positions: dict[int, set[Pos]] = {0: set(), 1: set()}

    builder_idle_turns: dict[int, int] = {0: 0, 1: 0}
    builder_presence_turns: dict[int, int] = {0: 0, 1: 0}
    builder_born: dict[int, int] = {}
    builder_death: dict[int, int] = {}
    builder_team: dict[int, int] = {}
    builder_actions: dict[int, list[tuple[int, str]]] = defaultdict(list)
    builder_pos_history: dict[int, list[tuple[int, Pos]]] = defaultdict(list)

    damaged_this_turn: set[int] = set()
    acted_this_turn: set[int] = set()

    for turn_idx, turn in enumerate(all_turns):
        conv_moves = 0
        damaged_this_turn.clear()
        acted_this_turn.clear()

        for u in turn.updates:
            kind = u.WhichOneof("kind")
            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                team = e.team
                pos: Pos = (e.position.x, e.position.y)
                entities[e.id] = (team, ek, e.max_hp)
                entity_pos[e.id] = pos
                final_hp[e.id] = e.hp
                placed[team][ek] += 1
                acted_this_turn.add(e.id)

                if ek not in ("builder_bot", "marker"):
                    building_at[pos] = e.id
                if ek not in first_built[team]:
                    first_built[team][ek] = turn_idx
                if ek == "core":
                    core_entity_ids[team] = e.id
                elif ek == "harvester":
                    harvester_ids[team].add(e.id)
                    harvester_positions[team].add(pos)
                elif ek in TURRET_KINDS:
                    turrets_built[team][ek] = turrets_built[team].get(ek, 0) + 1
                elif ek == "builder_bot":
                    builder_born[e.id] = turn_idx
                    builder_team[e.id] = team
                    builder_pos_history[e.id].append((turn_idx, pos))
                    builder_actions[e.id].append((turn_idx, "spawn"))

            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                new_pos: Pos = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new_pos
                if mb.id in entities:
                    team = entities[mb.id][0]
                    moves[team] += 1
                    acted_this_turn.add(mb.id)
                    builder_pos_history[mb.id].append((turn_idx, new_pos))
                    builder_actions[mb.id].append((turn_idx, "move"))

                    enemy_core = meta.core_pos.get(1 - team)
                    if enemy_core:
                        dx = abs(new_pos[0] - enemy_core[0])
                        dy = abs(new_pos[1] - enemy_core[1])
                        if dx <= 3 and dy <= 3:
                            raid_arrivals[team].append(turn_idx)

            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek, _ = entities[eid]
                    removed[team][ek] += 1
                    if ek == "builder_bot":
                        builder_losses[team] += 1
                        if eid in damaged_this_turn:
                            builder_kills_count[1 - team] += 1
                        else:
                            self_destructs_count[team] += 1
                            self_destruct_turn_list[team].append(turn_idx)
                        builder_death[eid] = turn_idx
                        builder_actions[eid].append((turn_idx, "die"))
                        acted_this_turn.add(eid)
                    elif ek != "marker":
                        if eid in damaged_this_turn:
                            entity_kills[1 - team] += 1
                            buildings_destroyed[1 - team][ek] = (
                                buildings_destroyed[1 - team].get(ek, 0) + 1
                            )
                            if (
                                ek in CONVEYOR_KINDS
                                and first_conveyor_killed_turn[team] is None
                            ):
                                first_conveyor_killed_turn[team] = turn_idx
                    epos = entity_pos.pop(eid, None)
                    if epos and building_at.get(epos) == eid:
                        del building_at[epos]
                    final_hp.pop(eid, None)
                    harvester_ids[team].discard(eid)

            elif kind == "update_hp":
                eid = u.update_hp.id
                delta = u.update_hp.delta
                if eid in final_hp:
                    final_hp[eid] += delta
                if delta < 0 and eid in entities:
                    damaged_this_turn.add(eid)
                    victim_team, victim_type, _ = entities[eid]
                    attacker = 1 - victim_team
                    dmg = abs(delta)
                    total_damage[attacker] += dmg
                    damage_events[attacker].append(
                        DamageEvent(turn_idx, dmg, victim_type),
                    )
                    damage_by_victim[attacker][victim_type] = (
                        damage_by_victim[attacker].get(victim_type, 0) + dmg
                    )
                    for t in (0, 1):
                        if eid == core_entity_ids.get(t):
                            core_hp[t] = max(0, core_hp[t] + delta)
                            core_hp_timeline[t].append((turn_idx, core_hp[t]))

            elif kind == "fire_turret":
                f = u.fire_turret
                f_from = getattr(f, "from")
                fpos: Pos = (f_from.x, f_from.y)
                fid = building_at.get(fpos)
                if fid and fid in entities:
                    team, ek, _ = entities[fid]
                    turret_shots[team][ek] = turret_shots[team].get(ek, 0) + 1
                    fire_count[team][ek] = fire_count[team].get(ek, 0) + 1

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
                for t, player in ((0, p.a), (1, p.b)):
                    rs = ResourceSnapshot(
                        turn_idx,
                        player.titanium,
                        player.axionite,
                        player.titanium_collected,
                        player.axionite_collected,
                    )
                    rh = resource_history[t]
                    rh.append(rs)
                    if first_resource_turn[t] is None and len(rh) >= 2:
                        prev = rh[-2]
                        if (rs.titanium_collected + rs.axionite_collected) > (
                            prev.titanium_collected + prev.axionite_collected
                        ):
                            first_resource_turn[t] = turn_idx

            elif kind == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    frm: Pos = (getattr(mv, "from").x, getattr(mv, "from").y)
                    to: Pos = (mv.to.x, mv.to.y)
                    conv_moves += 1
                    conveyor_flow_count[(frm, to)] += 1
                    for t in (0, 1):
                        if frm in harvester_positions[t]:
                            harvester_output_per_turn[t][turn_idx] = (
                                harvester_output_per_turn[t].get(turn_idx, 0) + 1
                            )
                        if to in core_tile_sets[t]:
                            core_deliveries_per_turn[t][turn_idx] = (
                                core_deliveries_per_turn[t].get(turn_idx, 0) + 1
                            )
                            if first_delivery_turn[t] is None:
                                first_delivery_turn[t] = turn_idx

        conveyor_moves_per_turn.append(conv_moves)

        for eid, (team, ek, _) in entities.items():
            if ek == "builder_bot" and eid in final_hp:
                builder_presence_turns[team] = builder_presence_turns.get(team, 0) + 1
                if eid not in acted_this_turn:
                    builder_idle_turns[team] = builder_idle_turns.get(team, 0) + 1
                    builder_actions[eid].append((turn_idx, "idle"))

    alive: dict[int, dict[str, int]] = {0: {}, 1: {}}
    for eid, hp in final_hp.items():
        if eid in entities and hp > 0:
            team, ek, _ = entities[eid]
            alive[team][ek] = alive[team].get(ek, 0) + 1

    income_rate: dict[int, list[tuple[int, float]]] = {0: [], 1: []}
    window = 100
    for t in (0, 1):
        rh = resource_history[t]
        for i in range(window, len(rh)):
            dt = rh[i].turn - rh[i - window].turn
            if dt > 0:
                d_ti = rh[i].titanium_collected - rh[i - window].titanium_collected
                d_ax = rh[i].axionite_collected - rh[i - window].axionite_collected
                income_rate[t].append((rh[i].turn, (d_ti + d_ax) / dt))

    flow_per_tile: dict[Pos, int] = {}
    for (frm, _), count in conveyor_flow_count.items():
        flow_per_tile[frm] = flow_per_tile.get(frm, 0) + count
    top_flow = sorted(flow_per_tile.items(), key=lambda x: -x[1])[:5]

    harvesters_connected: dict[int, int] = {0: 0, 1: 0}
    for t in (0, 1):
        for hid in harvester_ids[t]:
            hpos = entity_pos.get(hid)
            if hpos and any(
                conveyor_flow_count.get((hpos, _to), 0) > 0
                for _to in [
                    (hpos[0] + dx, hpos[1] + dy)
                    for dx in range(-1, 2)
                    for dy in range(-1, 2)
                    if dx != 0 or dy != 0
                ]
            ):
                harvesters_connected[t] += 1

    return ScanData(
        total_turns=total_turns,
        winner=winner,
        resource_history=resource_history,
        entities_placed={t: dict(placed[t]) for t in (0, 1)},
        entities_removed={t: dict(removed[t]) for t in (0, 1)},
        entities_alive=alive,
        first_built=first_built,
        total_moves=moves,
        total_damage=total_damage,
        entity_kills=entity_kills,
        builder_kills=builder_kills_count,
        self_destructs=self_destructs_count,
        self_destruct_turns=self_destruct_turn_list,
        tle_count=tle_count,
        exec_time_total=exec_time_total,
        exec_time_samples=exec_time_samples,
        max_exec_time=max_exec_time,
        fire_count={t: dict(fire_count[t]) for t in (0, 1)},
        conveyor_moves_per_turn=conveyor_moves_per_turn,
        conveyor_flow_count=dict(conveyor_flow_count),
        first_resource_turn=first_resource_turn,
        income_rate=income_rate,
        top_flow_tiles=top_flow,
        damage_events=damage_events,
        damage_by_victim={t: dict(damage_by_victim[t]) for t in (0, 1)},
        buildings_destroyed={t: dict(buildings_destroyed[t]) for t in (0, 1)},
        builder_losses=builder_losses,
        turrets_built={t: dict(turrets_built[t]) for t in (0, 1)},
        turret_shots={t: dict(turret_shots[t]) for t in (0, 1)},
        raid_arrivals=raid_arrivals,
        core_hp_timeline=core_hp_timeline,
        core_deliveries_per_turn={t: dict(core_deliveries_per_turn[t]) for t in (0, 1)},
        harvester_output_per_turn={
            t: dict(harvester_output_per_turn[t]) for t in (0, 1)
        },
        first_delivery_turn=first_delivery_turn,
        first_conveyor_killed_turn=first_conveyor_killed_turn,
        builder_idle_turns=builder_idle_turns,
        builder_presence_turns=builder_presence_turns,
        builder_born=builder_born,
        builder_death=builder_death,
        builder_team=builder_team,
        builder_actions=dict(builder_actions),
        builder_pos_history=dict(builder_pos_history),
        harvester_count={t: len(harvester_ids[t]) for t in (0, 1)},
        harvesters_connected=harvesters_connected,
    )
