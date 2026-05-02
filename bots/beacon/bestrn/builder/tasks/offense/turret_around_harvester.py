"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/turret_around_harvester.py`.

Place gunner / sentinel turrets adjacent to a vulnerable enemy
harvester, capping at 2 gunners + 1 sentinel per harvester.
"""
from __future__ import annotations

from cambc import Direction, EntityType, Environment
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import move_random, try_place
from builder.tasks.offense.helpers import gunner_chain_facing, is_allied_transport, pick_harvester_target, scout_toward_enemy, vulnerable_harvesters
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.directions import DIR4

def direction_to(src, dst):
    """Snap the unit vector from `src` to `dst` to the nearest 45-degree direction."""
    dx = dst.x - src.x
    dy = dst.y - src.y
    if dx == 0 and dy == 0:
        return Direction.CENTRE
    adx = abs(dx)
    ady = abs(dy)
    if adx * 5 < ady * 2:
        return Direction.NORTH if dy < 0 else Direction.SOUTH
    if ady * 5 < adx * 2:
        return Direction.WEST if dx < 0 else Direction.EAST
    match (((dx > 0) - (dx < 0)), ((dy > 0) - (dy < 0))):
        case (1, -1):
            return Direction.NORTHEAST
        case (1, 1):
            return Direction.SOUTHEAST
        case (-1, 1):
            return Direction.SOUTHWEST
        case (-1, -1):
            return Direction.NORTHWEST
        case _:
            return Direction.CENTRE

def rotate_right(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHEAST
        case Direction.NORTHEAST:
            return Direction.EAST
        case Direction.EAST:
            return Direction.SOUTHEAST
        case Direction.SOUTHEAST:
            return Direction.SOUTH
        case Direction.SOUTH:
            return Direction.SOUTHWEST
        case Direction.SOUTHWEST:
            return Direction.WEST
        case Direction.WEST:
            return Direction.NORTHWEST
        case Direction.NORTHWEST:
            return Direction.NORTH
        case Direction.CENTRE:
            return Direction.CENTRE

def turret_around_harvester(self_, ct):
    vulnerable = vulnerable_harvesters(self_)
    if (not vulnerable):
        return TaskRejected("not on empty terrain cardinal to a vulnerable harvester")
    target = pick_harvester_target(self_, vulnerable)
    if self_.my_pos.distance_squared(target) != 1:
        return TaskRejected("not on empty terrain cardinal to a vulnerable harvester")
    if is_allied_transport(self_, self_.my_pos):
        return TaskRejected("not on empty terrain cardinal to a vulnerable harvester")
    if self_.is_enemy_building(self_.my_pos):
        return TaskRejected("not on empty terrain cardinal to a vulnerable harvester")
    build_position = self_.my_pos
    enemy_core = self_.en_core_guess
    move_random(self_, ct)
    direction = direction_to(build_position, enemy_core)
    if direction == direction_to(build_position, target):
        direction = rotate_right(direction)
    n_gunner = 0
    n_sentinel = 0
    for d in DIR4:
        n = target.add(d)
        if not self_.in_bounds(n):
            continue
        __opt_tuple = self_.get_building(n)
        if __opt_tuple is None:
            continue
        nk, nt = __opt_tuple
        if nt != self_.my_team:
            continue
        if nk == EntityType.GUNNER:
            n_gunner += 1
        elif nk == EntityType.SENTINEL:
            n_sentinel += 1
    if n_gunner < 2:
        gdir = gunner_chain_facing(self_, build_position)
        gd = gdir
        if gd is not None:
            try_place(self_, ct, EntityType.GUNNER, build_position, gd, True)
    if n_sentinel == 0 and self_.env[self_.idx(target)] == Environment.ORE_TITANIUM:
        try_place(self_, ct, EntityType.SENTINEL, build_position, direction, True)
    if ct.can_build_road(build_position):
        ct.build_road(build_position)
    scout_toward_enemy(self_, ct)
    return None
