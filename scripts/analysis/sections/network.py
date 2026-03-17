from __future__ import annotations

from dataclasses import dataclass

from ..constants import CONVEYOR_KINDS, TEAM_LABEL, Pos
from ..graph import (
    articulation_points,
    betweenness_centrality,
    connected_harvesters,
    dead_conveyor_positions,
    dead_end_count,
    max_flow_capacity,
    network_diameter,
    shared_trunk_tiles,
    shortest_path_lengths,
    steiner_tree_comparison,
)
from ..snapshot import team_entities
from ..types import Context, GameState
from . import register


@dataclass
class NetworkSnapshot:
    turn: int
    harvesters_connected: int
    harvesters_disconnected: int
    disconnected_positions: list[Pos]
    total_conveyors: int
    dead_conveyors: int
    dead_conveyor_pos: list[Pos]
    max_flow: float
    theoretical_max_flow: float
    flow_utilization: float
    betweenness_top5: list[tuple[Pos, float]]
    single_points_of_failure: list[tuple[Pos, int]]
    path_lengths: dict[Pos, int | None]
    avg_path_length: float | None
    steiner_actual: int
    steiner_approx: int | None
    steiner_waste_ratio: float | None
    diameter: int | None
    dead_ends: int
    shared_trunk: int


@dataclass
class NetworkReport:
    snapshots: dict[int, list[NetworkSnapshot]]


def _analyze_snapshot(state: GameState, team: int) -> NetworkSnapshot:
    conn, disconn = connected_harvesters(state, team)
    dead = dead_conveyor_positions(state, team)
    bc = betweenness_centrality(state, team)
    mf = max_flow_capacity(state, team)
    ap = articulation_points(state, team)
    sp = shortest_path_lengths(state, team)
    st_actual, st_approx, st_waste = steiner_tree_comparison(state, team)
    diam = network_diameter(state, team)
    de = dead_end_count(state, team)
    trunk = shared_trunk_tiles(state, team)

    total_conv = sum(1 for e in team_entities(state, team) if e.kind in CONVEYOR_KINDS)
    lengths = [v for v in sp.values() if v is not None]
    avg_pl = sum(lengths) / len(lengths) if lengths else None

    return NetworkSnapshot(
        turn=state.turn,
        harvesters_connected=len(conn),
        harvesters_disconnected=len(disconn),
        disconnected_positions=disconn,
        total_conveyors=total_conv,
        dead_conveyors=len(dead),
        dead_conveyor_pos=dead[:10],
        max_flow=mf.max_flow,
        theoretical_max_flow=mf.theoretical_max,
        flow_utilization=mf.utilization,
        betweenness_top5=bc,
        single_points_of_failure=ap,
        path_lengths=sp,
        avg_path_length=avg_pl,
        steiner_actual=st_actual,
        steiner_approx=st_approx,
        steiner_waste_ratio=st_waste,
        diameter=diam,
        dead_ends=de,
        shared_trunk=trunk,
    )


def analyze(ctx: Context, teams: list[int]) -> NetworkReport:
    assert ctx.snapshots is not None
    result: dict[int, list[NetworkSnapshot]] = {}
    for t in teams:
        snaps: list[NetworkSnapshot] = []
        for state in ctx.snapshots:
            ns = _analyze_snapshot(state, t)
            if ns.total_conveyors > 0 or ns.harvesters_connected > 0:
                snaps.append(ns)
        result[t] = snaps
    return NetworkReport(snapshots=result)


def _fmt(p: Pos) -> str:
    return f"({p[0]},{p[1]})"


def render(report: NetworkReport, teams: list[int]) -> str:
    lines: list[str] = []
    for t in teams:
        label = TEAM_LABEL[t]
        lines.append(f"--- Team {label} ---")
        for ns in report.snapshots.get(t, []):
            lines.append(f"  Turn {ns.turn}:")
            lines.append(
                f"    Harvesters: {ns.harvesters_connected} connected, {ns.harvesters_disconnected} disconnected",
            )
            if ns.disconnected_positions:
                lines.append(
                    f"      disconnected: {', '.join(_fmt(p) for p in ns.disconnected_positions)}",
                )
            lines.append(
                f"    Conveyors: {ns.total_conveyors} total, {ns.dead_conveyors} dead, {ns.dead_ends} dead-ends, {ns.shared_trunk} shared-trunk",
            )
            lines.append(
                f"    Max flow: {ns.max_flow:.2f} stacks/t (theoretical {ns.theoretical_max_flow:.2f}, util {ns.flow_utilization * 100:.0f}%)",
            )
            if ns.steiner_approx is not None:
                lines.append(
                    f"    Steiner: {ns.steiner_approx} optimal vs {ns.steiner_actual} actual (waste {ns.steiner_waste_ratio:.1f}x)"
                    if ns.steiner_waste_ratio
                    else f"    Steiner: {ns.steiner_approx} optimal vs {ns.steiner_actual} actual",
                )
            if ns.diameter is not None:
                lines.append(f"    Diameter: {ns.diameter}")
            if ns.avg_path_length is not None:
                lines.append(
                    f"    Path lengths: avg={ns.avg_path_length:.1f} min={min(v for v in ns.path_lengths.values() if v is not None)} max={max(v for v in ns.path_lengths.values() if v is not None)}",
                )
            if ns.betweenness_top5:
                lines.append(
                    f"    Betweenness: {', '.join(f'{_fmt(p)}={bc:.3f}' for p, bc in ns.betweenness_top5)}",
                )
            if ns.single_points_of_failure:
                lines.append(
                    f"    SPOFs: {', '.join(f'{_fmt(p)} cuts {n}' for p, n in ns.single_points_of_failure)}",
                )
            lines.append("")
    return "\n".join(lines)


register("network", frozenset({"snapshots"}), analyze, render)
