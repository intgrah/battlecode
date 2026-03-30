"""Place a foundry adjacent to a mixed-flow conveyor.

Method 2 of RAx refining (splitter tech). Detects a conveyor carrying both
Ti and Ax flow, then places a foundry on a vacant tile adjacent to it. The
foundry will be fed by a splitter (placed by the place_splitter_foundry
task) which replaces the conveyor.

Unlike place_foundry_ti_conv, this preserves the original conveyor until
the splitter replaces it, keeping the Ti chain intact.
"""

from building import (
    BuildingArmouredConveyor,
    BuildingConveyor,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, Direction, Environment, Position
from util import DIR4_DELTA, INF

from .action import Action, PlaceFoundry
from .helpers import cardinal_adjacent, move_toward_with_road
from .state import State


def place_foundry_mixed_conv(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    f = state.my_flow
    best_conv: Position | None = None
    best_score = 0.0
    best_dist = INF

    for p in state.my_transport:
        i = state.idx(p.x, p.y)
        bld = state.building[i]
        match bld:
            case BuildingConveyor() | BuildingArmouredConveyor():
                pass
            case _:
                continue
        ti_f = f.ti[i]
        ax_f = f.ax[i]
        if ti_f <= 0 or ax_f <= 0:
            continue
        score = min(ti_f, ax_f)
        dist = (pos.x - p.x) ** 2 + (pos.y - p.y) ** 2
        if score > best_score or (score == best_score and dist < best_dist):
            best_score = score
            best_dist = dist
            best_conv = p

    if best_conv is None:
        return None

    cx, cy = best_conv.x, best_conv.y
    foundry_pos: Position | None = None
    foundry_dist = INF
    for dx, dy in DIR4_DELTA:
        nx, ny = cx + dx, cy + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = state.idx(nx, ny)
        env = state.env[ni]
        if env is None or env != Environment.EMPTY:
            continue
        bld = state.building[ni]
        match bld:
            case None | BuildingMarker():
                pass
            case BuildingRoad(team=team) if team == state.my_team:
                pass
            case _:
                continue
        d = (pos.x - nx) ** 2 + (pos.y - ny) ** 2
        if d < foundry_dist:
            foundry_dist = d
            foundry_pos = Position(nx, ny)

    if foundry_pos is None:
        return None

    if pos.distance_squared(foundry_pos) <= 2 and pos != foundry_pos:
        ct.draw_indicator_line(state.pos, foundry_pos, 255, 128, 0)
        return Direction.CENTRE, PlaceFoundry(foundry_pos)

    adj = cardinal_adjacent(state, pos, foundry_pos)
    if adj is None:
        return None
    move, build = move_toward_with_road(state, ct, adj)
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(foundry_pos) <= 2 and new_pos != foundry_pos:
            build = PlaceFoundry(foundry_pos)
    ct.draw_indicator_line(state.pos, foundry_pos, 255, 128, 0)
    return move, build
