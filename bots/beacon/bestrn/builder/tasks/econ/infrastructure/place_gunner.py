"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/place_gunner.py`.

Defensive gunner / sentinel placement adjacent to a friendly harvester.
Iterates DIR8 neighbours: gunner placement requires a forward-ray that
hits an enemy harvester or transport (via `gunner_facing`); sentinel
placement requires the nearest enemy turret to be within range
(`sentinel_facing`). Falls back to placing on `my_pos` after a random
step-off.
"""

from __future__ import annotations

from cambc import Direction, EntityType, GameConstants
from util.directions import DIR4, DIR8

from builder.helpers import move_random, try_place
from builder.tasks.rejected import TaskRejected


def is_turret(kind):
    return (kind is not None) and (
        kind
        in (
            EntityType.GUNNER,
            EntityType.SENTINEL,
            EntityType.BREACH,
            EntityType.LAUNCHER,
        )
    )


def is_turret_or_transport(kind):
    return (kind is not None) and (
        kind
        in (
            EntityType.GUNNER,
            EntityType.SENTINEL,
            EntityType.BREACH,
            EntityType.LAUNCHER,
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
        )
    )


def is_precious_friendly(kind, bteam, team):
    """
    True if the building kind+team is a friendly building we must NOT
    destroy when placing a turret.
    """
    if bteam != team:
        return False
    return (kind is not None) and (
        kind in (EntityType.HARVESTER, EntityType.FOUNDRY, EntityType.LAUNCHER)
    )


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


def gunner_facing(self_, position):
    if position not in self_.adjacent_to_harvester:
        return None
    if not self_.is_buildable(position):
        return None
    kind = self_.building_kind[self_.idx(position)]
    team = self_.building_team[self_.idx(position)]
    if is_precious_friendly(kind, team, self_.my_team):
        return None
    if is_turret(kind):
        return None
    uid = self_.all_bots.get(position)
    if uid is not None and (uid != self_.my_id):
        return None
    for d in DIR8:
        n = position.add(d)
        if not self_.in_bounds(n):
            continue
        nk = self_.building_kind[self_.idx(n)]
        nt = self_.building_team[self_.idx(n)]
        is_enemy_gunner_or_sentinel = (
            ((nk is not None) and (nk in (EntityType.GUNNER, EntityType.SENTINEL)))
            and (nt is not None)
            and nt != self_.my_team
        )
        if not is_enemy_gunner_or_sentinel:
            continue
        for harvester_direction in DIR4:
            if harvester_direction != d:
                hn = position.add(harvester_direction)
                if not self_.in_bounds(hn):
                    continue
                if self_.building_kind[self_.idx(hn)] == EntityType.HARVESTER:
                    return d
    return None


def sentinel_facing(self_, ct, position):
    kind = self_.building_kind[self_.idx(position)]
    team = self_.building_team[self_.idx(position)]
    nearest = self_.nearest_enemy_turret
    if (
        (nearest is None)
        or position.distance_squared(nearest) > GameConstants.SENTINEL_VISION_RADIUS_SQ
        or position not in self_.adjacent_to_harvester
        or not self_.is_buildable(position)
        or is_turret_or_transport(kind)
        or is_precious_friendly(kind, team, self_.my_team)
        or not self_.in_bounds(position)
    ):
        return None
    uid = self_.all_bots.get(position)
    if uid is not None and (uid != self_.my_id):
        return None
    nearest = nearest
    d = direction_to(position, nearest)
    found_harvester = False
    for harvester_direction in DIR4:
        if harvester_direction != d:
            hn = position.add(harvester_direction)
            if not self_.in_bounds(hn):
                continue
            if self_.building_kind[self_.idx(hn)] == EntityType.HARVESTER:
                found_harvester = True
    if not found_harvester:
        return None
    shootable_tiles = ct.get_attackable_tiles_from(position, d, EntityType.SENTINEL)
    if nearest in shootable_tiles:
        return d
    return None


def place_sentinel_nearby(self_, ct):
    neighbours_8 = list(self_.neighbours_8)
    for test_position in neighbours_8:
        result = sentinel_facing(self_, ct, test_position)
        d = result
        if d is not None:
            return try_place(self_, ct, EntityType.SENTINEL, test_position, d, True)
    my_pos = self_.my_pos
    result = sentinel_facing(self_, ct, my_pos)
    d = result
    if d is not None and (move_random(self_, ct)):
        try_place(self_, ct, EntityType.SENTINEL, my_pos, d, True)
        return True
    return False


def place_gunner(self_, ct):
    neighbours_8 = list(self_.neighbours_8)
    for test_position in neighbours_8:
        result = gunner_facing(self_, test_position)
        d = result
        if d is not None:
            if try_place(self_, ct, EntityType.GUNNER, test_position, d, True):
                return None
            return TaskRejected("no valid gunner or sentinel placement nearby")
    my_pos = self_.my_pos
    result = gunner_facing(self_, my_pos)
    d = result
    if d is not None and (move_random(self_, ct)):
        try_place(self_, ct, EntityType.GUNNER, my_pos, d, True)
        return None
    if place_sentinel_nearby(self_, ct):
        return None
    return TaskRejected("no valid gunner or sentinel placement nearby")
