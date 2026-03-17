from __future__ import annotations

import math
from dataclasses import dataclass

from ..constants import TEAM_LABEL, VISION_SQ, Pos
from ..snapshot import team_entities
from ..types import Context, GameState
from . import register


def _tiles_in_vision(cx: int, cy: int, rsq: int, w: int, h: int) -> set[Pos]:
    r = math.isqrt(rsq) + 1
    tiles: set[Pos] = set()
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx * dx + dy * dy <= rsq:
                nx_, ny = cx + dx, cy + dy
                if 0 <= nx_ < w and 0 <= ny < h:
                    tiles.add((nx_, ny))
    return tiles


@dataclass
class VisionSnapshot:
    turn: int
    current_pct: float
    cumulative_pct: float
    cumulative_tiles: int


@dataclass
class OreSnapshot:
    turn: int
    total: int
    discovered: int
    undiscovered: int
    discovery_pct: float
    harvested: int
    harvest_pct: float
    undiscovered_positions: list[Pos]


@dataclass
class MapControl:
    team_a_exclusive: int
    team_b_exclusive: int
    contested: int
    dark: int
    passable: int


@dataclass
class SpatialReport:
    vision: dict[int, list[VisionSnapshot]]
    ore: dict[int, list[OreSnapshot]]
    map_control: MapControl | None


def _vision_set(state: GameState, team: int) -> set[Pos]:
    visible: set[Pos] = set()
    for e in team_entities(state, team):
        rsq = VISION_SQ.get(e.kind)
        if rsq is not None:
            visible |= _tiles_in_vision(
                e.pos[0],
                e.pos[1],
                rsq,
                state.width,
                state.height,
            )
    return visible


def analyze(ctx: Context, teams: list[int]) -> SpatialReport:
    assert ctx.snapshots is not None
    states = ctx.snapshots

    all_ores: set[Pos] = set()
    if states:
        for y in range(states[0].height):
            for x in range(states[0].width):
                t = states[0].tiles[y][x]
                if t in (2, 3):
                    all_ores.add((x, y))
    total_ore = len(all_ores)
    passable = ctx.map_meta.passable_count

    vision_result: dict[int, list[VisionSnapshot]] = {}
    ore_result: dict[int, list[OreSnapshot]] = {}

    for team in teams:
        ever_seen: set[Pos] = set()
        discovered: set[Pos] = set()
        harvested: set[Pos] = set()
        v_snaps: list[VisionSnapshot] = []
        o_snaps: list[OreSnapshot] = []

        for state in states:
            vis = _vision_set(state, team)
            ever_seen |= vis
            discovered |= vis & all_ores

            for e in team_entities(state, team, "harvester"):
                if e.pos in all_ores:
                    harvested.add(e.pos)

            current_pct = 100 * len(vis) / passable if passable > 0 else 0.0
            cumulative_pct = 100 * len(ever_seen) / passable if passable > 0 else 0.0
            v_snaps.append(
                VisionSnapshot(state.turn, current_pct, cumulative_pct, len(ever_seen)),
            )

            undiscovered = all_ores - discovered
            o_snaps.append(
                OreSnapshot(
                    turn=state.turn,
                    total=total_ore,
                    discovered=len(discovered),
                    undiscovered=len(undiscovered),
                    discovery_pct=100 * len(discovered) / total_ore
                    if total_ore > 0
                    else 0.0,
                    harvested=len(harvested),
                    harvest_pct=100 * len(harvested) / total_ore
                    if total_ore > 0
                    else 0.0,
                    undiscovered_positions=sorted(undiscovered)[:20],
                ),
            )

        vision_result[team] = v_snaps
        ore_result[team] = o_snaps

    mc: MapControl | None = None
    if states:
        final = states[-1]
        vis_a = _vision_set(final, 0)
        vis_b = _vision_set(final, 1)
        dark = set()
        for y in range(final.height):
            for x in range(final.width):
                if (
                    final.tiles[y][x] != 1
                    and (x, y) not in vis_a
                    and (x, y) not in vis_b
                ):
                    dark.add((x, y))
        mc = MapControl(
            team_a_exclusive=len(vis_a - vis_b),
            team_b_exclusive=len(vis_b - vis_a),
            contested=len(vis_a & vis_b),
            dark=len(dark),
            passable=passable,
        )

    return SpatialReport(vision=vision_result, ore=ore_result, map_control=mc)


def render(report: SpatialReport, teams: list[int]) -> str:
    lines: list[str] = []
    for t in teams:
        label = TEAM_LABEL[t]
        lines.append(f"--- Team {label} ---")
        lines.append("  Vision:")
        lines.extend(
            f"    t{v.turn:>5d}: current {v.current_pct:5.1f}%  cumulative {v.cumulative_pct:5.1f}% ({v.cumulative_tiles} tiles)"
            for v in report.vision.get(t, [])
        )
        lines.append("  Ore discovery:")
        lines.extend(
            f"    t{o.turn:>5d}: {o.discovered}/{o.total} found ({o.discovery_pct:.0f}%), {o.harvested} harvested ({o.harvest_pct:.0f}%), {o.undiscovered} unseen"
            for o in report.ore.get(t, [])
        )
        ore_list = report.ore.get(t, [])
        if ore_list and ore_list[-1].undiscovered_positions:
            lines.append(
                f"    unseen ore: {', '.join(f'({p[0]},{p[1]})' for p in ore_list[-1].undiscovered_positions[:10])}",
            )
        lines.append("")

    mc = report.map_control
    if mc:
        lines.append(
            f"Map control: A={mc.team_a_exclusive} B={mc.team_b_exclusive} contested={mc.contested} dark={mc.dark} (of {mc.passable} passable)",
        )

    return "\n".join(lines)


register("spatial", frozenset({"snapshots"}), analyze, render)
