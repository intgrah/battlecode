"""Standing on an enemy building cardinal to a vulnerable enemy
harvester: fire on it (2 Ti for 2 dmg). Tracks `last_fire = (pos,
expected_hp)` so a future visit can detect enemy heals (current HP >
expected) — when detected, blacklist the tile for 5 turns and retreat
to an alternate attack spot. Cheap structural pressure; ranks first in
OFFENSE policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from builder.helpers import make_move, try_attack
from builder.tasks.offense_helpers import (
    is_allied_transport,
    pick_attack_destination,
    pick_harvester_target,
    should_attack,
    vulnerable_harvesters,
)
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNotOnEnemyTileError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "not standing on an enemy building"


class TaskRejectedOnAlliedTransportError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "standing on friendly transport — fire would break own chain"


class TaskRejectedNotAdjacentToHarvesterError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "not cardinally adjacent to a vulnerable harvester"


def fire_on_enemy_tile(self: Builder, ct: Controller) -> None:
    # Adjacent-to-vulnerable-harvester is the original guard: the
    # "fire on my tile" branch inside attack.py only runs inside the
    # `dist²(target) == 1` case after picking a vulnerable harvester.
    vulnerable = vulnerable_harvesters(self)
    if not vulnerable:
        raise TaskRejectedNotAdjacentToHarvesterError
    target = pick_harvester_target(self, vulnerable)
    if self.my_pos.distance_squared(target) != 1:
        raise TaskRejectedNotAdjacentToHarvesterError

    if is_allied_transport(self, self.my_pos):
        raise TaskRejectedOnAlliedTransportError
    if not self.is_enemy_building(self.my_pos):
        raise TaskRejectedNotOnEnemyTileError

    # Check for actual healing: if we stood here last turn and fired,
    # we know the HP we LEFT the tile at. If current HP > that, enemy
    # is healing. Blacklist and retreat to an alternate attack tile.
    being_healed = False
    match self.last_fire:
        case (self.my_pos, expected_hp):
            bid_here = ct.get_tile_building_id(self.my_pos)
            if bid_here is not None:
                current_hp = ct.get_hp(bid_here)
                if current_hp > expected_hp:
                    being_healed = True

    if being_healed:
        self.attack_tile_blacklist[self.my_pos] = 5
        self.last_fire = None
        alt = pick_attack_destination(self, target)
        if alt is not None and alt != self.my_pos:
            make_move(self, ct, alt)
        self.offense_target = self.my_pos
        self.offense_turns = 0
        return

    if not should_attack(self, self.my_pos):
        self.last_fire = None
        alt = pick_attack_destination(self, target)
        if alt is not None and alt != self.my_pos:
            make_move(self, ct, alt)
        self.offense_target = self.my_pos
        self.offense_turns = 0
        return

    bid_here = ct.get_tile_building_id(self.my_pos)
    if bid_here is not None:
        pre_hp = ct.get_hp(bid_here)
        self.last_fire = (self.my_pos, max(0, pre_hp - 2))
    try_attack(ct, self.my_pos)
    self.offense_target = self.my_pos
    self.offense_turns = 0
