from __future__ import annotations

import math
from dataclasses import dataclass

from ..constants import TEAM_LABEL, Pos
from ..snapshot import team_entities
from ..types import Context
from . import register


@dataclass
class BotClusterSnapshot:
    turn: int
    count: int
    avg_separation: float
    min_separation: float
    max_separation: float
    avg_core_distance: float
    max_core_distance: float


@dataclass
class BotsReport:
    action_breakdown: dict[int, dict[str, int]]
    action_breakdown_pct: dict[int, dict[str, float]]
    stuck_builders: dict[int, int]
    avg_longest_idle_streak: dict[int, float]
    avg_lifetime: dict[int, float]
    avg_builds_per_builder: dict[int, float]
    avg_max_core_distance: dict[int, float]
    furthest_from_core: dict[int, float]
    round_trips: dict[int, int]
    oscillation_pct: dict[int, float]
    idle_pct: dict[int, float]
    clustering: dict[int, list[BotClusterSnapshot]]


def _pairwise(bots: list[Pos]) -> tuple[float, float, float]:
    if len(bots) < 2:
        return 0.0, 0.0, 0.0
    dists: list[float] = []
    for i in range(len(bots)):
        for j in range(i + 1, len(bots)):
            dx = bots[i][0] - bots[j][0]
            dy = bots[i][1] - bots[j][1]
            dists.append(math.sqrt(dx * dx + dy * dy))
    return sum(dists) / len(dists), min(dists), max(dists)


def analyze(ctx: Context, teams: list[int]) -> BotsReport:
    s = ctx.scan
    assert s is not None

    ab: dict[int, dict[str, int]] = {}
    abp: dict[int, dict[str, float]] = {}
    stuck: dict[int, int] = {}
    avg_idle: dict[int, float] = {}
    avg_life: dict[int, float] = {}
    avg_builds: dict[int, float] = {}
    avg_max_cd: dict[int, float] = {}
    furthest: dict[int, float] = {}
    rtrips: dict[int, int] = {}
    osc_pct: dict[int, float] = {}
    idle_pct: dict[int, float] = {}

    for t in teams:
        team_bots = [bid for bid, bt in s.builder_team.items() if bt == t]
        actions: dict[str, int] = {}
        total_actions = 0
        for bid in team_bots:
            for _, act in s.builder_actions.get(bid, []):
                actions[act] = actions.get(act, 0) + 1
                total_actions += 1
        ab[t] = actions
        abp[t] = (
            {k: 100 * v / total_actions for k, v in actions.items()}
            if total_actions > 0
            else {}
        )

        stuck_count = 0
        max_idle_streaks: list[int] = []
        for bid in team_bots:
            acts = s.builder_actions.get(bid, [])
            consec = 0
            max_i = 0
            was_stuck = False
            for _, act in acts:
                if act == "idle":
                    consec += 1
                    if consec >= 10 and not was_stuck:
                        stuck_count += 1
                        was_stuck = True
                else:
                    max_i = max(max_i, consec)
                    consec = 0
            max_i = max(max_i, consec)
            max_idle_streaks.append(max_i)
        stuck[t] = stuck_count
        avg_idle[t] = (
            sum(max_idle_streaks) / len(max_idle_streaks) if max_idle_streaks else 0.0
        )

        lifetimes: list[int] = []
        build_counts: list[int] = []
        for bid in team_bots:
            born = s.builder_born.get(bid, 0)
            death = s.builder_death.get(bid, s.total_turns)
            lifetimes.append(death - born)
            bc = sum(
                1
                for _, act in s.builder_actions.get(bid, [])
                if act.startswith("build_")
            )
            build_counts.append(bc)
        avg_life[t] = sum(lifetimes) / len(lifetimes) if lifetimes else 0.0
        avg_builds[t] = sum(build_counts) / len(build_counts) if build_counts else 0.0

        core = ctx.map_meta.core_pos.get(t)
        max_dists: list[float] = []
        trips = 0
        if core:
            for bid in team_bots:
                hist = s.builder_pos_history.get(bid, [])
                md = 0.0
                for _, pos in hist:
                    d = math.sqrt((pos[0] - core[0]) ** 2 + (pos[1] - core[1]) ** 2)
                    md = max(md, d)
                max_dists.append(md)

                left = False
                for _, pos in hist:
                    manhattan = abs(pos[0] - core[0]) + abs(pos[1] - core[1])
                    if manhattan > 3:
                        left = True
                    elif left and manhattan <= 3:
                        trips += 1
                        left = False

        avg_max_cd[t] = sum(max_dists) / len(max_dists) if max_dists else 0.0
        furthest[t] = max(max_dists) if max_dists else 0.0
        rtrips[t] = trips

        osc_turns = 0
        total_bot_turns = 0
        for bid in team_bots:
            hist = s.builder_pos_history.get(bid, [])
            positions = [p for _, p in hist]
            total_bot_turns += len(positions)
            for i in range(10, len(positions)):
                window = positions[i - 10 : i]
                if len(set(window)) <= 2:
                    osc_turns += 1
        osc_pct[t] = 100 * osc_turns / total_bot_turns if total_bot_turns > 0 else 0.0

        active = s.builder_presence_turns.get(t, 0)
        idle = s.builder_idle_turns.get(t, 0)
        idle_pct[t] = 100 * idle / active if active > 0 else 0.0

    clustering: dict[int, list[BotClusterSnapshot]] = {}
    if ctx.snapshots:
        for t in teams:
            snaps: list[BotClusterSnapshot] = []
            for state in ctx.snapshots:
                bots = [e.pos for e in team_entities(state, t, "builder_bot")]
                avg_s, min_s, max_s = _pairwise(bots)
                core = state.core_pos.get(t)
                if core and bots:
                    cd = [
                        math.sqrt((b[0] - core[0]) ** 2 + (b[1] - core[1]) ** 2)
                        for b in bots
                    ]
                    avg_cd = sum(cd) / len(cd)
                    max_cd = max(cd)
                else:
                    avg_cd = 0.0
                    max_cd = 0.0
                snaps.append(
                    BotClusterSnapshot(
                        state.turn,
                        len(bots),
                        avg_s,
                        min_s,
                        max_s,
                        avg_cd,
                        max_cd,
                    ),
                )
            clustering[t] = snaps

    return BotsReport(
        action_breakdown=ab,
        action_breakdown_pct=abp,
        stuck_builders=stuck,
        avg_longest_idle_streak=avg_idle,
        avg_lifetime=avg_life,
        avg_builds_per_builder=avg_builds,
        avg_max_core_distance=avg_max_cd,
        furthest_from_core=furthest,
        round_trips=rtrips,
        oscillation_pct=osc_pct,
        idle_pct=idle_pct,
        clustering=clustering,
    )


def render(report: BotsReport, teams: list[int]) -> str:
    lines: list[str] = []
    for t in teams:
        label = TEAM_LABEL[t]
        lines.append(f"--- Team {label} ---")
        ab = report.action_breakdown[t]
        abp = report.action_breakdown_pct[t]
        if ab:
            parts = [
                f"{k}={v} ({abp.get(k, 0):.0f}%)"
                for k, v in sorted(ab.items(), key=lambda x: -x[1])
            ]
            lines.append(f"  Actions: {', '.join(parts)}")
        lines.append(
            f"  Stuck builders (10+ idle): {report.stuck_builders[t]}  Avg longest idle streak: {report.avg_longest_idle_streak[t]:.0f}",
        )
        lines.append(
            f"  Avg lifetime: {report.avg_lifetime[t]:.0f}  Avg builds/builder: {report.avg_builds_per_builder[t]:.1f}",
        )
        lines.append(
            f"  Avg max core dist: {report.avg_max_core_distance[t]:.1f}  Furthest: {report.furthest_from_core[t]:.1f}  Round trips: {report.round_trips[t]}",
        )
        lines.append(
            f"  Idle: {report.idle_pct[t]:.1f}%  Oscillation: {report.oscillation_pct[t]:.1f}%",
        )
        lines.append("  Clustering:")
        for cs in report.clustering.get(t, []):
            if cs.count == 0:
                continue
            lines.append(
                f"    t{cs.turn:>5d}: {cs.count} bots  sep={cs.avg_separation:.1f} ({cs.min_separation:.1f}-{cs.max_separation:.1f})  core={cs.avg_core_distance:.1f} (max {cs.max_core_distance:.1f})",
            )
        lines.append("")
    return "\n".join(lines)


register("bots", frozenset({"scan", "snapshots"}), analyze, render)
