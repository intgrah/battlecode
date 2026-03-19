from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from analysis.constants import SCALE_PCT, TURRET_KINDS, Pos
from analysis.parse import extract_map_meta, parse
from analysis.snapshot import core_tiles, entity_kind

REPLAYS_DIR = Path(__file__).resolve().parent.parent / "replays_all"
INDEX_PATH = REPLAYS_DIR / "index.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "features.csv"

SNAPSHOT_TURNS = [50, 100, 200, 400, 700, 1000, 1500]
BUILDING_TYPES = [
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
TURRET_TYPE_MAP = {"gunner": 0, "sentinel": 1, "breach": 2, "launcher": 3}

WORKERS = 4


def chebyshev(a: Pos, b: Pos) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass
class BuilderTrace:
    eid: int
    team: int
    born: int
    death: int = -1
    max_own_core_dist: int = 0
    min_enemy_core_dist: int = 999
    was_self_destruct: bool = False
    was_launched: bool = False
    prev_pos: Pos = (0, 0)
    near_enemy_turns: int = 0


@dataclass
class TeamState:
    placed: Counter[str] = field(default_factory=Counter)
    alive: Counter[str] = field(default_factory=Counter)
    first_built: dict[str, int] = field(default_factory=dict)

    harvester_positions: list[Pos] = field(default_factory=list)
    turret_positions: list[Pos] = field(default_factory=list)
    harvester_turns: list[int] = field(default_factory=list)

    builder_spawn_turns: list[int] = field(default_factory=list)
    builders: dict[int, BuilderTrace] = field(default_factory=dict)
    builder_idle_turns: int = 0
    builder_presence_turns: int = 0
    self_destruct_turns: list[int] = field(default_factory=list)

    raid_arrivals: list[int] = field(default_factory=list)
    raid_per_turn: Counter[int] = field(default_factory=Counter)

    first_resource_turn: int | None = None
    first_delivery_turn: int | None = None


def extract_features(
    replay_path: str,
    team_a_name: str,
    team_b_name: str,
) -> dict[str, object] | None:
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

    own_core: dict[int, Pos] = {}
    enemy_core: dict[int, Pos] = {}
    for t in (0, 1):
        own_core[t] = meta.core_pos.get(t, (0, 0))
        enemy_core[t] = meta.core_pos.get(1 - t, (0, 0))

    core_tile_sets = {t: core_tiles(meta.core_pos, t) for t in (0, 1)}

    entities: dict[int, tuple[int, str]] = {}
    entity_pos: dict[int, Pos] = {}
    ts: dict[int, TeamState] = {0: TeamState(), 1: TeamState()}

    snapshot_counts: dict[int, dict[int, dict[str, int]]] = {}
    snapshot_turn_set = set(SNAPSHOT_TURNS)

    acted_this_turn: set[int] = set()
    damaged_this_turn: set[int] = set()

    for turn_idx, turn in enumerate(all_turns):
        acted_this_turn.clear()
        damaged_this_turn.clear()

        for u in turn.updates:
            kind = u.WhichOneof("kind")

            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                team = e.team
                pos: Pos = (e.position.x, e.position.y)
                entities[e.id] = (team, ek)
                entity_pos[e.id] = pos
                acted_this_turn.add(e.id)
                st = ts[team]
                st.placed[ek] += 1
                st.alive[ek] += 1

                if ek not in st.first_built:
                    st.first_built[ek] = turn_idx

                if ek == "harvester":
                    st.harvester_positions.append(pos)
                    st.harvester_turns.append(turn_idx)
                elif ek in TURRET_KINDS:
                    st.turret_positions.append(pos)
                elif ek == "builder_bot":
                    st.builder_spawn_turns.append(turn_idx)
                    bt = BuilderTrace(
                        eid=e.id,
                        team=team,
                        born=turn_idx,
                        prev_pos=pos,
                    )
                    bt.max_own_core_dist = chebyshev(pos, own_core[team])
                    bt.min_enemy_core_dist = chebyshev(pos, enemy_core[team])
                    st.builders[e.id] = bt

            elif kind == "move_builder_bot":
                mb = u.move_builder_bot
                new_pos: Pos = (mb.to.x, mb.to.y)
                old_pos = entity_pos.get(mb.id)
                entity_pos[mb.id] = new_pos
                acted_this_turn.add(mb.id)

                if mb.id in entities:
                    team = entities[mb.id][0]
                    st = ts[team]
                    bt = st.builders.get(mb.id)
                    if bt:
                        d_own = chebyshev(new_pos, own_core[team])
                        d_enemy = chebyshev(new_pos, enemy_core[team])
                        bt.max_own_core_dist = max(bt.max_own_core_dist, d_own)
                        bt.min_enemy_core_dist = min(bt.min_enemy_core_dist, d_enemy)

                        if d_enemy <= 4:
                            st.raid_arrivals.append(turn_idx)
                            st.raid_per_turn[turn_idx] += 1
                        if d_enemy <= 8:
                            bt.near_enemy_turns += 1

                        if old_pos:
                            manhattan = abs(new_pos[0] - old_pos[0]) + abs(
                                new_pos[1] - old_pos[1],
                            )
                            if manhattan > 3:
                                bt.was_launched = True
                        bt.prev_pos = new_pos

            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek = entities[eid]
                    st = ts[team]
                    st.alive[ek] = max(0, st.alive[ek] - 1)

                    if ek == "builder_bot":
                        acted_this_turn.add(eid)
                        bt = st.builders.get(eid)
                        if bt:
                            bt.death = turn_idx
                            if eid not in damaged_this_turn:
                                bt.was_self_destruct = True
                                st.self_destruct_turns.append(turn_idx)
                    entity_pos.pop(eid, None)

            elif kind == "update_hp":
                delta = u.update_hp.delta
                if delta < 0:
                    damaged_this_turn.add(u.update_hp.id)

            elif kind == "update_players":
                p = u.update_players.players
                for t, player in ((0, p.a), (1, p.b)):
                    if (
                        ts[t].first_resource_turn is None
                        and player.titanium_collected > 0
                    ):
                        ts[t].first_resource_turn = turn_idx

            elif kind == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    to: Pos = (mv.to.x, mv.to.y)
                    for t in (0, 1):
                        if (
                            to in core_tile_sets[t]
                            and ts[t].first_delivery_turn is None
                        ):
                            ts[t].first_delivery_turn = turn_idx

        for eid, (team, ek) in entities.items():
            if (
                ek == "builder_bot"
                and eid in ts[team].builders
                and ts[team].builders[eid].death == -1
            ):
                ts[team].builder_presence_turns += 1
                if eid not in acted_this_turn:
                    ts[team].builder_idle_turns += 1

        if turn_idx in snapshot_turn_set:
            snapshot_counts[turn_idx] = {}
            for t in (0, 1):
                snapshot_counts[turn_idx][t] = dict(ts[t].alive)

    # ── post-processing ──

    row: dict[str, object] = {}
    row["replay"] = Path(replay_path).stem
    row["winner"] = winner
    row["team_a"] = team_a_name
    row["team_b"] = team_b_name
    row["total_turns"] = total_turns

    # map context
    row["map_w"] = meta.width
    row["map_h"] = meta.height
    row["map_area"] = meta.width * meta.height
    row["map_passable_pct"] = round(meta.passable_count / (meta.width * meta.height), 4)
    ti_ore = sum(1 for _, _, t in meta.ore_tiles if t == "titanium")
    ax_ore = sum(1 for _, _, t in meta.ore_tiles if t == "axionite")
    row["map_ti_ore"] = ti_ore
    row["map_ax_ore"] = ax_ore
    row["core_dist_cheb"] = chebyshev(own_core[0], own_core[1])
    row["game_end_pct"] = round(total_turns / 2000, 4)

    for t in (0, 1):
        p = f"t{t}_"
        st = ts[t]

        # ── build order ──
        for etype in BUILDING_TYPES:
            row[p + f"first_{etype}"] = st.first_built.get(etype)
        row[p + "builds_before_first_harvester"] = _count_before(
            st.builder_spawn_turns,
            st.first_built.get("harvester"),
        )
        first_turret_turn = _first_turret_turn(st.first_built)
        row[p + "harvesters_before_first_turret"] = _harvester_count_before(
            st.harvester_turns,
            first_turret_turn,
        )
        row[p + "first_turret_type"] = _first_turret_type(st.first_built)
        row[p + "has_foundry"] = int("foundry" in st.first_built)

        # ── snapshots ──
        for snap_t in SNAPSHOT_TURNS:
            sp = f"{p}t{snap_t}_"
            if snap_t in snapshot_counts and t in snapshot_counts[snap_t]:
                counts = snapshot_counts[snap_t][t]
                row[sp + "builders"] = counts.get("builder_bot", 0)
                row[sp + "harvesters"] = counts.get("harvester", 0)
                row[sp + "turrets"] = sum(counts.get(tt, 0) for tt in TURRET_TYPES)
                row[sp + "conveyors"] = sum(counts.get(ct, 0) for ct in CONVEYOR_TYPES)
            else:
                row[sp + "builders"] = None
                row[sp + "harvesters"] = None
                row[sp + "turrets"] = None
                row[sp + "conveyors"] = None

        # ── builder allocation ──
        all_builders = list(st.builders.values())
        total_builders = len(all_builders)
        raiders = [b for b in all_builders if b.min_enemy_core_dist <= 4]
        defenders = [
            b
            for b in all_builders
            if b.max_own_core_dist <= 6 and b.min_enemy_core_dist > 4
        ]
        scouts = [b for b in all_builders if b not in raiders and b not in defenders]

        row[p + "raider_count"] = len(raiders)
        row[p + "defender_count"] = len(defenders)
        row[p + "scout_count"] = len(scouts)
        row[p + "raider_pct"] = (
            round(len(raiders) / total_builders, 4) if total_builders > 0 else 0.0
        )

        raider_born_turns = [b.born for b in raiders]
        row[p + "first_raider_turn"] = (
            min(raider_born_turns) if raider_born_turns else None
        )
        quarter = total_turns // 4
        row[p + "raider_commitment_early"] = sum(1 for b in raiders if b.born < quarter)

        raider_lifetimes = [
            (b.death if b.death >= 0 else total_turns) - b.born for b in raiders
        ]
        row[p + "avg_raider_lifetime"] = (
            round(statistics.mean(raider_lifetimes), 1) if raider_lifetimes else 0.0
        )

        max_dists = [b.max_own_core_dist for b in all_builders]
        row[p + "avg_builder_max_dist_from_own_core"] = (
            round(statistics.mean(max_dists), 2) if max_dists else 0.0
        )

        row[p + "builder_idle_pct"] = (
            round(st.builder_idle_turns / st.builder_presence_turns, 4)
            if st.builder_presence_turns > 0
            else 0.0
        )
        sd_count = len(st.self_destruct_turns)
        dead_builders = sum(1 for b in all_builders if b.death >= 0)
        row[p + "self_destruct_count"] = sd_count
        row[p + "self_destruct_pct"] = (
            round(sd_count / dead_builders, 4) if dead_builders > 0 else 0.0
        )
        row[p + "self_destruct_turn_first"] = (
            st.self_destruct_turns[0] if st.self_destruct_turns else None
        )
        row[p + "self_destruct_turn_median"] = (
            int(statistics.median(st.self_destruct_turns))
            if st.self_destruct_turns
            else None
        )
        row[p + "builders_spawned"] = total_builders
        row[p + "builder_spawn_rate_early"] = (
            round(sum(1 for t2 in st.builder_spawn_turns if t2 < 200) / 200, 4)
            if total_turns >= 200
            else 0.0
        )
        row[p + "builder_spawn_rate_late"] = (
            round(
                sum(1 for t2 in st.builder_spawn_turns if t2 >= 500)
                / max(1, total_turns - 500),
                4,
            )
            if total_turns > 500
            else 0.0
        )
        row[p + "builder_spawn_cadence_cv"] = _cadence_cv(st.builder_spawn_turns)

        # ── raid strategy ──
        row[p + "raid_start_turn"] = st.raid_arrivals[0] if st.raid_arrivals else None
        row[p + "raid_start_pct"] = (
            round(st.raid_arrivals[0] / total_turns, 4) if st.raid_arrivals else None
        )
        row[p + "raid_phases"] = _count_raid_phases(st.raid_arrivals)
        row[p + "raid_total_arrivals"] = len(st.raid_arrivals)
        row[p + "raid_peak_builders"] = (
            max(st.raid_per_turn.values()) if st.raid_per_turn else 0
        )
        raider_depths = [b.min_enemy_core_dist for b in raiders]
        row[p + "raid_depth_avg"] = (
            round(statistics.mean(raider_depths), 2) if raider_depths else None
        )
        raid_span = (
            st.raid_arrivals[-1] - st.raid_arrivals[0]
            if len(st.raid_arrivals) >= 2
            else 0
        )
        row[p + "raid_sustained"] = int(raid_span > 200)
        row[p + "raid_early"] = int(
            bool(st.raid_arrivals) and st.raid_arrivals[0] < 150,
        )
        row[p + "launched_raiders"] = sum(1 for b in raiders if b.was_launched)

        # ── economy layout ──
        row[p + "harvesters_placed"] = st.placed.get("harvester", 0)
        row[p + "harvester_timing_avg"] = (
            round(statistics.mean(st.harvester_turns), 1)
            if st.harvester_turns
            else None
        )
        harv_dists = [chebyshev(hp, own_core[t]) for hp in st.harvester_positions]
        row[p + "harvester_dist_from_core_avg"] = (
            round(statistics.mean(harv_dists), 2) if harv_dists else 0.0
        )
        row[p + "harvester_dist_from_core_max"] = max(harv_dists) if harv_dists else 0
        row[p + "harvester_spread"] = _pairwise_std(st.harvester_positions)
        row[p + "conveyors_placed"] = sum(st.placed.get(c, 0) for c in CONVEYOR_TYPES)
        harv_count = st.placed.get("harvester", 0)
        conv_count = sum(st.placed.get(c, 0) for c in CONVEYOR_TYPES)
        row[p + "conveyor_per_harvester"] = (
            round(conv_count / harv_count, 2) if harv_count > 0 else 0.0
        )
        row[p + "bridges_placed"] = st.placed.get("bridge", 0)
        row[p + "splitters_placed"] = st.placed.get("splitter", 0)
        row[p + "armoured_conveyors_placed"] = st.placed.get("armoured_conveyor", 0)
        row[p + "roads_placed"] = st.placed.get("road", 0)
        row[p + "barriers_placed"] = st.placed.get("barrier", 0)
        row[p + "scale_pressure"] = _scale_pressure(st.placed)
        row[p + "econ_start_turn"] = st.first_built.get("harvester")
        row[p + "econ_setup_duration"] = (
            st.first_delivery_turn - st.first_built.get("builder_bot", 0)
            if st.first_delivery_turn is not None and "builder_bot" in st.first_built
            else None
        )

        # ── turret/defense ──
        row[p + "turrets_placed"] = sum(st.placed.get(tt, 0) for tt in TURRET_TYPES)
        for tt in TURRET_TYPES:
            row[p + f"{tt}s_placed"] = st.placed.get(tt, 0)
        turret_types_used = sum(1 for tt in TURRET_TYPES if st.placed.get(tt, 0) > 0)
        row[p + "turret_diversity"] = turret_types_used
        row[p + "turret_start_turn"] = _first_turret_turn(st.first_built)
        turret_core_dists = [chebyshev(tp, own_core[t]) for tp in st.turret_positions]
        row[p + "turret_dist_from_core_avg"] = (
            round(statistics.mean(turret_core_dists), 2) if turret_core_dists else None
        )
        row[p + "turrets_near_core"] = sum(1 for d in turret_core_dists if d <= 4)
        turret_enemy_dists = [
            chebyshev(tp, enemy_core[t]) for tp in st.turret_positions
        ]
        row[p + "turrets_near_enemy"] = sum(1 for d in turret_enemy_dists if d <= 8)
        row[p + "turret_to_harvester_ratio"] = (
            round(sum(st.placed.get(tt, 0) for tt in TURRET_TYPES) / harv_count, 3)
            if harv_count > 0
            else 0.0
        )
        total_turrets = sum(st.placed.get(tt, 0) for tt in TURRET_TYPES)
        row[p + "launcher_pct"] = (
            round(st.placed.get("launcher", 0) / total_turrets, 4)
            if total_turrets > 0
            else 0.0
        )
        row[p + "has_breach"] = int(st.placed.get("breach", 0) > 0)

        # ── tempo ──
        row[p + "first_builder_turn"] = st.first_built.get("builder_bot")
        row[p + "first_resource_turn"] = st.first_resource_turn
        row[p + "first_delivery_turn"] = st.first_delivery_turn
        fb_turn = st.first_built.get("builder_bot", 0)
        row[p + "setup_speed"] = (
            st.first_delivery_turn - fb_turn
            if st.first_delivery_turn is not None
            else None
        )
        first_harv = st.first_built.get("harvester")
        first_raid_t = st.raid_arrivals[0] if st.raid_arrivals else None
        row[p + "aggression_before_econ"] = int(
            first_raid_t is not None
            and first_harv is not None
            and first_raid_t < first_harv,
        )
        second_harv_turn = (
            st.harvester_turns[1] if len(st.harvester_turns) >= 2 else None
        )
        row[p + "turret_before_second_harvester"] = int(
            first_turret_turn is not None
            and second_harv_turn is not None
            and first_turret_turn < second_harv_turn,
        )

    return row


def _count_before(spawn_turns: list[int], threshold: int | None) -> int:
    if threshold is None:
        return len(spawn_turns)
    return sum(1 for t in spawn_turns if t < threshold)


def _harvester_count_before(harvester_turns: list[int], threshold: int | None) -> int:
    if threshold is None:
        return len(harvester_turns)
    return sum(1 for t in harvester_turns if t < threshold)


def _first_turret_turn(first_built: dict[str, int]) -> int | None:
    turns = [first_built[k] for k in TURRET_TYPES if k in first_built]
    return min(turns) if turns else None


def _first_turret_type(first_built: dict[str, int]) -> int:
    best_turn = float("inf")
    best_type = 4
    for tt in TURRET_TYPES:
        t = first_built.get(tt)
        if t is not None and t < best_turn:
            best_turn = t
            best_type = TURRET_TYPE_MAP[tt]
    return best_type


def _cadence_cv(spawn_turns: list[int]) -> float:
    if len(spawn_turns) < 3:
        return 0.0
    intervals = [
        spawn_turns[i + 1] - spawn_turns[i] for i in range(len(spawn_turns) - 1)
    ]
    mean = statistics.mean(intervals)
    if mean == 0:
        return 0.0
    return round(statistics.stdev(intervals) / mean, 4)


def _count_raid_phases(arrivals: list[int]) -> int:
    if not arrivals:
        return 0
    phases = 1
    prev = arrivals[0]
    for a in arrivals[1:]:
        if a - prev > 50:
            phases += 1
        prev = a
    return phases


def _pairwise_std(positions: list[Pos]) -> float:
    if len(positions) < 2:
        return 0.0
    dists: list[float] = [
        chebyshev(positions[i], positions[j])
        for i in range(len(positions))
        for j in range(i + 1, len(positions))
    ]
    return round(statistics.stdev(dists), 2) if len(dists) >= 2 else 0.0


def _scale_pressure(placed: Counter[str]) -> float:
    scale = 100.0
    for kind, count in placed.items():
        pct = SCALE_PCT.get(kind, 0.0)
        scale += pct * count
    return round(scale, 1)


def process_one(
    args: tuple[str, str, str, str],
) -> tuple[str, dict[str, object] | None]:
    key, path, team_a, team_b = args
    return key, extract_features(path, team_a, team_b)


def main() -> None:
    if not INDEX_PATH.exists():
        print(f"No index at {INDEX_PATH}")
        sys.exit(1)

    index: dict[str, dict] = json.loads(INDEX_PATH.read_text())
    tasks: list[tuple[str, str, str, str]] = []
    for key, entry in index.items():
        mid = entry["matchId"]
        g = entry["game"]
        path = REPLAYS_DIR / f"{mid}_g{g}.replay26"
        if path.exists():
            tasks.append(
                (key, str(path), entry.get("teamA", ""), entry.get("teamB", "")),
            )

    print(f"Extracting features from {len(tasks)} replays ({WORKERS} workers)...")
    t0 = time.time()

    rows: list[dict[str, object]] = []
    done = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_one, t): t for t in tasks}
        for future in as_completed(futures):
            key, row_result = future.result()
            if row_result is not None:
                rows.append(row_result)
                done += 1
            else:
                failed += 1
            total = done + failed
            if total % 50 == 0:
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
