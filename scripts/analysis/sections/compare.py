from __future__ import annotations

from dataclasses import dataclass

from ..constants import CONVEYOR_KINDS
from ..graph import (
    connected_harvesters,
    dead_conveyor_positions,
    max_flow_capacity,
    steiner_tree_comparison,
)
from ..types import Context
from . import register


@dataclass
class Metric:
    name: str
    a: float
    b: float
    unit: str = ""
    higher_is_better: bool = True


@dataclass
class CompareReport:
    metrics: list[Metric]


def _pct_delta(a: float, b: float) -> str:
    if a == 0 and b == 0:
        return "  ="
    if a == 0:
        return " >>B"
    if b == 0:
        return "A>> "
    ratio = a / b
    if 0.95 <= ratio <= 1.05:
        return "  = "
    if ratio > 1:
        pct = (ratio - 1) * 100
        if pct > 200:
            return "A>>>"
        return f"A+{pct:.0f}%"
    pct = (1 / ratio - 1) * 100
    if pct > 200:
        return "B>>>"
    return f"B+{pct:.0f}%"


def _bar(a: float, b: float, *, higher_is_better: bool) -> str:
    total = a + b
    if total == 0:
        return "[------:------]"
    frac_a = a / total
    width = 12
    filled_a = round(frac_a * width)
    filled_b = width - filled_a

    left = "#" * filled_a + "." * max(0, width // 2 - filled_a)
    right = "." * max(0, width // 2 - filled_b) + "#" * filled_b

    if len(left) > width // 2:
        left = left[: width // 2]
    if len(right) > width // 2:
        right = right[: width // 2]

    winner = ""
    if a > b * 1.05:
        winner = " <" if higher_is_better else " !"
    elif b > a * 1.05:
        winner = " >" if higher_is_better else " !"

    return f"[{left}:{right}]{winner}"


def _fmt_val(v: float, unit: str) -> str:
    if unit == "t" and v >= 9999:
        return "never"
    if v == int(v) and abs(v) < 100000:
        return f"{int(v)}{unit}"
    return f"{v:.1f}{unit}"


def analyze(ctx: Context, _teams: list[int]) -> CompareReport:
    s = ctx.scan
    assert s is not None
    metrics: list[Metric] = []

    rh_a = s.resource_history.get(0, [])
    rh_b = s.resource_history.get(1, [])
    ti_a = rh_a[-1].titanium_collected if rh_a else 0
    ti_b = rh_b[-1].titanium_collected if rh_b else 0
    metrics.append(Metric("Ti collected", ti_a, ti_b))

    ir_a = s.income_rate.get(0, [])
    ir_b = s.income_rate.get(1, [])
    peak_a = max((r for _, r in ir_a), default=0.0)
    peak_b = max((r for _, r in ir_b), default=0.0)
    metrics.append(Metric("Peak income", peak_a, peak_b, "/t"))

    final_a = ir_a[-1][1] if ir_a else 0.0
    final_b = ir_b[-1][1] if ir_b else 0.0
    metrics.append(Metric("Final income", final_a, final_b, "/t"))

    frt_a = s.first_resource_turn.get(0)
    frt_b = s.first_resource_turn.get(1)
    metrics.append(
        Metric(
            "First income turn",
            frt_a or 9999,
            frt_b or 9999,
            "t",
            higher_is_better=False,
        ),
    )

    fck_a = s.first_conveyor_killed_turn.get(0)
    fck_b = s.first_conveyor_killed_turn.get(1)
    metrics.append(
        Metric(
            "First conv killed",
            fck_a or 9999,
            fck_b or 9999,
            "t",
            higher_is_better=False,
        ),
    )

    del_a = sum(s.core_deliveries_per_turn.get(0, {}).values())
    del_b = sum(s.core_deliveries_per_turn.get(1, {}).values())
    metrics.append(Metric("Core deliveries", del_a, del_b))

    metrics.append(
        Metric(
            "Harvesters built",
            s.harvester_count.get(0, 0),
            s.harvester_count.get(1, 0),
        ),
    )

    placed_a = s.entities_placed.get(0, {})
    placed_b = s.entities_placed.get(1, {})
    conv_a = sum(placed_a.get(k, 0) for k in CONVEYOR_KINDS)
    conv_b = sum(placed_b.get(k, 0) for k in CONVEYOR_KINDS)
    metrics.append(Metric("Conveyors built", conv_a, conv_b))

    metrics.append(
        Metric(
            "Builders spawned",
            placed_a.get("builder_bot", 0),
            placed_b.get("builder_bot", 0),
        ),
    )
    metrics.append(
        Metric(
            "Barriers built",
            placed_a.get("barrier", 0),
            placed_b.get("barrier", 0),
        ),
    )

    turrets_a = s.turrets_built.get(0, {})
    turrets_b = s.turrets_built.get(1, {})
    metrics.append(
        Metric(
            "Gunners built",
            turrets_a.get("gunner", 0),
            turrets_b.get("gunner", 0),
        ),
    )
    metrics.append(
        Metric(
            "Sentinels built",
            turrets_a.get("sentinel", 0),
            turrets_b.get("sentinel", 0),
        ),
    )
    metrics.append(
        Metric(
            "Launchers built",
            placed_a.get("launcher", 0),
            placed_b.get("launcher", 0),
        ),
    )
    metrics.append(
        Metric(
            "Foundries built",
            placed_a.get("foundry", 0),
            placed_b.get("foundry", 0),
        ),
    )
    metrics.append(
        Metric(
            "Bridges built",
            placed_a.get("bridge", 0),
            placed_b.get("bridge", 0),
        ),
    )

    shots_a = s.turret_shots.get(0, {})
    shots_b = s.turret_shots.get(1, {})
    total_shots_a = sum(shots_a.values())
    total_shots_b = sum(shots_b.values())
    metrics.append(Metric("Turret shots", total_shots_a, total_shots_b))

    metrics.append(
        Metric(
            "Builder losses",
            s.builder_losses.get(0, 0),
            s.builder_losses.get(1, 0),
            higher_is_better=False,
        ),
    )
    metrics.append(
        Metric(
            "Self-destructs",
            s.self_destructs.get(0, 0),
            s.self_destructs.get(1, 0),
        ),
    )

    metrics.append(
        Metric("Damage dealt", s.total_damage.get(0, 0), s.total_damage.get(1, 0)),
    )
    metrics.append(
        Metric("Entity kills", s.entity_kills.get(0, 0), s.entity_kills.get(1, 0)),
    )
    metrics.append(
        Metric("Builder kills", s.builder_kills.get(0, 0), s.builder_kills.get(1, 0)),
    )

    metrics.append(
        Metric("Total moves", s.total_moves.get(0, 0), s.total_moves.get(1, 0)),
    )

    idle_a = s.builder_idle_turns.get(0, 0)
    idle_b = s.builder_idle_turns.get(1, 0)
    pres_a = s.builder_presence_turns.get(0, 1)
    pres_b = s.builder_presence_turns.get(1, 1)
    metrics.append(
        Metric(
            "Idle %",
            100 * idle_a / pres_a if pres_a else 0,
            100 * idle_b / pres_b if pres_b else 0,
            "%",
            higher_is_better=False,
        ),
    )

    raids_a = len(s.raid_arrivals.get(0, []))
    raids_b = len(s.raid_arrivals.get(1, []))
    metrics.append(Metric("Raids", raids_a, raids_b))

    if ctx.snapshots:
        final = ctx.snapshots[-1]
        conn_a, disc_a = connected_harvesters(final, 0)
        conn_b, disc_b = connected_harvesters(final, 1)
        metrics.append(Metric("Harv connected (final)", len(conn_a), len(conn_b)))
        metrics.append(
            Metric(
                "Harv disconnected (final)",
                len(disc_a),
                len(disc_b),
                higher_is_better=False,
            ),
        )

        dead_a = dead_conveyor_positions(final, 0)
        dead_b = dead_conveyor_positions(final, 1)
        metrics.append(
            Metric(
                "Dead conveyors (final)",
                len(dead_a),
                len(dead_b),
                higher_is_better=False,
            ),
        )

        mf_a = max_flow_capacity(final, 0)
        mf_b = max_flow_capacity(final, 1)
        metrics.append(Metric("Max flow (final)", mf_a.max_flow, mf_b.max_flow, "/t"))

        st_a = steiner_tree_comparison(final, 0)
        st_b = steiner_tree_comparison(final, 1)
        if st_a[2] is not None and st_b[2] is not None:
            metrics.append(
                Metric(
                    "Steiner waste (final)",
                    st_a[2],
                    st_b[2],
                    "x",
                    higher_is_better=False,
                ),
            )

    return CompareReport(metrics=metrics)


def render(report: CompareReport, _teams: list[int]) -> str:
    lines: list[str] = []
    name_w = max(len(m.name) for m in report.metrics)
    lines.append(f"{'':>{name_w}}   {'A':>10}  {'B':>10}  {'delta':>6}  bar")
    lines.append(f"{'':>{name_w}}   {'---':>10}  {'---':>10}  {'---':>6}  ---")

    for m in report.metrics:
        a_str = _fmt_val(m.a, m.unit)
        b_str = _fmt_val(m.b, m.unit)
        delta = _pct_delta(m.a, m.b)
        bar = _bar(m.a, m.b, higher_is_better=m.higher_is_better)
        lines.append(
            f"{m.name:>{name_w}}   {a_str:>10}  {b_str:>10}  {delta:>6}  {bar}",
        )

    return "\n".join(lines)


register("compare", frozenset({"scan", "snapshots"}), analyze, render)
