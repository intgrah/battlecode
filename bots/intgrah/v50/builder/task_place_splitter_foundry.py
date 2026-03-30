"""Replace a conveyor adjacent to a foundry with a splitter.

Method 2 of RAx refining (splitter tech). After place_foundry_mixed_conv
has placed a foundry next to a mixed-flow conveyor, this task replaces
that conveyor with a splitter. The splitter diverts a fraction of the
mixed flow to the foundry while forwarding the rest along the original
direction.

The splitter preserves the original direction of the conveyor it replaces,
ensuring downstream flow continues uninterrupted.
"""

from building import BuildingArmouredConveyor, BuildingConveyor
from cambc import Controller, Direction, Position

from .action import Action, PlaceSplitter
from .helpers import cardinal_adjacent, move_toward_with_road
from .state import State


def place_splitter_foundry(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    for fp in state.my_foundries:
        fx, fy = fp.x, fp.y
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = fx + dx, fy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = state.idx(nx, ny)
            bld = state.building[ni]
            match bld:
                case (
                    BuildingConveyor(team=team, direction=d)
                    | BuildingArmouredConveyor(team=team, direction=d)
                ):
                    if team != state.my_team:
                        continue
                case _:
                    continue
            target = Position(nx, ny)

            if pos.distance_squared(target) <= 2 and pos != target:
                state.debug_target = (target, 255, 200, 0)
                return Direction.CENTRE, PlaceSplitter(target, d)

            adj = cardinal_adjacent(state, pos, target)
            if adj is None:
                continue
            move, build = move_toward_with_road(state, ct, adj)
            if move != Direction.CENTRE and build is None:
                new_pos = pos.add(move)
                if new_pos.distance_squared(target) <= 2 and new_pos != target:
                    build = PlaceSplitter(target, d)
            state.debug_target = (target, 255, 200, 0)
            return move, build
    return None
