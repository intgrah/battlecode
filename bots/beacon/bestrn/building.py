"""
Per-tile building helpers. The bot stores building state in the
`Builder`'s `SoA` arrays (`building_kind[i]`, `building_team[i]`,
`out_edges[i]`) — there's no separate `Building` ADT.

These free functions handle reading from `ct` at `_add_topology` time
(the only place Building info enters the bot's state).
"""
from __future__ import annotations

from cambc import Direction, EntityType, Position
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Team

def make_building(ct, bid):
    """
    Read kind + team at `bid` from `ct`. Panics on `BuilderBot` (not a
    building) — by convention callers gate on `is_in_vision` first.
    """
    kind = ct.get_entity_type(bid)
    team = ct.get_team(bid)
    if (kind == EntityType.BUILDER_BOT):
        raise Exception("BUILDER_BOT is not a building")
    return (kind, team)

def edge_targets(ct, pos, bid, kind):
    """
    Routing output positions for the building at `pos` (id `bid`, kind
    `kind`). Empty for non-routing variants. Used by `_add_topology` to
    populate `out_edges[i]`.
    """
    match kind:
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR:
            return [pos.add(ct.get_direction(bid))]
        case EntityType.BRIDGE:
            return [ct.get_bridge_target(bid)]
        case EntityType.SPLITTER:
            d = ct.get_direction(bid)
            return [pos.add(d), pos.add(rotate_right_2(d)), pos.add(rotate_left_2(d))]
        case _:
            return []

def splitter_back_input(pos, outputs):
    """
    Splitter back-input cell (the side opposite its forward output). Sum
    of the three outputs = `3*pos + d`, so `4*pos - sum = pos - d`.
    Order-independent.
    """
    sum_x: int = sum((p.x for p in outputs))
    sum_y: int = sum((p.y for p in outputs))
    return Position(x=4 * pos.x - sum_x, y=4 * pos.y - sum_y)

def rotate_right_2(d):
    match d:
        case Direction.NORTH:
            return Direction.EAST
        case Direction.NORTHEAST:
            return Direction.SOUTHEAST
        case Direction.EAST:
            return Direction.SOUTH
        case Direction.SOUTHEAST:
            return Direction.SOUTHWEST
        case Direction.SOUTH:
            return Direction.WEST
        case Direction.SOUTHWEST:
            return Direction.NORTHWEST
        case Direction.WEST:
            return Direction.NORTH
        case Direction.NORTHWEST:
            return Direction.NORTHEAST
        case Direction.CENTRE:
            return Direction.CENTRE

def rotate_left_2(d):
    match d:
        case Direction.NORTH:
            return Direction.WEST
        case Direction.NORTHEAST:
            return Direction.NORTHWEST
        case Direction.EAST:
            return Direction.NORTH
        case Direction.SOUTHEAST:
            return Direction.NORTHEAST
        case Direction.SOUTH:
            return Direction.EAST
        case Direction.SOUTHWEST:
            return Direction.SOUTHEAST
        case Direction.WEST:
            return Direction.SOUTH
        case Direction.NORTHWEST:
            return Direction.SOUTHWEST
        case Direction.CENTRE:
            return Direction.CENTRE
