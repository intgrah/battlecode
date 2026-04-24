from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import (
    BuildingBreach,
    BuildingCore,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSentinel,
)
from cambc import EntityType
from util.constants import MAX_WIDTH
from util.directions import DELTA_TO_DIR, DIR4, DIR8

from builder.helpers import can_afford, make_move, move_random, try_place
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Direction, Position

    from builder import Builder


class TaskRejectedNoSentinelSpotError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no dangling end with an enemy in sentinel range"


class TaskRejectedCannotAffordSentinelError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "cannot afford SENTINEL"


def _is_enemy_valuable(self: Builder, pos: Position) -> bool:
    b = self.get_building(pos)
    if b is None or b.team == self.my_team:
        return False
    return isinstance(
        b,
        BuildingHarvester
        | BuildingCore
        | BuildingFoundry
        | BuildingGunner
        | BuildingSentinel
        | BuildingBreach
        | BuildingLauncher,
    )


def _banned_facings(self: Builder, pos: Position) -> set[Direction]:
    """Directions a sentinel at `pos` must NOT face, because the tile in
    that direction feeds it ammo. Turrets can't receive from the side
    they face.
    - Structural feeders (conveyor/splitter/bridge) via `in_edges`: add
      the cardinal/diagonal vector from feeder to pos.
    - Friendly harvesters on cardinal neighbours: add the cardinal
      direction toward the harvester (harvesters dump into all 4
      cardinals, not tracked in `in_edges`)."""
    banned: set[Direction] = set()
    for feeder in self.in_edges[pos.y * MAX_WIDTH + pos.x]:
        dx, dy = pos.x - feeder.x, pos.y - feeder.y
        d = DELTA_TO_DIR.get((dx, dy))
        if d is not None:
            banned.add(d)
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if isinstance(b, BuildingHarvester) and b.team == self.my_team:
            banned.add(d)
    return banned


def _sentinel_facing(
    self: Builder,
    ct: Controller,
    pos: Position,
) -> Direction | None:
    """Return the first DIR8 direction for which placing a sentinel at
    `pos` facing `d` would cover a valuable enemy building AND does not
    collide with any feeder side; else None."""
    banned = _banned_facings(self, pos)
    for d in DIR8:
        if d in banned:
            continue
        tiles = ct.get_attackable_tiles_from(pos, d, EntityType.SENTINEL)
        for t in tiles:
            if _is_enemy_valuable(self, t):
                return d
    return None


def place_offensive_sentinel(self: Builder, ct: Controller) -> None:
    if not can_afford(self, EntityType.SENTINEL):
        raise TaskRejectedCannotAffordSentinelError

    # Sentinels go on DANGLING ENDS — tiles that a conveyor points at but
    # have no consumer yet. Iterating dangling_set is both correct and
    # cheap; nearby_buildings is irrelevant (we never demolish a conveyor
    # to place a sentinel — that was the earlier bug).
    best_pos: Position | None = None
    best_facing: Direction | None = None
    best_dist = 1 << 30
    for pos in self.dangling_set:
        if not self.is_buildable(pos):
            continue
        if pos in self.all_bots and self.all_bots[pos] != self.my_id:
            continue
        facing = _sentinel_facing(self, ct, pos)
        if facing is None:
            continue
        d = self.my_pos.distance_squared(pos)
        if d < best_dist:
            best_dist = d
            best_pos = pos
            best_facing = facing

    if best_pos is None or best_facing is None:
        raise TaskRejectedNoSentinelSpotError

    # `ct.can_build(SENTINEL, pos)` rejects when a builder (us included)
    # is on the tile, so we must step off first.
    if self.my_pos == best_pos:
        move_random(self, ct)
        return
    if self.my_pos.distance_squared(best_pos) <= 2:
        try_place(self, ct, EntityType.SENTINEL, best_pos, best_facing)
        return
    make_move(self, ct, best_pos)
