from __future__ import annotations

from dataclasses import dataclass

from ..constants import TEAM_LABEL, Pos
from ..types import Context
from . import register


@dataclass
class EconomyReport:
    first_income_turn: dict[int, int | None]
    peak_income_rate: dict[int, float]
    final_income_rate: dict[int, float]
    income_quartiles: dict[int, tuple[float, float, float]]
    total_spent: dict[int, int]
    conveyor_moves_total: int
    conveyor_moves_avg: float
    conveyor_moves_peak: int
    top_flow_tiles: list[tuple[Pos, int]]
    first_delivery_turn: dict[int, int | None]
    total_core_deliveries: dict[int, int]
    delivery_rate_windows: dict[int, list[tuple[str, float]]]
    flow_loss: dict[int, int]
    delivery_efficiency: dict[int, float]


def analyze(ctx: Context, teams: list[int]) -> EconomyReport:
    s = ctx.scan
    assert s is not None

    peak: dict[int, float] = {}
    final: dict[int, float] = {}
    quartiles: dict[int, tuple[float, float, float]] = {}
    for t in teams:
        ir = s.income_rate.get(t, [])
        if ir:
            rates = [r for _, r in ir]
            peak[t] = max(rates)
            final[t] = rates[-1]
            n = len(rates)
            quartiles[t] = (rates[n // 4], rates[n // 2], rates[3 * n // 4])
        else:
            peak[t] = 0.0
            final[t] = 0.0
            quartiles[t] = (0.0, 0.0, 0.0)

    spent: dict[int, int] = {}
    for t in teams:
        rh = s.resource_history.get(t, [])
        if rh:
            col = rh[-1].titanium_collected + rh[-1].axionite_collected
            remaining = rh[-1].titanium + rh[-1].axionite
            spent[t] = col + 1000 - remaining
        else:
            spent[t] = 0

    cmp = s.conveyor_moves_per_turn
    total_conv = sum(cmp)
    avg_conv = total_conv / len(cmp) if cmp else 0.0
    peak_conv = max(cmp) if cmp else 0

    total_del: dict[int, int] = {}
    rate_windows: dict[int, list[tuple[str, float]]] = {}
    loss: dict[int, int] = {}
    efficiency: dict[int, float] = {}
    windows = [(0, 200), (200, 500), (500, 1000), (1000, 1500), (1500, 2000)]

    for t in teams:
        cd = s.core_deliveries_per_turn.get(t, {})
        ho = s.harvester_output_per_turn.get(t, {})
        total_del[t] = sum(cd.values())
        total_ho = sum(ho.values())
        loss[t] = total_ho - total_del[t]

        h_count = s.harvester_count.get(t, 0)
        theoretical = h_count * (s.total_turns / 4) if h_count > 0 else 0
        efficiency[t] = 100 * total_del[t] / theoretical if theoretical > 0 else 0.0

        rw: list[tuple[str, float]] = []
        for lo, hi in windows:
            count = sum(v for turn, v in cd.items() if lo <= turn < hi)
            rate = count / (hi - lo) if hi > lo else 0
            rw.append((f"t{lo}-{hi}", rate))
        rate_windows[t] = rw

    return EconomyReport(
        first_income_turn={t: s.first_resource_turn.get(t) for t in teams},
        peak_income_rate=peak,
        final_income_rate=final,
        income_quartiles=quartiles,
        total_spent=spent,
        conveyor_moves_total=total_conv,
        conveyor_moves_avg=avg_conv,
        conveyor_moves_peak=peak_conv,
        top_flow_tiles=s.top_flow_tiles,
        first_delivery_turn={t: s.first_delivery_turn.get(t) for t in teams},
        total_core_deliveries=total_del,
        delivery_rate_windows=rate_windows,
        flow_loss=loss,
        delivery_efficiency=efficiency,
    )


def _fmt_turn(t: int | None) -> str:
    return f"t{t}" if t is not None else "never"


def render(report: EconomyReport, teams: list[int]) -> str:
    lines: list[str] = []
    for t in teams:
        label = TEAM_LABEL[t]
        lines.append(f"--- Team {label} ---")
        lines.append(
            f"  First income: {_fmt_turn(report.first_income_turn[t])}  First delivery: {_fmt_turn(report.first_delivery_turn[t])}",
        )
        lines.append(
            f"  Income rate: peak={report.peak_income_rate[t]:.1f}/t  final={report.final_income_rate[t]:.1f}/t",
        )
        q = report.income_quartiles[t]
        lines.append(
            f"  Income quartiles (25/50/75): {q[0]:.1f} / {q[1]:.1f} / {q[2]:.1f}",
        )
        lines.append(f"  Total spent: ~{report.total_spent[t]}")
        lines.append(
            f"  Core deliveries: {report.total_core_deliveries[t]}  Flow loss: {report.flow_loss[t]}  Efficiency: {report.delivery_efficiency[t]:.0f}%",
        )
        rw = report.delivery_rate_windows[t]
        lines.append(
            f"  Delivery rate: {' | '.join(f'{label}:{rate:.2f}/t' for label, rate in rw)}",
        )
        lines.append("")

    lines.append(
        f"Conveyor moves: {report.conveyor_moves_total} total  avg={report.conveyor_moves_avg:.1f}/t  peak={report.conveyor_moves_peak}/t",
    )
    if report.top_flow_tiles:
        lines.append(
            f"Top flow tiles: {', '.join(f'({p[0]},{p[1]})={c}' for p, c in report.top_flow_tiles)}",
        )

    return "\n".join(lines)


register("economy", frozenset({"scan"}), analyze, render)
