"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/place_offensive_sentinel.py`.

Drop a sentinel on a dangling end whose attack ray reaches a valuable
enemy structure. Candidates come from `dangling_set` (chain tips, never
existing conveyors).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Direction, EntityType

if TYPE_CHECKING:
    from cambc import Position
from util.directions import DIR8

from builder.helpers import can_afford, make_move, move_random, try_place
from builder.tasks.rejected import TaskRejected


def is_enemy_valuable(self_, pos):
    """Sentinel-worthy enemy targets."""
    __opt_tuple = self_.get_building(pos)
    if __opt_tuple is None:
        return False
    kind, team = __opt_tuple
    if team == self_.my_team:
        return False
    if kind == EntityType.HARVESTER:
        return False
    return kind in (
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
        EntityType.CORE,
        EntityType.GUNNER,
        EntityType.SENTINEL,
        EntityType.BREACH,
        EntityType.LAUNCHER,
    )


def delivers_ammo(self_, pos, side):
    """
    `side` is a deliverer for a turret at `pos` iff it's a structural
    feeder of `pos` or a friendly harvester.
    """
    in_edges = self_.in_edges[int(pos.y) * 50 + int(pos.x)]
    if side in in_edges:
        return True
    return (
        self_.building_kind[self_.idx(side)] == EntityType.HARVESTER
        and self_.building_team[self_.idx(side)] == self_.my_team
    )


def sentinel_facing(self_, ct, pos):
    """
    First DIR8 direction such that a sentinel at `pos` facing `d`
    has at least one valuable enemy in its attack ray AND has no
    feeder on the tile in direction `d`.
    """
    for d in DIR8:
        front = pos.add(d)
        if self_.in_bounds(front) and delivers_ammo(self_, pos, front):
            continue
        tiles = ct.get_attackable_tiles_from(pos, d, EntityType.SENTINEL)
        for t in tiles:
            if is_enemy_valuable(self_, t):
                return d
    return None


def place_offensive_sentinel(self_, ct):
    if not can_afford(self_, EntityType.SENTINEL):
        return TaskRejected("cannot afford SENTINEL")
    best_pos: Position | None = None
    best_facing: Direction | None = None
    best_dist = 1 << 30
    dangling = list(self_.dangling_set)
    for pos in dangling:
        if not self_.is_buildable(pos):
            continue
        uid = self_.all_bots.get(pos)
        if uid is not None and (uid != self_.my_id):
            continue
        facing = sentinel_facing(self_, ct, pos)
        facing = facing
        if facing is None:
            continue
        d = self_.my_pos.distance_squared(pos)
        if d < best_dist:
            best_dist = d
            best_pos = pos
            best_facing = facing
    best_pos = best_pos
    best_facing = best_facing
    if best_pos is None or best_facing is None:
        return TaskRejected("no dangling end with an enemy in sentinel range")
    if self_.my_pos == best_pos:
        move_random(self_, ct)
        return None
    if self_.my_pos.distance_squared(best_pos) <= 2:
        try_place(self_, ct, EntityType.SENTINEL, best_pos, best_facing, True)
        return None
    make_move(self_, ct, best_pos)
    return None
