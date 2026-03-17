import math

from .snapshot import ATTACK_SQ, CONVEYOR_KINDS, TURRET_KINDS, GameState


def _in_range(pos: tuple[int, int], target: tuple[int, int], rsq: int) -> bool:
    dx = pos[0] - target[0]
    dy = pos[1] - target[1]
    return dx * dx + dy * dy <= rsq


def turret_coverage_map(state: GameState, team: int) -> dict[tuple[int, int], list[tuple[int, int]]]:
    coverage: dict[tuple[int, int], list[tuple[int, int]]] = {}
    turrets = [e for e in state.team_entities(team) if e.kind in TURRET_KINDS]

    infra = [e for e in state.team_entities(team)
             if e.kind in CONVEYOR_KINDS | {"harvester", "foundry"}]

    for t in turrets:
        rsq = ATTACK_SQ.get(t.kind, 0)
        for i in infra:
            if _in_range(t.pos, i.pos, rsq):
                coverage.setdefault(i.pos, []).append(t.pos)

    return coverage


def defense_analysis(state: GameState, team: int) -> dict:
    turrets = [e for e in state.team_entities(team) if e.kind in TURRET_KINDS]
    harvesters = state.team_entities(team, "harvester")
    conveyors = [e for e in state.team_entities(team) if e.kind in CONVEYOR_KINDS]

    coverage = turret_coverage_map(state, team)

    defended_harv = sum(1 for h in harvesters if h.pos in coverage)
    defended_conv = sum(1 for c in conveyors if c.pos in coverage)
    total_harv = len(harvesters)
    total_conv = len(conveyors)

    enemy = 1 - team
    enemy_turrets = [e for e in state.team_entities(enemy) if e.kind in TURRET_KINDS]
    exposed_harv = 0
    exposed_conv = 0
    for et in enemy_turrets:
        rsq = ATTACK_SQ.get(et.kind, 0)
        for h in harvesters:
            if _in_range(et.pos, h.pos, rsq):
                exposed_harv += 1
                break
        for c in conveyors:
            if _in_range(et.pos, c.pos, rsq):
                exposed_conv += 1

    core_pos = state.core_pos.get(team)
    core_defended = False
    if core_pos:
        core_defended = any(
            _in_range(t.pos, core_pos, ATTACK_SQ.get(t.kind, 0))
            for t in turrets
        )

    undefended_harvesters = [h.pos for h in harvesters if h.pos not in coverage]

    return {
        "turret_count": len(turrets),
        "turret_types": {k: sum(1 for t in turrets if t.kind == k) for k in TURRET_KINDS if any(t.kind == k for t in turrets)},
        "harvesters_defended": defended_harv,
        "harvesters_total": total_harv,
        "harvester_defense_pct": 100 * defended_harv / total_harv if total_harv > 0 else 0,
        "conveyors_defended": defended_conv,
        "conveyors_total": total_conv,
        "conveyor_defense_pct": 100 * defended_conv / total_conv if total_conv > 0 else 0,
        "core_defended": core_defended,
        "harvesters_exposed_to_enemy": exposed_harv,
        "conveyors_exposed_to_enemy": exposed_conv,
        "undefended_harvesters": undefended_harvesters,
    }
