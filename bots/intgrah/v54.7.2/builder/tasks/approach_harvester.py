"""Walk toward a vulnerable enemy harvester so a follow-up turn can fire
on it. Picks a cardinal-of-target destination via `pick_attack_destination`
(prefers no-healer, low-HP, close), optionally stages a launcher en route,
and walks via the launcher / cached `offense_target` / direct-to-target
cascade. Rejects when no vulnerable harvester exists or when we're already
adjacent (FIRE / TURRET tasks own the adjacent case).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingLauncher
from cambc import EntityType, GameConstants
from util.directions import DIR4
from util.metrics import closest

from builder.helpers import make_move, try_attack, try_place
from builder.tasks.offense_helpers import (
    buildable,
    is_allied_transport,
    open_tiles,
    pick_attack_destination,
    pick_harvester_target,
    should_attack,
    vulnerable_harvesters,
    without_allied_transport,
)
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNoVulnerableHarvesterError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no vulnerable enemy harvesters in vision"


class TaskRejectedAlreadyAdjacentError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "already adjacent to target (fire/turret task handles this)"


class TaskRejectedNoDestinationError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no walkable cardinal of target"


def approach_harvester(self: Builder, ct: Controller) -> None:
    vulnerable = vulnerable_harvesters(self)
    if not vulnerable:
        raise TaskRejectedNoVulnerableHarvesterError
    target = pick_harvester_target(self, vulnerable)

    # The "already adjacent, not on friendly conveyor" case is owned
    # by fire_on_enemy_tile / turret_around_harvester. If we'd handle
    # it here we'd double-handle; reject instead so those tasks fire
    # first at their own priority.
    on_friendly_conveyor = is_allied_transport(self, self.my_pos)
    if self.my_pos.distance_squared(target) == 1 and not on_friendly_conveyor:
        raise TaskRejectedAlreadyAdjacentError

    destination = pick_attack_destination(self, target, avoid_healers=False)
    if destination is None:
        # Original fallback: allow any walkable non-friendly-transport
        # cardinal. Covers cases where pick_attack_destination is too
        # strict.
        destination = closest(
            self.my_pos,
            without_allied_transport(
                self,
                open_tiles(self, [target.add(d) for d in DIR4]),
            ),
        )
        if destination is None:
            raise TaskRejectedNoDestinationError

    launcher_location = closest(
        destination,
        buildable(self, list(self.neighbours_8)),
    )
    adjacent_launchers = [
        p
        for p in self.neighbours_8
        if isinstance(self.get_building(p), BuildingLauncher)
    ]
    best_adjacent_launcher = closest(destination, adjacent_launchers)
    if (
        self.my_pos.distance_squared(destination) <= 2
        or self.my_pos.distance_squared(target) < 9
    ):
        make_move(self, ct, destination)
    elif (
        best_adjacent_launcher
        and self.is_walkable(destination)
        and best_adjacent_launcher.distance_squared(destination)
        <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
    ):
        pass
    elif (
        launcher_location
        and not best_adjacent_launcher
        and self.is_walkable(destination)
        and launcher_location.distance_squared(destination)
        <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
        and try_place(self, ct, EntityType.LAUNCHER, launcher_location)
    ):
        self.offense_launcher = launcher_location
    elif (
        self.offense_launcher
        and self.offense_launcher.distance_squared(self.my_pos) < 25
    ):
        make_move(self, ct, self.offense_launcher)
    elif self.offense_target and self.offense_target.distance_squared(self.my_pos) < 20:
        make_move(self, ct, self.offense_target)
    else:
        make_move(self, ct, target)

    # Post-step: if the move left us cardinal to target on an enemy
    # building, fire opportunistically. Preserves the `if (...)
    # try_attack(ct, ct.get_position())` tail of the original.
    if (
        ct.get_position().distance_squared(target) == 1
        and self.is_enemy_building(ct.get_position())
        and should_attack(self, ct.get_position())
    ):
        try_attack(ct, ct.get_position())
