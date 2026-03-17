from __future__ import annotations

from dataclasses import dataclass

from ..constants import ATTACK_SQ, CONVEYOR_KINDS, TEAM_LABEL, TURRET_KINDS, Pos
from ..snapshot import team_entities
from ..types import Context, GameState
from . import register


def _in_range(pos: Pos, target: Pos, rsq: int) -> bool:
    dx = pos[0] - target[0]
    dy = pos[1] - target[1]
    return dx * dx + dy * dy <= rsq


@dataclass
class DefenseReport:
    turret_count: dict[int, int]
    turret_types: dict[int, dict[str, int]]
    core_defended: dict[int, bool]
    harvesters_defended: dict[int, int]
    harvesters_total: dict[int, int]
    harvester_defense_pct: dict[int, float]
    conveyors_defended: dict[int, int]
    conveyors_total: dict[int, int]
    conveyor_defense_pct: dict[int, float]
    undefended_harvester_positions: dict[int, list[Pos]]
    harvesters_exposed_to_enemy: dict[int, int]
    conveyors_exposed_to_enemy: dict[int, int]


def _analyze_team(state: GameState, team: int) -> dict[str, object]:
    turrets = [e for e in team_entities(state, team) if e.kind in TURRET_KINDS]
    harvesters = team_entities(state, team, "harvester")
    conveyors = [e for e in team_entities(state, team) if e.kind in CONVEYOR_KINDS]

    defended_h: set[Pos] = set()
    defended_c: set[Pos] = set()
    for t in turrets:
        rsq = ATTACK_SQ.get(t.kind, 0)
        for h in harvesters:
            if _in_range(t.pos, h.pos, rsq):
                defended_h.add(h.pos)
        for c in conveyors:
            if _in_range(t.pos, c.pos, rsq):
                defended_c.add(c.pos)

    enemy = 1 - team
    enemy_turrets = [e for e in team_entities(state, enemy) if e.kind in TURRET_KINDS]
    exposed_h = sum(
        1
        for h in harvesters
        if any(
            _in_range(et.pos, h.pos, ATTACK_SQ.get(et.kind, 0)) for et in enemy_turrets
        )
    )
    exposed_c = sum(
        1
        for c in conveyors
        if any(
            _in_range(et.pos, c.pos, ATTACK_SQ.get(et.kind, 0)) for et in enemy_turrets
        )
    )

    core_pos = state.core_pos.get(team)
    core_def = False
    if core_pos:
        core_def = any(
            _in_range(t.pos, core_pos, ATTACK_SQ.get(t.kind, 0)) for t in turrets
        )

    types: dict[str, int] = {}
    for t in turrets:
        types[t.kind] = types.get(t.kind, 0) + 1

    undefended = [h.pos for h in harvesters if h.pos not in defended_h]

    return {
        "turret_count": len(turrets),
        "turret_types": types,
        "core_defended": core_def,
        "harvesters_defended": len(defended_h),
        "harvesters_total": len(harvesters),
        "conveyors_defended": len(defended_c),
        "conveyors_total": len(conveyors),
        "undefended_harvester_positions": undefended,
        "harvesters_exposed": exposed_h,
        "conveyors_exposed": exposed_c,
    }


def analyze(ctx: Context, teams: list[int]) -> DefenseReport:
    assert ctx.snapshots is not None
    state = ctx.snapshots[-1]

    tc: dict[int, int] = {}
    tt: dict[int, dict[str, int]] = {}
    cd: dict[int, bool] = {}
    hd: dict[int, int] = {}
    ht: dict[int, int] = {}
    hdp: dict[int, float] = {}
    cvd: dict[int, int] = {}
    cvt: dict[int, int] = {}
    cvdp: dict[int, float] = {}
    uhp: dict[int, list[Pos]] = {}
    he: dict[int, int] = {}
    ce: dict[int, int] = {}

    for t in teams:
        r = _analyze_team(state, t)
        tc[t] = r["turret_count"]  # type: ignore[assignment]
        tt[t] = r["turret_types"]  # type: ignore[assignment]
        cd[t] = r["core_defended"]  # type: ignore[assignment]
        hd[t] = r["harvesters_defended"]  # type: ignore[assignment]
        ht[t] = r["harvesters_total"]  # type: ignore[assignment]
        hdp[t] = 100 * hd[t] / ht[t] if ht[t] > 0 else 0.0
        cvd[t] = r["conveyors_defended"]  # type: ignore[assignment]
        cvt[t] = r["conveyors_total"]  # type: ignore[assignment]
        cvdp[t] = 100 * cvd[t] / cvt[t] if cvt[t] > 0 else 0.0
        uhp[t] = r["undefended_harvester_positions"]  # type: ignore[assignment]
        he[t] = r["harvesters_exposed"]  # type: ignore[assignment]
        ce[t] = r["conveyors_exposed"]  # type: ignore[assignment]

    return DefenseReport(
        turret_count=tc,
        turret_types=tt,
        core_defended=cd,
        harvesters_defended=hd,
        harvesters_total=ht,
        harvester_defense_pct=hdp,
        conveyors_defended=cvd,
        conveyors_total=cvt,
        conveyor_defense_pct=cvdp,
        undefended_harvester_positions=uhp,
        harvesters_exposed_to_enemy=he,
        conveyors_exposed_to_enemy=ce,
    )


def render(report: DefenseReport, teams: list[int]) -> str:
    lines: list[str] = []
    for t in teams:
        label = TEAM_LABEL[t]
        lines.append(f"--- Team {label} ---")
        types_str = ", ".join(f"{v} {k}" for k, v in report.turret_types[t].items())
        lines.append(f"  Turrets: {report.turret_count[t]} ({types_str})")
        lines.append(f"  Core defended: {'yes' if report.core_defended[t] else 'NO'}")
        lines.append(
            f"  Harvesters defended: {report.harvesters_defended[t]}/{report.harvesters_total[t]} ({report.harvester_defense_pct[t]:.0f}%)",
        )
        lines.append(
            f"  Conveyors defended: {report.conveyors_defended[t]}/{report.conveyors_total[t]} ({report.conveyor_defense_pct[t]:.0f}%)",
        )
        if report.undefended_harvester_positions[t]:
            lines.append(
                f"    undefended at: {', '.join(f'({p[0]},{p[1]})' for p in report.undefended_harvester_positions[t])}",
            )
        lines.append(
            f"  Exposed to enemy: {report.harvesters_exposed_to_enemy[t]} harv, {report.conveyors_exposed_to_enemy[t]} conv",
        )
        lines.append("")
    return "\n".join(lines)


register("defense", frozenset({"snapshots"}), analyze, render)
