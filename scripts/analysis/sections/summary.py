from __future__ import annotations

from dataclasses import dataclass

from ..constants import TEAM_LABEL
from ..types import Context
from . import register


@dataclass
class SummaryReport:
    winner: str
    total_turns: int
    map_size: tuple[int, int]
    final_titanium: dict[int, int]
    final_axionite: dict[int, int]
    titanium_collected: dict[int, int]
    axionite_collected: dict[int, int]
    entities_placed: dict[int, dict[str, int]]
    entities_removed: dict[int, dict[str, int]]
    entities_alive: dict[int, dict[str, int]]
    first_built: dict[int, dict[str, int]]
    total_moves: dict[int, int]
    total_damage_dealt: dict[int, int]
    entity_kills: dict[int, int]
    builder_kills: dict[int, int]
    self_destructs: dict[int, int]
    tle_count: dict[int, int]
    avg_exec_time_us: dict[int, float]
    max_exec_time_us: dict[int, int]


def analyze(ctx: Context, teams: list[int]) -> SummaryReport:
    s = ctx.scan
    assert s is not None

    final_ti: dict[int, int] = {}
    final_ax: dict[int, int] = {}
    ti_col: dict[int, int] = {}
    ax_col: dict[int, int] = {}
    for t in teams:
        rh = s.resource_history.get(t, [])
        if rh:
            final_ti[t] = rh[-1].titanium
            final_ax[t] = rh[-1].axionite
            ti_col[t] = rh[-1].titanium_collected
            ax_col[t] = rh[-1].axionite_collected
        else:
            final_ti[t] = 0
            final_ax[t] = 0
            ti_col[t] = 0
            ax_col[t] = 0

    avg_exec: dict[int, float] = {}
    for t in teams:
        samples = s.exec_time_samples.get(t, 0)
        avg_exec[t] = s.exec_time_total.get(t, 0) / samples if samples > 0 else 0.0

    return SummaryReport(
        winner=s.winner,
        total_turns=s.total_turns,
        map_size=(ctx.map_meta.width, ctx.map_meta.height),
        final_titanium=final_ti,
        final_axionite=final_ax,
        titanium_collected=ti_col,
        axionite_collected=ax_col,
        entities_placed={t: s.entities_placed.get(t, {}) for t in teams},
        entities_removed={t: s.entities_removed.get(t, {}) for t in teams},
        entities_alive={t: s.entities_alive.get(t, {}) for t in teams},
        first_built={t: s.first_built.get(t, {}) for t in teams},
        total_moves={t: s.total_moves.get(t, 0) for t in teams},
        total_damage_dealt={t: s.total_damage.get(t, 0) for t in teams},
        entity_kills={t: s.entity_kills.get(t, 0) for t in teams},
        builder_kills={t: s.builder_kills.get(t, 0) for t in teams},
        self_destructs={t: s.self_destructs.get(t, 0) for t in teams},
        tle_count={t: s.tle_count.get(t, 0) for t in teams},
        avg_exec_time_us=avg_exec,
        max_exec_time_us={t: s.max_exec_time.get(t, 0) for t in teams},
    )


def render(report: SummaryReport, teams: list[int]) -> str:
    lines: list[str] = []
    w, h = report.map_size
    lines.append(
        f"Winner: Team {report.winner}  |  Turns: {report.total_turns}  |  Map: {w}x{h}",
    )
    lines.append("")

    for t in teams:
        label = TEAM_LABEL[t]
        lines.append(f"--- Team {label} ---")
        lines.append(
            f"  Ti={report.final_titanium[t]} Ax={report.final_axionite[t]}  collected Ti={report.titanium_collected[t]} Ax={report.axionite_collected[t]}",
        )
        lines.append(f"  Built: {report.entities_placed[t]}")
        lines.append(f"  Lost:  {report.entities_removed[t]}")
        lines.append(f"  Alive: {report.entities_alive[t]}")

        milestones = [
            f"{k}@t{v}"
            for k, v in sorted(report.first_built[t].items(), key=lambda x: x[1])
            if k not in ("core", "marker", "road")
        ]
        if milestones:
            lines.append(f"  Firsts: {', '.join(milestones)}")

        lines.append(
            f"  Moves: {report.total_moves[t]}  Damage: {report.total_damage_dealt[t]}  Kills: {report.entity_kills[t]}  Builder kills: {report.builder_kills[t]}  Self-destructs: {report.self_destructs[t]}",
        )
        if report.tle_count[t] > 0:
            lines.append(
                f"  TLEs: {report.tle_count[t]}  Avg exec: {report.avg_exec_time_us[t]:.0f}us  Max: {report.max_exec_time_us[t]}us",
            )
        lines.append("")

    return "\n".join(lines)


register("summary", frozenset({"scan"}), analyze, render)
