from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from analysis.constants import CONVEYOR_KINDS, Pos
from analysis.parse import extract_map_meta, parse
from analysis.snapshot import core_tiles, entity_kind

REPLAYS_DIR = Path(__file__).resolve().parent.parent / "replays_all"
INDEX_PATH = REPLAYS_DIR / "index.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "features.csv"

SNAPSHOT_TURNS = [50, 100, 200, 300, 500, 750, 1000]
ENTITY_TYPES = [
    "builder_bot",
    "conveyor",
    "armoured_conveyor",
    "splitter",
    "bridge",
    "harvester",
    "foundry",
    "gunner",
    "sentinel",
    "breach",
    "launcher",
    "road",
    "barrier",
]
TURRET_TYPES = ["gunner", "sentinel", "breach", "launcher"]
CONVEYOR_TYPES = ["conveyor", "armoured_conveyor", "splitter", "bridge"]

WORKERS = 8


def chebyshev(a: Pos, b: Pos) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def euclidean_sq(a: Pos, b: Pos) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def extract_features(replay_path: str) -> dict[str, object] | None:
    try:
        replay = parse(replay_path)
    except (OSError, ValueError, KeyError):
        return None

    meta = extract_map_meta(replay)
    all_turns = replay.turns  # type: ignore[attr-defined]
    total_turns = len(all_turns)
    if total_turns < 10:
        return None

    winner_raw = replay.winner if replay.HasField("winner") else None  # type: ignore[attr-defined]
    winner = winner_raw if winner_raw is not None else -1

    row: dict[str, object] = {}
    row["replay"] = Path(replay_path).stem
    row["total_turns"] = total_turns
    row["winner"] = winner

    # ── map features ──
    row["map_w"] = meta.width
    row["map_h"] = meta.height
    row["map_area"] = meta.width * meta.height
    row["map_passable"] = meta.passable_count
    row["map_passable_pct"] = meta.passable_count / (meta.width * meta.height)
    ti_ore = sum(1 for _, _, t in meta.ore_tiles if t == "titanium")
    ax_ore = sum(1 for _, _, t in meta.ore_tiles if t == "axionite")
    row["map_ti_ore"] = ti_ore
    row["map_ax_ore"] = ax_ore
    row["map_total_ore"] = ti_ore + ax_ore
    c0 = meta.core_pos.get(0, (0, 0))
    c1 = meta.core_pos.get(1, (0, 0))
    row["core_dist_cheb"] = chebyshev(c0, c1)
    row["core_dist_sq"] = euclidean_sq(c0, c1)

    # ── per-team state tracking ──
    entities: dict[int, tuple[int, str, int]] = {}
    entity_pos: dict[int, Pos] = {}
    entity_hp: dict[int, int] = {}
    building_at: dict[Pos, int] = {}
    core_tile_sets = {t: core_tiles(meta.core_pos, t) for t in (0, 1)}
    core_entity_ids: dict[int, int] = {}

    # counters per team
    placed: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    removed: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    alive_count: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    moves: dict[int, int] = {0: 0, 1: 0}
    total_damage: dict[int, int] = {0: 0, 1: 0}
    damage_by_victim: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    buildings_destroyed: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    builder_kills: dict[int, int] = {0: 0, 1: 0}
    self_destructs: dict[int, int] = {0: 0, 1: 0}
    tle_count: dict[int, int] = {0: 0, 1: 0}
    exec_total: dict[int, int] = {0: 0, 1: 0}
    exec_samples: dict[int, int] = {0: 0, 1: 0}
    exec_max: dict[int, int] = {0: 0, 1: 0}
    turret_shots: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}
    fire_count: dict[int, int] = {0: 0, 1: 0}

    # timing
    first_built: dict[int, dict[str, int]] = {0: {}, 1: {}}
    first_resource_turn: dict[int, int | None] = {0: None, 1: None}
    first_delivery_turn: dict[int, int | None] = {0: None, 1: None}
    first_conveyor_killed: dict[int, int | None] = {0: None, 1: None}
    first_core_damage: dict[int, int | None] = {0: None, 1: None}
    first_raid: dict[int, int | None] = {0: None, 1: None}
    raid_count: dict[int, int] = {0: 0, 1: 0}

    # resources
    ti_collected: dict[int, int] = {0: 0, 1: 0}
    ax_collected: dict[int, int] = {0: 0, 1: 0}
    ti_current: dict[int, int] = {0: 1000, 1: 1000}
    ax_current: dict[int, int] = {0: 0, 1: 0}
    # income tracking (rolling window)
    income_history: dict[int, list[tuple[int, int]]] = {0: [], 1: []}
    peak_income: dict[int, float] = {0: 0.0, 1: 0.0}

    # core hp
    core_hp: dict[int, int] = {0: 500, 1: 500}
    min_core_hp: dict[int, int] = {0: 500, 1: 500}

    # flow
    conv_moves_total = 0
    conv_moves_peak = 0
    core_deliveries: dict[int, int] = {0: 0, 1: 0}
    harvester_positions: dict[int, set[Pos]] = {0: set(), 1: set()}
    harvester_outputs: dict[int, int] = {0: 0, 1: 0}

    # builder trace stats
    builder_born: dict[int, int] = {}
    builder_team: dict[int, int] = {}
    builder_prev_pos: dict[int, Pos] = {}
    builder_dist_traveled: dict[int, int] = {0: 0, 1: 0}
    builder_idle_turns: dict[int, int] = {0: 0, 1: 0}
    builder_presence_turns: dict[int, int] = {0: 0, 1: 0}
    builder_max_core_dist: dict[int, int] = {0: 0, 1: 0}
    builder_sum_core_dist: dict[int, int] = {0: 0, 1: 0}
    builder_core_dist_samples: dict[int, int] = {0: 0, 1: 0}
    builder_oscillation_count: dict[int, int] = {0: 0, 1: 0}
    builder_pos_window: dict[int, list[Pos]] = {}
    builder_builds: dict[int, int] = {0: 0, 1: 0}
    builder_heals: dict[int, int] = {0: 0, 1: 0}
    builder_near_enemy_turns: dict[int, int] = {0: 0, 1: 0}
    builder_near_own_infra_turns: dict[int, int] = {0: 0, 1: 0}

    # snapshot collection
    snapshot_data: dict[int, dict[int, dict[str, int]]] = {}
    snapshot_resources: dict[int, dict[int, dict[str, int]]] = {}
    snapshot_turn_set = set(SNAPSHOT_TURNS)

    acted_this_turn: set[int] = set()
    damaged_this_turn: set[int] = set()

    for turn_idx, turn in enumerate(all_turns):
        conv_moves_this = 0
        acted_this_turn.clear()
        damaged_this_turn.clear()

        for u in turn.updates:
            kind = u.WhichOneof("kind")

            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                team = e.team
                pos: Pos = (e.position.x, e.position.y)
                entities[e.id] = (team, ek, e.max_hp)
                entity_pos[e.id] = pos
                entity_hp[e.id] = e.hp
                placed[team][ek] += 1
                alive_count[team][ek] += 1
                acted_this_turn.add(e.id)

                if ek not in ("builder_bot", "marker"):
                    building_at[pos] = e.id
                if ek not in first_built[team]:
                    first_built[team][ek] = turn_idx
                if ek == "core":
                    core_entity_ids[team] = e.id
                elif ek == "harvester":
                    harvester_positions[team].add(pos)
                elif ek == "builder_bot":
                    builder_born[e.id] = turn_idx
                    builder_team[e.id] = team
                    builder_prev_pos[e.id] = pos
                    builder_pos_window[e.id] = [pos]
                    builder_builds[team] += 1

                    own_core = meta.core_pos.get(team, (0, 0))
                    d = chebyshev(pos, own_core)
                    builder_sum_core_dist[team] += d
                    builder_core_dist_samples[team] += 1

            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                new_pos: Pos = (mb.to.x, mb.to.y)
                old_pos = entity_pos.get(mb.id, new_pos)
                entity_pos[mb.id] = new_pos
                if mb.id in entities:
                    team = entities[mb.id][0]
                    moves[team] += 1
                    acted_this_turn.add(mb.id)

                    dist = abs(new_pos[0] - old_pos[0]) + abs(new_pos[1] - old_pos[1])
                    builder_dist_traveled[team] += dist

                    own_core = meta.core_pos.get(team, (0, 0))
                    d = chebyshev(new_pos, own_core)
                    builder_max_core_dist[team] = max(builder_max_core_dist[team], d)
                    builder_sum_core_dist[team] += d
                    builder_core_dist_samples[team] += 1

                    enemy_core = meta.core_pos.get(1 - team)
                    if enemy_core and chebyshev(new_pos, enemy_core) <= 3:
                        raid_count[team] += 1
                        if first_raid[team] is None:
                            first_raid[team] = turn_idx

                    if enemy_core and chebyshev(new_pos, enemy_core) <= 8:
                        builder_near_enemy_turns[team] += 1

                    own_infra = harvester_positions[team]
                    if own_infra:
                        nearest = min(chebyshev(new_pos, p) for p in own_infra)
                        if nearest <= 3:
                            builder_near_own_infra_turns[team] += 1

                    window = builder_pos_window.get(mb.id)
                    if window is not None:
                        window.append(new_pos)
                        if len(window) > 10:
                            window.pop(0)
                        if len(window) == 10 and len(set(window)) <= 2:
                            builder_oscillation_count[team] += 1

                    builder_prev_pos[mb.id] = new_pos

            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek, _ = entities[eid]
                    removed[team][ek] += 1
                    alive_count[team][ek] = max(0, alive_count[team][ek] - 1)

                    if ek == "builder_bot":
                        if eid in damaged_this_turn:
                            builder_kills[1 - team] += 1
                        else:
                            self_destructs[team] += 1
                        builder_prev_pos.pop(eid, None)
                        builder_pos_window.pop(eid, None)
                        acted_this_turn.add(eid)
                    elif ek != "marker":
                        if eid in damaged_this_turn:
                            buildings_destroyed[1 - team][ek] += 1
                            if ek in CONVEYOR_KINDS and first_conveyor_killed[team] is None:
                                first_conveyor_killed[team] = turn_idx

                    epos = entity_pos.pop(eid, None)
                    if epos and building_at.get(epos) == eid:
                        del building_at[epos]
                    entity_hp.pop(eid, None)
                    if ek == "harvester" and epos:
                        harvester_positions[team].discard(epos)

            elif kind == "update_hp":
                eid = u.update_hp.id
                delta = u.update_hp.delta
                if eid in entity_hp:
                    entity_hp[eid] += delta
                if delta < 0 and eid in entities:
                    damaged_this_turn.add(eid)
                    victim_team, victim_type, _ = entities[eid]
                    attacker = 1 - victim_team
                    dmg = abs(delta)
                    total_damage[attacker] += dmg
                    damage_by_victim[attacker][victim_type] += dmg

                    for t in (0, 1):
                        if eid == core_entity_ids.get(t):
                            core_hp[t] = max(0, core_hp[t] + delta)
                            min_core_hp[t] = min(min_core_hp[t], core_hp[t])
                            if first_core_damage[t] is None:
                                first_core_damage[t] = turn_idx
                elif delta > 0 and eid in entities:
                    healer_team = entities[eid][0]
                    builder_heals[healer_team] += 1

            elif kind == "fire_turret":
                f = u.fire_turret
                f_from = getattr(f, "from")
                fpos: Pos = (f_from.x, f_from.y)
                fid = building_at.get(fpos)
                if fid and fid in entities:
                    team, ek, _ = entities[fid]
                    turret_shots[team][ek] += 1
                    fire_count[team] += 1

            elif kind == "bot_output":
                bo = u.bot_output
                if bo.id in entities:
                    team = entities[bo.id][0]
                    if bo.tled:
                        tle_count[team] += 1
                    if bo.exec_time_us > 0:
                        exec_total[team] += bo.exec_time_us
                        exec_samples[team] += 1
                        exec_max[team] = max(exec_max[team], bo.exec_time_us)
                acted_this_turn.add(bo.id)
                if bo.id in entities:
                    team = entities[bo.id][0]
                    ek = entities[bo.id][1]
                    if ek == "builder_bot" and hasattr(bo, "built") and bo.built:
                        builder_builds[team] += 1

            elif kind == "update_players":
                p = u.update_players.players
                for t, player in ((0, p.a), (1, p.b)):
                    old_ti = ti_collected[t]
                    ti_collected[t] = player.titanium_collected
                    ax_collected[t] = player.axionite_collected
                    ti_current[t] = player.titanium
                    ax_current[t] = player.axionite
                    if first_resource_turn[t] is None and ti_collected[t] > old_ti:
                        first_resource_turn[t] = turn_idx

                    income_history[t].append((turn_idx, ti_collected[t] + ax_collected[t]))
                    if len(income_history[t]) >= 2:
                        hist = income_history[t]
                        lookback = min(100, len(hist) - 1)
                        dt = hist[-1][0] - hist[-1 - lookback][0]
                        if dt > 0:
                            dr = hist[-1][1] - hist[-1 - lookback][1]
                            rate = dr / dt
                            peak_income[t] = max(peak_income[t], rate)

            elif kind == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    frm: Pos = (getattr(mv, "from").x, getattr(mv, "from").y)
                    to: Pos = (mv.to.x, mv.to.y)
                    conv_moves_this += 1
                    for t in (0, 1):
                        if frm in harvester_positions[t]:
                            harvester_outputs[t] += 1
                        if to in core_tile_sets[t]:
                            core_deliveries[t] += 1
                            if first_delivery_turn[t] is None:
                                first_delivery_turn[t] = turn_idx

            elif kind == "heal_entity":
                h = u.heal_entity
                if h.id in entities:
                    team = entities[h.id][0]
                    builder_heals[team] += 1

        conv_moves_total += conv_moves_this
        conv_moves_peak = max(conv_moves_peak, conv_moves_this)

        # builder idle tracking
        for eid, (team, ek, _) in entities.items():
            if ek == "builder_bot" and eid in entity_hp:
                builder_presence_turns[team] += 1
                if eid not in acted_this_turn:
                    builder_idle_turns[team] += 1

        # snapshot at key turns
        if turn_idx in snapshot_turn_set:
            for t in (0, 1):
                counts = dict(alive_count[t])
                if turn_idx not in snapshot_data:
                    snapshot_data[turn_idx] = {}
                snapshot_data[turn_idx][t] = counts
            if turn_idx not in snapshot_resources:
                snapshot_resources[turn_idx] = {}
            for t in (0, 1):
                snapshot_resources[turn_idx][t] = {
                    "ti": ti_current[t],
                    "ax": ax_current[t],
                    "ti_collected": ti_collected[t],
                    "ax_collected": ax_collected[t],
                }

    # ── write features ──

    # map
    # (already written above)

    # per-team features
    for t in (0, 1):
        p = f"t{t}_"

        # timing
        row[p + "first_resource"] = first_resource_turn[t]
        row[p + "first_delivery"] = first_delivery_turn[t]
        row[p + "first_conv_killed"] = first_conveyor_killed[t]
        row[p + "first_core_dmg"] = first_core_damage[t]
        row[p + "first_raid"] = first_raid[t]
        row[p + "raid_count"] = raid_count[t]

        for etype in ENTITY_TYPES:
            fb = first_built[t].get(etype)
            row[p + f"first_{etype}"] = fb

        # final resources
        row[p + "final_ti"] = ti_current[t]
        row[p + "final_ax"] = ax_current[t]
        row[p + "ti_collected"] = ti_collected[t]
        row[p + "ax_collected"] = ax_collected[t]
        row[p + "peak_income"] = round(peak_income[t], 3)

        # entity totals
        for etype in ENTITY_TYPES:
            row[p + f"placed_{etype}"] = placed[t].get(etype, 0)
            row[p + f"removed_{etype}"] = removed[t].get(etype, 0)
            row[p + f"alive_{etype}"] = alive_count[t].get(etype, 0)

        row[p + "total_placed"] = sum(placed[t].values())
        row[p + "total_conveyors_placed"] = sum(placed[t].get(c, 0) for c in CONVEYOR_TYPES)
        row[p + "total_turrets_placed"] = sum(placed[t].get(c, 0) for c in TURRET_TYPES)

        # combat
        row[p + "total_damage"] = total_damage[t]
        row[p + "builder_kills"] = builder_kills[t]
        row[p + "self_destructs"] = self_destructs[t]
        row[p + "buildings_destroyed_total"] = sum(buildings_destroyed[t].values())
        for etype in ENTITY_TYPES:
            row[p + f"destroyed_{etype}"] = buildings_destroyed[t].get(etype, 0)
        row[p + "dmg_to_core"] = damage_by_victim[t].get("core", 0)
        row[p + "dmg_to_builders"] = damage_by_victim[t].get("builder_bot", 0)
        row[p + "dmg_to_conveyors"] = sum(
            damage_by_victim[t].get(c, 0) for c in CONVEYOR_TYPES
        )
        row[p + "dmg_to_harvesters"] = damage_by_victim[t].get("harvester", 0)
        row[p + "dmg_to_turrets"] = sum(
            damage_by_victim[t].get(c, 0) for c in TURRET_TYPES
        )
        row[p + "fire_count"] = fire_count[t]
        for tt in TURRET_TYPES:
            row[p + f"shots_{tt}"] = turret_shots[t].get(tt, 0)

        # core hp
        row[p + "core_hp"] = core_hp[t]
        row[p + "min_core_hp"] = min_core_hp[t]

        # flow
        row[p + "core_deliveries"] = core_deliveries[t]
        row[p + "harvester_outputs"] = harvester_outputs[t]

        # moves
        row[p + "total_moves"] = moves[t]

        # builder trace
        row[p + "builder_dist_traveled"] = builder_dist_traveled[t]
        row[p + "builder_idle_turns"] = builder_idle_turns[t]
        row[p + "builder_presence_turns"] = builder_presence_turns[t]
        idle_pct = (
            builder_idle_turns[t] / builder_presence_turns[t]
            if builder_presence_turns[t] > 0
            else 0.0
        )
        row[p + "builder_idle_pct"] = round(idle_pct, 4)
        row[p + "builder_max_core_dist"] = builder_max_core_dist[t]
        avg_core_dist = (
            builder_sum_core_dist[t] / builder_core_dist_samples[t]
            if builder_core_dist_samples[t] > 0
            else 0.0
        )
        row[p + "builder_avg_core_dist"] = round(avg_core_dist, 2)
        row[p + "builder_oscillation"] = builder_oscillation_count[t]
        row[p + "builder_near_enemy_turns"] = builder_near_enemy_turns[t]
        row[p + "builder_near_own_infra_turns"] = builder_near_own_infra_turns[t]
        row[p + "builder_heals"] = builder_heals[t]

        # efficiency
        row[p + "tle_count"] = tle_count[t]
        avg_exec = (
            exec_total[t] / exec_samples[t] if exec_samples[t] > 0 else 0
        )
        row[p + "avg_exec_us"] = round(avg_exec, 1)
        row[p + "max_exec_us"] = exec_max[t]

        # snapshots
        for st in SNAPSHOT_TURNS:
            sp = f"{p}t{st}_"
            if st in snapshot_data and t in snapshot_data[st]:
                counts = snapshot_data[st][t]
                for etype in ENTITY_TYPES:
                    row[sp + etype] = counts.get(etype, 0)
                row[sp + "total_conveyors"] = sum(
                    counts.get(c, 0) for c in CONVEYOR_TYPES
                )
                row[sp + "total_turrets"] = sum(
                    counts.get(c, 0) for c in TURRET_TYPES
                )
            else:
                for etype in ENTITY_TYPES:
                    row[sp + etype] = None
                row[sp + "total_conveyors"] = None
                row[sp + "total_turrets"] = None

            if st in snapshot_resources and t in snapshot_resources[st]:
                r = snapshot_resources[st][t]
                row[sp + "ti"] = r["ti"]
                row[sp + "ax"] = r["ax"]
                row[sp + "ti_collected"] = r["ti_collected"]
                row[sp + "ax_collected"] = r["ax_collected"]
            else:
                row[sp + "ti"] = None
                row[sp + "ax"] = None
                row[sp + "ti_collected"] = None
                row[sp + "ax_collected"] = None

    # global flow
    row["conv_moves_total"] = conv_moves_total
    row["conv_moves_peak"] = conv_moves_peak
    avg_conv = conv_moves_total / total_turns if total_turns > 0 else 0
    row["conv_moves_avg"] = round(avg_conv, 2)

    # ── delta features (t0 - t1) ──
    for feat in [
        "first_resource",
        "first_delivery",
        "first_conv_killed",
        "first_core_dmg",
        "first_raid",
        "ti_collected",
        "ax_collected",
        "peak_income",
        "total_damage",
        "core_hp",
        "total_moves",
        "builder_idle_pct",
        "builder_oscillation",
        "total_placed",
        "total_conveyors_placed",
        "total_turrets_placed",
        "placed_harvester",
        "core_deliveries",
        "builder_near_enemy_turns",
        "fire_count",
    ]:
        v0 = row.get(f"t0_{feat}")
        v1 = row.get(f"t1_{feat}")
        if v0 is not None and v1 is not None:
            row[f"delta_{feat}"] = v0 - v1  # type: ignore[operator]
        else:
            row[f"delta_{feat}"] = None

    # ── ratio features ──
    for t in (0, 1):
        p = f"t{t}_"
        ti = ti_collected[t]
        if ti > 0:
            row[p + "turret_invest_pct"] = round(
                sum(placed[t].get(c, 0) for c in TURRET_TYPES) * 10 / ti, 4,
            )
            row[p + "conv_invest_pct"] = round(
                sum(placed[t].get(c, 0) for c in CONVEYOR_TYPES) * 3 / ti, 4,
            )
            row[p + "harvester_invest_pct"] = round(
                placed[t].get("harvester", 0) * 80 / ti, 4,
            )
        else:
            row[p + "turret_invest_pct"] = 0.0
            row[p + "conv_invest_pct"] = 0.0
            row[p + "harvester_invest_pct"] = 0.0

        total_conv_placed = sum(placed[t].get(c, 0) for c in CONVEYOR_TYPES)
        if total_conv_placed > 0:
            row[p + "conv_survival_pct"] = round(
                sum(alive_count[t].get(c, 0) for c in CONVEYOR_TYPES) / total_conv_placed,
                4,
            )
        else:
            row[p + "conv_survival_pct"] = None

        if builder_presence_turns[t] > 0:
            row[p + "builds_per_presence"] = round(
                sum(placed[t].values()) / builder_presence_turns[t], 4,
            )
            row[p + "dist_per_presence"] = round(
                builder_dist_traveled[t] / builder_presence_turns[t], 4,
            )
        else:
            row[p + "builds_per_presence"] = 0.0
            row[p + "dist_per_presence"] = 0.0

        harv = placed[t].get("harvester", 0)
        if harv > 0:
            row[p + "deliveries_per_harvester"] = round(core_deliveries[t] / harv, 2)
        else:
            row[p + "deliveries_per_harvester"] = 0.0

    return row


def process_one(args: tuple[str, str]) -> tuple[str, dict[str, object] | None]:
    key, path = args
    return key, extract_features(path)


def main() -> None:
    if not INDEX_PATH.exists():
        print(f"No index at {INDEX_PATH}")
        sys.exit(1)

    index: dict[str, dict] = json.loads(INDEX_PATH.read_text())
    tasks: list[tuple[str, str]] = []
    for key, entry in index.items():
        mid = entry["matchId"]
        g = entry["game"]
        path = REPLAYS_DIR / f"{mid}_g{g}.replay26"
        if path.exists():
            tasks.append((key, str(path)))

    print(f"Extracting features from {len(tasks)} replays ({WORKERS} workers)...")
    t0 = time.time()

    rows: list[dict[str, object]] = []
    done = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_one, t): t for t in tasks}
        for future in as_completed(futures):
            key, row = future.result()
            if row is not None:
                rows.append(row)
                done += 1
            else:
                failed += 1
            total = done + failed
            if total % 500 == 0:
                elapsed = time.time() - t0
                rate = total / elapsed if elapsed > 0 else 0
                eta = (len(tasks) - total) / rate if rate > 0 else 0
                pct = total * 100 // len(tasks)
                bar = f"[{'#' * (pct // 2)}{'-' * (50 - pct // 2)}]"
                print(
                    f"\r  {bar} {pct}%  {total}/{len(tasks)}  {rate:.0f}/s  ETA {eta:.0f}s  ({failed} fail)",
                    end="",
                    flush=True,
                )

    print()
    elapsed = time.time() - t0
    print(f"Done: {done} extracted, {failed} failed in {elapsed:.0f}s")

    if not rows:
        print("No features extracted.")
        return

    fieldnames = list(rows[0].keys())
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows x {len(fieldnames)} columns to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
