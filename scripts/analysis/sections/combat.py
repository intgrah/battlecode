from __future__ import annotations

from dataclasses import dataclass

from ..constants import TEAM_LABEL
from ..types import Context
from . import register


@dataclass
class CombatReport:
    total_damage_dealt: dict[int, int]
    damage_by_victim_type: dict[int, dict[str, int]]
    peak_dps: dict[int, float]
    self_destruct_count: dict[int, int]
    self_destruct_window: dict[int, tuple[int, int] | None]
    builder_losses: dict[int, int]
    turrets_built: dict[int, dict[str, int]]
    turret_shots: dict[int, dict[str, int]]
    shots_per_turret: dict[int, float]
    buildings_destroyed: dict[int, dict[str, int]]
    raid_count: dict[int, int]
    first_raid_turn: dict[int, int | None]
    core_hp_timeline: dict[int, list[tuple[int, int]]]


def analyze(ctx: Context, teams: list[int]) -> CombatReport:
    s = ctx.scan
    assert s is not None

    peak_dps: dict[int, float] = {}
    for t in teams:
        events = s.damage_events.get(t, [])
        if not events:
            peak_dps[t] = 0.0
            continue
        dmg_timeline = [0] * s.total_turns
        for ev in events:
            if ev.turn < s.total_turns:
                dmg_timeline[ev.turn] += ev.damage
        window = 100
        best = 0.0
        for i in range(window, s.total_turns):
            dps = sum(dmg_timeline[i - window : i]) / window
            best = max(best, dps)
        peak_dps[t] = best

    sd_window: dict[int, tuple[int, int] | None] = {}
    for t in teams:
        turns = s.self_destruct_turns.get(t, [])
        sd_window[t] = (turns[0], turns[-1]) if turns else None

    spt: dict[int, float] = {}
    for t in teams:
        tb = sum(s.turrets_built.get(t, {}).values())
        ts = sum(s.turret_shots.get(t, {}).values())
        spt[t] = ts / tb if tb > 0 else 0.0

    return CombatReport(
        total_damage_dealt={t: s.total_damage.get(t, 0) for t in teams},
        damage_by_victim_type={t: s.damage_by_victim.get(t, {}) for t in teams},
        peak_dps=peak_dps,
        self_destruct_count={t: s.self_destructs.get(t, 0) for t in teams},
        self_destruct_window=sd_window,
        builder_losses={t: s.builder_losses.get(t, 0) for t in teams},
        turrets_built={t: s.turrets_built.get(t, {}) for t in teams},
        turret_shots={t: s.turret_shots.get(t, {}) for t in teams},
        shots_per_turret=spt,
        buildings_destroyed={t: s.buildings_destroyed.get(t, {}) for t in teams},
        raid_count={t: len(s.raid_arrivals.get(t, [])) for t in teams},
        first_raid_turn={
            t: s.raid_arrivals[t][0] if s.raid_arrivals.get(t) else None for t in teams
        },
        core_hp_timeline={t: s.core_hp_timeline.get(t, []) for t in teams},
    )


def render(report: CombatReport, teams: list[int]) -> str:
    lines: list[str] = []
    for t in teams:
        label = TEAM_LABEL[t]
        lines.append(f"--- Team {label} ---")
        lines.append(
            f"  Damage dealt: {report.total_damage_dealt[t]}  Peak DPS (100t): {report.peak_dps[t]:.1f}/t",
        )
        if report.damage_by_victim_type[t]:
            lines.append(f"  By victim: {report.damage_by_victim_type[t]}")
        lines.append(f"  Self-destructs: {report.self_destruct_count[t]}")
        w = report.self_destruct_window[t]
        if w:
            lines.append(f"    window: t{w[0]}-t{w[1]}")
        lines.append(f"  Builder losses: {report.builder_losses[t]}")
        if report.turrets_built[t]:
            lines.append(
                f"  Turrets built: {report.turrets_built[t]}  Shots: {report.turret_shots[t]}  Shots/turret: {report.shots_per_turret[t]:.1f}",
            )
        if report.buildings_destroyed[t]:
            lines.append(f"  Buildings destroyed: {report.buildings_destroyed[t]}")
        if report.raid_count[t] > 0:
            lines.append(
                f"  Raids: {report.raid_count[t]} (first t{report.first_raid_turn[t]})",
            )
        hp = report.core_hp_timeline.get(1 - t, [])
        if hp:
            lines.append(
                f"  Enemy core HP: {hp[-1][1]} (from {hp[0][1] if hp else 500})",
            )
        lines.append("")
    return "\n".join(lines)


register("combat", frozenset({"scan"}), analyze, render)
