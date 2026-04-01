"""Replay loss analysis tool.

Parses .replay26 files and classifies losses with turning point detection.
Uses the existing replay_common infrastructure.

Usage:
    python tools/analyze.py replay /tmp/match.replay26
    python tools/analyze.py replay /tmp/match.replay26 --team B
    python tools/analyze.py replay /tmp/match.replay26 --detail
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from replay_common import (
    TEAM_A,
    initial_entities,
    load_replay,
    other_team,
    pos_tuple,
    team_label,
)


def dist_sq(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


INFRA_KINDS = {"conveyor", "bridge", "splitter", "armoured_conveyor"}
TURRET_KINDS = {"sentinel", "gunner", "breach", "launcher"}


def analyze_replay(path: str | Path, our_team: int) -> dict[str, Any]:
    """Full analysis of a single replay from our_team's perspective."""
    replay = load_replay(path)
    enemy_team = other_team(our_team)

    # Find core positions.
    our_core_pos: tuple[int, int] | None = None
    enemy_core_pos: tuple[int, int] | None = None
    our_core_id: int | None = None
    enemy_core_id: int | None = None
    for core in replay.map.cores:
        if core.team == our_team:
            our_core_pos = pos_tuple(core.position)
            our_core_id = core.id
        else:
            enemy_core_pos = pos_tuple(core.position)
            enemy_core_id = core.id

    entities = initial_entities(replay)
    total_turns = len(replay.turns)

    # Per-turn tracking.
    our_ti_collected: list[int] = []
    enemy_ti_collected: list[int] = []
    our_core_hp: list[int | None] = []
    enemy_core_hp: list[int | None] = []

    # Event counters.
    our_buildings_destroyed: list[int] = []  # per turn
    enemy_buildings_destroyed: list[int] = []
    our_harvesters_built = 0
    our_harvesters_destroyed = 0
    our_sentinels_built = 0
    our_sentinels_destroyed = 0
    enemy_harvesters_built = 0
    our_infra_destroyed_near_core: list[tuple[int, int, str]] = []  # (turn, id, kind)
    tle_turns: list[int] = []
    turret_shots_at_our_core: list[tuple[int, tuple[int, int]]] = []  # (turn, from_pos)

    # Track enemy turrets and their positions relative to our harvesters.
    # (turn, enemy_turret_kind, turret_pos, adjacent_harvester_pos_or_None)
    enemy_turret_placements: list[tuple[int, str, tuple[int, int], tuple[int, int] | None]] = []
    # Track our harvester positions (live).
    our_harvester_positions: dict[int, tuple[int, int]] = {}
    # Track all enemy building removals near our core for detail mode.
    our_buildings_destroyed_detail: list[tuple[int, str, tuple[int, int]]] = []  # (turn, kind, pos)
    # Track positions where our transport was destroyed — for interception detection.
    # pos -> (turn_destroyed, kind)
    our_transport_destroyed_at: dict[tuple[int, int], tuple[int, str]] = {}
    # Detected interceptions: enemy building placed where our transport was.
    interceptions: list[tuple[int, str, tuple[int, int], int, str]] = []  # (turn, enemy_kind, pos, destroyed_turn, our_kind)

    # Enemy bots near our core per turn.
    enemy_bots_near_core: list[int] = []

    for turn_no, turn in enumerate(replay.turns, start=1):
        our_destroyed = 0
        enemy_destroyed = 0

        for update in turn.updates:
            kind = update.WhichOneof("kind")

            if kind == "place_entity":
                entity = update.place_entity.entity
                ek = entity.WhichOneof("kind") or "unknown"
                entities[entity.id] = {
                    "id": entity.id,
                    "team": entity.team,
                    "kind": ek,
                    "pos": pos_tuple(entity.position),
                    "hp": entity.hp,
                    "max_hp": entity.max_hp,
                }
                if entity.team == our_team:
                    if ek == "harvester":
                        our_harvesters_built += 1
                        our_harvester_positions[entity.id] = pos_tuple(entity.position)
                    elif ek == "sentinel":
                        our_sentinels_built += 1
                elif entity.team == enemy_team:
                    if ek == "harvester":
                        enemy_harvesters_built += 1
                    epos = pos_tuple(entity.position)
                    if ek in TURRET_KINDS:
                        adj_harv = None
                        for hid, hpos in our_harvester_positions.items():
                            if max(abs(epos[0] - hpos[0]), abs(epos[1] - hpos[1])) <= 1:
                                adj_harv = hpos
                                break
                        enemy_turret_placements.append((turn_no, ek, epos, adj_harv))
                    # Check if enemy placed anything where our transport was.
                    if epos in our_transport_destroyed_at:
                        d_turn, our_kind = our_transport_destroyed_at[epos]
                        if turn_no - d_turn <= 20:
                            interceptions.append((turn_no, ek, epos, d_turn, our_kind))

            elif kind == "remove_entity":
                eid = update.remove_entity.id
                state = entities.pop(eid, None)
                if state is not None:
                    if state["team"] == our_team:
                        our_destroyed += 1
                        our_buildings_destroyed_detail.append(
                            (turn_no, state["kind"], state["pos"])
                        )
                        if state["kind"] == "harvester":
                            our_harvesters_destroyed += 1
                            our_harvester_positions.pop(eid, None)
                        elif state["kind"] == "sentinel":
                            our_sentinels_destroyed += 1
                        if state["kind"] in INFRA_KINDS:
                            our_transport_destroyed_at[state["pos"]] = (turn_no, state["kind"])
                            if our_core_pos is not None and dist_sq(state["pos"], our_core_pos) <= 100:
                                our_infra_destroyed_near_core.append(
                                    (turn_no, eid, state["kind"])
                                )
                    elif state["team"] == enemy_team:
                        enemy_destroyed += 1

            elif kind == "move_builder_bot":
                state = entities.get(update.move_builder_bot.id)
                if state is not None:
                    state["pos"] = pos_tuple(update.move_builder_bot.to)

            elif kind == "update_hp":
                state = entities.get(update.update_hp.id)
                if state is not None and state.get("hp") is not None:
                    state["hp"] += update.update_hp.delta

            elif kind == "update_players":
                p = update.update_players.players
                our_p = p.a if our_team == TEAM_A else p.b
                enemy_p = p.b if our_team == TEAM_A else p.a
                our_ti_collected.append(our_p.titanium_collected)
                enemy_ti_collected.append(enemy_p.titanium_collected)

            elif kind == "fire_turret":
                ft = update.fire_turret
                target = pos_tuple(ft.to)
                # Check if firing at our core tiles.
                if our_core_pos is not None and dist_sq(target, our_core_pos) <= 2:
                    turret_shots_at_our_core.append((turn_no, pos_tuple(getattr(ft, "from"))))

            elif kind == "bot_output":
                if update.bot_output.tled:
                    state = entities.get(update.bot_output.id)
                    if state is not None and state["team"] == our_team:
                        tle_turns.append(turn_no)

        our_buildings_destroyed.append(our_destroyed)
        enemy_buildings_destroyed.append(enemy_destroyed)

        # Core HP.
        our_core_state = entities.get(our_core_id)
        enemy_core_state = entities.get(enemy_core_id)
        our_core_hp.append(our_core_state["hp"] if our_core_state else None)
        enemy_core_hp.append(enemy_core_state["hp"] if enemy_core_state else None)

        # Enemy bots near our core.
        near_count = 0
        if our_core_pos is not None:
            for e in entities.values():
                if e["team"] == enemy_team and e["kind"] == "builder_bot":
                    if dist_sq(e["pos"], our_core_pos) <= 50:
                        near_count += 1
        enemy_bots_near_core.append(near_count)

    # --- Classification ---
    winner = replay.winner if replay.HasField("winner") else None
    we_won = winner == our_team
    we_lost = winner == enemy_team

    # Final resources.
    our_ti_final = our_ti_collected[-1] if our_ti_collected else 0
    enemy_ti_final = enemy_ti_collected[-1] if enemy_ti_collected else 0

    # Core destroyed?
    our_core_destroyed = our_core_hp[-1] is None or (our_core_hp[-1] is not None and our_core_hp[-1] <= 0)
    enemy_core_destroyed = enemy_core_hp[-1] is None or (enemy_core_hp[-1] is not None and enemy_core_hp[-1] <= 0)

    categories: list[str] = []
    details: list[str] = []

    if we_lost and our_core_destroyed:
        categories.append("CORE_SNIPED")
        # Find when core started taking damage.
        first_core_dmg = None
        for i, hp in enumerate(our_core_hp):
            if hp is not None and hp < 500:
                first_core_dmg = i + 1
                break
        details.append(f"Core first damaged: turn {first_core_dmg or '?'}")
        if turret_shots_at_our_core:
            first_shot = turret_shots_at_our_core[0]
            details.append(f"First turret shot at core: turn {first_shot[0]} from {first_shot[1]}")
            # Count unique turret positions.
            turret_positions = set(s[1] for s in turret_shots_at_our_core)
            details.append(f"Turrets firing at core: {len(turret_positions)} from {turret_positions}")

    if we_lost and not our_core_destroyed:
        categories.append("OUTMINED")
        ti_ratio = enemy_ti_final / max(1, our_ti_final)
        details.append(f"Ti mined: us={our_ti_final} them={enemy_ti_final} (ratio={ti_ratio:.2f})")
        # Find turning point.
        turning_point = None
        for i in range(len(our_ti_collected)):
            if enemy_ti_collected[i] > our_ti_collected[i]:
                turning_point = i + 1
                break
        if turning_point:
            details.append(f"They overtook us on Ti at turn {turning_point}")

    # Infrastructure collapse near core.
    if our_infra_destroyed_near_core:
        # Check for bursts.
        burst_window = 100
        max_burst = 0
        max_burst_start = 0
        for start in range(0, total_turns, 50):
            count = sum(1 for t, _, _ in our_infra_destroyed_near_core if start <= t < start + burst_window)
            if count > max_burst:
                max_burst = count
                max_burst_start = start
        if max_burst >= 3:
            categories.append("INFRA_COLLAPSE")
            details.append(f"Infrastructure burst: {max_burst} buildings destroyed near core in turns {max_burst_start}-{max_burst_start + burst_window}")

    # TLE.
    if tle_turns:
        categories.append("TLE")
        details.append(f"TLE on {len(tle_turns)} turns, first at turn {tle_turns[0]}")

    # Aggro ineffective.
    if our_sentinels_built <= 1 and enemy_harvesters_built >= 3:
        categories.append("AGGRO_INEFFECTIVE")
        details.append(f"Sentinels built: {our_sentinels_built}, enemy harvesters: {enemy_harvesters_built}")

    # Late stall.
    if len(our_ti_collected) > 500:
        mid_lead = our_ti_collected[499] > enemy_ti_collected[499]
        final_loss = our_ti_final < enemy_ti_final
        if mid_lead and final_loss:
            categories.append("LATE_STALL")
            details.append(f"Led at turn 500 ({our_ti_collected[499]} vs {enemy_ti_collected[499]}) but lost ({our_ti_final} vs {enemy_ti_final})")

    # Intercepted — enemy destroyed our transport and placed their building on it.
    if interceptions:
        categories.append("INTERCEPTED")
        details.append(f"Supply lines intercepted: {len(interceptions)}")
        for turn, ek, pos, d_turn, our_kind in interceptions:
            details.append(f"  t={turn} enemy {ek} at {pos} (our {our_kind} destroyed t={d_turn})")

    # Parasited — enemy placed turrets adjacent to our harvesters.
    parasited = [e for e in enemy_turret_placements if e[3] is not None]
    if parasited:
        categories.append("PARASITED")
        details.append(f"Enemy turrets on our harvesters: {len(parasited)}")
        for turn, ek, tpos, hpos in parasited:
            details.append(f"  t={turn} enemy {ek} at {tpos} adj to our harvester at {hpos}")

    # All enemy turret placements.
    if enemy_turret_placements:
        non_parasited = [e for e in enemy_turret_placements if e[3] is None]
        if non_parasited:
            details.append(f"Other enemy turrets: {len(non_parasited)}")
            for turn, ek, tpos, _ in non_parasited:
                details.append(f"  t={turn} enemy {ek} at {tpos}")

    # Enemy bot pressure.
    peak_bots = max(enemy_bots_near_core) if enemy_bots_near_core else 0
    if peak_bots >= 2:
        peak_turn = enemy_bots_near_core.index(peak_bots) + 1
        details.append(f"Enemy bots near core: peaked at {peak_bots} (turn {peak_turn})")

    # Ti income rate at key points.
    def income_at(turn: int) -> tuple[int, int]:
        if turn >= len(our_ti_collected) or turn < 50:
            return (0, 0)
        return (
            our_ti_collected[turn] - our_ti_collected[turn - 50],
            enemy_ti_collected[turn] - enemy_ti_collected[turn - 50],
        )

    income_details = []
    for t in [200, 500, 1000, 1500]:
        if t < len(our_ti_collected):
            ours, theirs = income_at(t)
            income_details.append(f"t{t}: us={ours}/50t them={theirs}/50t")
    if income_details:
        details.append("Income rate: " + ", ".join(income_details))

    return {
        "path": str(path),
        "turns": total_turns,
        "our_team": team_label(our_team),
        "result": "WIN" if we_won else "LOSS" if we_lost else "DRAW",
        "win_condition": "core_destroyed" if (our_core_destroyed or enemy_core_destroyed) else "resources",
        "categories": categories or ["UNKNOWN"],
        "our_ti_mined": our_ti_final,
        "enemy_ti_mined": enemy_ti_final,
        "our_harvesters": f"{our_harvesters_built} built, {our_harvesters_destroyed} destroyed",
        "our_sentinels": f"{our_sentinels_built} built, {our_sentinels_destroyed} destroyed",
        "our_core_final_hp": our_core_hp[-1] if our_core_hp else None,
        "enemy_core_final_hp": enemy_core_hp[-1] if enemy_core_hp else None,
        "tle_count": len(tle_turns),
        "interceptions": [
            {"turn": t, "enemy_kind": k, "pos": p, "destroyed_turn": dt, "our_kind": ok}
            for t, k, p, dt, ok in interceptions
        ],
        "enemy_turret_placements": [
            {"turn": t, "kind": k, "pos": p, "adj_harvester": h}
            for t, k, p, h in enemy_turret_placements
        ],
        "our_buildings_destroyed_detail": [
            {"turn": t, "kind": k, "pos": p}
            for t, k, p in our_buildings_destroyed_detail
        ],
        "details": details,
    }


def print_analysis(analysis: dict[str, Any]) -> None:
    r = analysis
    result_str = r["result"]
    cats = ", ".join(r["categories"])
    print(f"{'='*60}")
    print(f"{r['path']}")
    print(f"  Result: {result_str} ({r['win_condition']}, turn {r['turns']})")
    print(f"  Team: {r['our_team']}")
    if r["result"] == "LOSS":
        print(f"  Categories: {cats}")
    print(f"  Ti mined: us={r['our_ti_mined']} them={r['enemy_ti_mined']}")
    print(f"  Harvesters: {r['our_harvesters']}")
    print(f"  Sentinels: {r['our_sentinels']}")
    print(f"  Core HP: ours={r['our_core_final_hp']} theirs={r['enemy_core_final_hp']}")
    if r["tle_count"]:
        print(f"  TLEs: {r['tle_count']}")
    for d in r["details"]:
        print(f"  > {d}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze replay files for loss patterns.")
    sub = parser.add_subparsers(dest="command")

    rp = sub.add_parser("replay", help="Analyze a local replay file")
    rp.add_argument("path", help="Path to .replay26 file")
    rp.add_argument("--team", default="A", help="Our team (A or B)")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "replay":
        from replay_common import team_from_side
        our_team = team_from_side(args.team)
        analysis = analyze_replay(args.path, our_team)
        print_analysis(analysis)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
