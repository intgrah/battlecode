"""Drop a sentinel on a dangling end whose attack ray reaches a valuable
enemy structure. Candidates come from `dangling_set` (chain tips, never
existing conveyors). `_banned_facings` excludes directions blocked by
the chain's own input (turrets can't receive from the side they face) —
unioning structural feeders and friendly-harvester cardinals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import (
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import EntityType
from util.constants import MAX_WIDTH
from util.directions import DIR8

from builder.helpers import can_afford, make_move, move_random, try_place
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Direction, Position

    from builder import Builder


class TaskRejectedNoSentinelSpotError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no dangling end with an enemy in sentinel range"


class TaskRejectedCannotAffordSentinelError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "cannot afford SENTINEL"


def _is_enemy_valuable(self: Builder, pos: Position) -> bool:
    """Sentinel-worthy enemy targets:
    - Transports (conveyors / splitters / bridges) — economy disruption,
      sentinels eat the chain tile-by-tile.
    - Core, gunners, sentinels, breach, launchers — direct threats.
    Excluded:
    - Harvesters: sentinels can't attack harvesters.
    - Foundries: better left alive (50%-scaling drag on the opponent;
      destroying chains starves it without surrendering the scaling).
    - Roads / barriers / markers: not worth ammo.
    """
    b = self.get_building(pos)
    if b is None or b.team == self.my_team:
        return False
    if isinstance(b, BuildingHarvester):
        return False
    return isinstance(
        b,
        BuildingConveyor
        | BuildingArmouredConveyor
        | BuildingSplitter
        | BuildingBridge
        | BuildingCore
        | BuildingGunner
        | BuildingSentinel
        | BuildingBreach
        | BuildingLauncher,
    )


def _delivers_ammo(self: Builder, pos: Position, side: Position) -> bool:
    """`side` is a deliverer for a turret at `pos` iff it's a structural
    feeder of `pos` (conveyor / splitter / bridge in `in_edges`) or a
    friendly harvester (harvesters dump into all 4 cardinals; not in
    `in_edges`).
    """
    if side in self.in_edges[pos.y * MAX_WIDTH + pos.x]:
        return True
    b = self.get_building(side)
    return isinstance(b, BuildingHarvester) and b.team == self.my_team


def _sentinel_facing(
    self: Builder,
    ct: Controller,
    pos: Position,
) -> Direction | None:
    """First DIR8 direction such that a sentinel at `pos` facing `d`
    has at least one valuable enemy in its attack ray AND has no
    feeder on the tile in direction `d` (turrets can't receive ammo
    from the side they face).
    """
    for d in DIR8:
        front = pos.add(d)
        if self.in_bounds(front) and _delivers_ammo(self, pos, front):
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
