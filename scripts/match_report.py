"""Comprehensive per-bucket time-series match report.

Extracts macro (economy, production) and micro (combat, defense) metrics
from a replay, bucketed over time, and prints a structured comparison table.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from scripts.analysis.constants import CONVEYOR_KINDS, SCALE_PCT, TEAM_LABEL, Pos
from scripts.analysis.snapshot import core_tiles, entity_kind
from scripts.replay import load_replay

if TYPE_CHECKING:
    from proto.cambc_pb2 import Replay


@dataclass
class TeamBucket:
    builders_spawned: int = 0
    builders_alive: int = 0
    harvesters: int = 0
    transport: int = 0
    sentinels: int = 0
    gunners: int = 0
    launchers: int = 0
    barriers: int = 0
    buildings: int = 0
    roads: int = 0
    scale: float = 0.0
    titanium: int = 0
    axionite: int = 0
    ti_collected: int = 0
    ax_collected: int = 0
    core_deliveries: int = 0
    turret_fires: int = 0
    damage_dealt: int = 0
    damage_taken: int = 0
    entities_lost: int = 0
    builder_deaths: int = 0
    healing: int = 0


@dataclass
class Diagnostics:
    game_length: int = 0
    winner: str = "?"
    win_condition: str = ""
    first_harvester: dict[int, int | None] = field(
        default_factory=lambda: {0: None, 1: None}
    )
    first_transport: dict[int, int | None] = field(
        default_factory=lambda: {0: None, 1: None}
    )
    first_sentinel: dict[int, int | None] = field(
        default_factory=lambda: {0: None, 1: None}
    )
    first_turret_fire: dict[int, int | None] = field(
        default_factory=lambda: {0: None, 1: None}
    )
    first_delivery: dict[int, int | None] = field(
        default_factory=lambda: {0: None, 1: None}
    )
    last_builder_spawn: dict[int, int | None] = field(
        default_factory=lambda: {0: None, 1: None}
    )
    total_turret_fires: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    total_damage: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    total_healing: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    tle_count: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})


def scan(replay: Replay) -> tuple[list[int], dict[int, list[TeamBucket]], Diagnostics]:
    all_turns = replay.turns
    total = len(all_turns)
    bucket_size = max(25, total // 8)

    m = replay.map
    core_pos: dict[int, Pos] = {}
    for c in m.cores:
        core_pos[c.team] = (c.position.x, c.position.y)
    core_tile_sets = {t: core_tiles(core_pos, t) for t in (0, 1)}

    entities: dict[int, tuple[int, str, int]] = {}
    building_at: dict[Pos, int] = {}
    final_hp: dict[int, int] = {}

    cum: dict[int, defaultdict[str, int]] = {t: defaultdict(int) for t in (0, 1)}
    cum_scale: dict[int, float] = {0: 0.0, 1: 0.0}
    alive_builders: dict[int, int] = {0: 0, 1: 0}
    latest_ti: dict[int, int] = {0: 500, 1: 500}
    latest_ax: dict[int, int] = {0: 0, 1: 0}
    latest_ti_collected: dict[int, int] = {0: 0, 1: 0}
    latest_ax_collected: dict[int, int] = {0: 0, 1: 0}

    diag = Diagnostics(game_length=total)
    winner_raw = replay.winner if replay.HasField("winner") else None
    if winner_raw is None:
        msg = "Replay has no winner field — file may be empty or corrupt"
        raise ValueError(msg)
    diag.winner = TEAM_LABEL[winner_raw]

    boundaries: list[int] = []
    buckets: dict[int, list[TeamBucket]] = {0: [], 1: []}
    damaged_this_turn: set[int] = set()

    for turn_idx, turn in enumerate(all_turns):
        damaged_this_turn.clear()

        for u in turn.updates:
            kind = u.WhichOneof("kind")

            if kind == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                team = e.team
                pos: Pos = (e.position.x, e.position.y)
                entities[e.id] = (team, ek, e.max_hp)
                final_hp[e.id] = e.hp
                if ek not in ("builder_bot", "marker"):
                    building_at[pos] = e.id

                c = cum[team]
                if ek == "builder_bot":
                    c["builders_spawned"] += 1
                    alive_builders[team] += 1
                    diag.last_builder_spawn[team] = turn_idx
                elif ek == "harvester":
                    c["harvesters"] += 1
                    if diag.first_harvester[team] is None:
                        diag.first_harvester[team] = turn_idx
                elif ek in CONVEYOR_KINDS:
                    c["transport"] += 1
                    if diag.first_transport[team] is None:
                        diag.first_transport[team] = turn_idx
                elif ek == "sentinel":
                    c["sentinels"] += 1
                    if diag.first_sentinel[team] is None:
                        diag.first_sentinel[team] = turn_idx
                elif ek == "gunner":
                    c["gunners"] += 1
                elif ek == "launcher":
                    c["launchers"] += 1
                elif ek == "barrier":
                    c["barriers"] += 1
                elif ek == "road":
                    c["roads"] += 1

                if ek not in ("marker", "builder_bot"):
                    c["buildings"] += 1
                    cum_scale[team] += SCALE_PCT.get(ek, 0.0)

            elif kind == "remove_entity":
                eid = u.remove_entity.id
                if eid in entities:
                    team, ek, _ = entities[eid]
                    cum[team]["entities_lost"] += 1
                    if ek == "builder_bot":
                        alive_builders[team] -= 1
                        cum[team]["builder_deaths"] += 1
                    epos = None
                    for p, bid in building_at.items():
                        if bid == eid:
                            epos = p
                            break
                    if epos is not None:
                        del building_at[epos]
                    final_hp.pop(eid, None)

            elif kind == "update_hp":
                eid = u.update_hp.id
                delta = u.update_hp.delta
                if eid in final_hp:
                    final_hp[eid] += delta
                if eid in entities:
                    team, _, _ = entities[eid]
                    if delta < 0:
                        damaged_this_turn.add(eid)
                        attacker = 1 - team
                        cum[attacker]["damage_dealt"] += abs(delta)
                        cum[team]["damage_taken"] += abs(delta)
                    elif delta > 0:
                        cum[team]["healing"] += delta

            elif kind == "fire_turret":
                f = u.fire_turret
                f_from = getattr(f, "from")
                fpos: Pos = (f_from.x, f_from.y)
                fid = building_at.get(fpos)
                if fid and fid in entities:
                    team = entities[fid][0]
                    cum[team]["turret_fires"] += 1
                    if diag.first_turret_fire[team] is None:
                        diag.first_turret_fire[team] = turn_idx

            elif kind == "update_players":
                p = u.update_players.players
                for t, player in ((0, p.a), (1, p.b)):
                    latest_ti[t] = player.titanium
                    latest_ax[t] = player.axionite
                    latest_ti_collected[t] = player.titanium_collected
                    latest_ax_collected[t] = player.axionite_collected

            elif kind == "distribute_resources":
                for mv in u.distribute_resources.moves:
                    to: Pos = (mv.to.x, mv.to.y)
                    for t in (0, 1):
                        if to in core_tile_sets[t]:
                            cum[t]["core_deliveries"] += 1
                            if diag.first_delivery[t] is None:
                                diag.first_delivery[t] = turn_idx

            elif kind == "bot_output":
                bo = u.bot_output
                if bo.tled and bo.id in entities:
                    team = entities[bo.id][0]
                    diag.tle_count[team] += 1

        if (turn_idx + 1) % bucket_size == 0 or turn_idx == total - 1:
            boundaries.append(turn_idx)
            for t in (0, 1):
                c = cum[t]
                buckets[t].append(
                    TeamBucket(
                        builders_spawned=c["builders_spawned"],
                        builders_alive=alive_builders[t],
                        harvesters=c["harvesters"],
                        transport=c["transport"],
                        sentinels=c["sentinels"],
                        gunners=c["gunners"],
                        launchers=c["launchers"],
                        barriers=c["barriers"],
                        buildings=c["buildings"],
                        roads=c["roads"],
                        scale=cum_scale[t],
                        titanium=latest_ti[t],
                        axionite=latest_ax[t],
                        ti_collected=latest_ti_collected[t],
                        ax_collected=latest_ax_collected[t],
                        core_deliveries=c["core_deliveries"],
                        turret_fires=c["turret_fires"],
                        damage_dealt=c["damage_dealt"],
                        damage_taken=c["damage_taken"],
                        entities_lost=c["entities_lost"],
                        builder_deaths=c["builder_deaths"],
                        healing=c["healing"],
                    )
                )

    for t in (0, 1):
        diag.total_turret_fires[t] = cum[t]["turret_fires"]
        diag.total_damage[t] = cum[t]["damage_dealt"]
        diag.total_healing[t] = cum[t]["healing"]

    return boundaries, buckets, diag


def _fmt(v: float, w: int = 5) -> str:
    if isinstance(v, float):
        return f"{v:{w}.0f}"
    return f"{v:{w}d}"


def _diag_val(v: int | None) -> str:
    return f"R{v}" if v is not None else "-"


def print_report(
    boundaries: list[int],
    buckets: dict[int, list[TeamBucket]],
    diag: Diagnostics,
    name_a: str,
    name_b: str,
) -> None:
    bucket_size = boundaries[0] + 1 if boundaries else 1
    print(
        f"Rounds: {diag.game_length}  Bucket: {bucket_size}  "
        f"Winner: {diag.winner}  {diag.win_condition}"
    )
    print()

    _print_economy(boundaries, buckets, name_a, name_b)
    print()
    _print_combat(boundaries, buckets, name_a, name_b)
    print()
    _print_diagnostics(diag, name_a, name_b)


def _range_label(i: int, boundaries: list[int]) -> str:
    start = 0 if i == 0 else boundaries[i - 1] + 1
    end = boundaries[i]
    return f"{start:>4d}-{end:<4d}"


def _print_economy(
    boundaries: list[int],
    buckets: dict[int, list[TeamBucket]],
    name_a: str,
    name_b: str,
) -> None:
    hdr = "  Bld BAlv Harv Trns Sent  Gun  Barr Road   Ti TiCol CDel"
    print(f"{'Rounds':>10s} |{name_a:^{len(hdr)}s}|{name_b:^{len(hdr)}s}|")
    print(f"{'':>10s} |{hdr}|{hdr}|")
    sep = "-" * (11 + 2 * (len(hdr) + 1) + 1)
    print(sep)

    for i, _ in enumerate(boundaries):
        label = _range_label(i, boundaries)
        parts: list[str] = []
        for t in (0, 1):
            b = buckets[t][i]
            parts.append(
                f"{_fmt(b.builders_spawned)}"
                f"{_fmt(b.builders_alive)}"
                f"{_fmt(b.harvesters)}"
                f"{_fmt(b.transport)}"
                f"{_fmt(b.sentinels)}"
                f"{_fmt(b.gunners)}"
                f"{_fmt(b.barriers)}"
                f"{_fmt(b.roads)}"
                f"{_fmt(b.titanium)}"
                f"{_fmt(b.ti_collected)}"
                f"{_fmt(b.core_deliveries)}"
            )
        print(f"{label} |{parts[0]}|{parts[1]}|")


def _print_combat(
    boundaries: list[int],
    buckets: dict[int, list[TeamBucket]],
    name_a: str,
    name_b: str,
) -> None:
    hdr = " Fires DmgDl DmgTk  Lost BDeth  Heal Scl%"
    print(f"{'Rounds':>10s} |{name_a:^{len(hdr)}s}|{name_b:^{len(hdr)}s}|")
    print(f"{'':>10s} |{hdr}|{hdr}|")
    sep = "-" * (11 + 2 * (len(hdr) + 1) + 1)
    print(sep)

    for i, _ in enumerate(boundaries):
        label = _range_label(i, boundaries)
        parts: list[str] = []
        for t in (0, 1):
            b = buckets[t][i]
            parts.append(
                f"{_fmt(b.turret_fires)}"
                f"{_fmt(b.damage_dealt)}"
                f"{_fmt(b.damage_taken)}"
                f"{_fmt(b.entities_lost)}"
                f"{_fmt(b.builder_deaths)}"
                f"{_fmt(b.healing)}"
                f"{_fmt(b.scale, 5)}"
            )
        print(f"{label} |{parts[0]}|{parts[1]}|")


def _print_diagnostics(diag: Diagnostics, name_a: str, name_b: str) -> None:
    w = max(len(name_a), len(name_b), 8)
    print(f"{'':>24s} {name_a:>{w}s}  {name_b:>{w}s}")
    rows = [
        ("First harvester", diag.first_harvester),
        ("First transport", diag.first_transport),
        ("First sentinel", diag.first_sentinel),
        ("First turret fire", diag.first_turret_fire),
        ("First core delivery", diag.first_delivery),
        ("Last builder spawn", diag.last_builder_spawn),
        ("Total turret fires", diag.total_turret_fires),
        ("Total damage dealt", diag.total_damage),
        ("Total healing", diag.total_healing),
        ("TLEs", diag.tle_count),
    ]
    for label, vals in rows:
        is_round = label.startswith(("First", "Last"))
        a = _diag_val(vals[0]) if is_round else str(vals[0])
        b = _diag_val(vals[1]) if is_round else str(vals[1])
        print(f"{label:>24s} {a:>{w}s}  {b:>{w}s}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Match report")
    parser.add_argument("replay", help="Path to replay file")
    parser.add_argument("--a", default="Team A", help="Team A name")
    parser.add_argument("--b", default="Team B", help="Team B name")
    args = parser.parse_args()

    replay = load_replay(args.replay)
    boundaries, buckets, diag = scan(replay)
    print_report(boundaries, buckets, diag, args.a, args.b)


if __name__ == "__main__":
    main()
