"""Place gunner / sentinel turrets adjacent to a vulnerable enemy
harvester, capping at 2 gunners + 1 sentinel per harvester. Builder
must be on empty terrain at d²==1 of the harvester. Sequence: random
step-off (so the build tile is unblocked), pick chain-facing for the
gunner via `gunner_chain_facing` (ray must end on enemy transport),
sentinel facing toward enemy core, pave a road on the build tile, then
scout toward enemy. Atomic — one task call does all four steps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingGunner, BuildingSentinel
from cambc import EntityType, Environment
from util.directions import DIR4

from builder.helpers import move_random, try_place
from builder.tasks.offense.helpers import (
    gunner_chain_facing,
    is_allied_transport,
    pick_harvester_target,
    scout_toward_enemy,
    vulnerable_harvesters,
)
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


class TaskRejectedNotAdjacentEmptyError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "not on empty terrain cardinal to a vulnerable harvester"


def turret_around_harvester(self: Builder, ct: Controller) -> None:
    # Preconditions: standing on empty (non-enemy-building) terrain at
    # d²==1 of a vulnerable harvester, not on allied transport.
    vulnerable = vulnerable_harvesters(self)
    if not vulnerable:
        raise TaskRejectedNotAdjacentEmptyError
    target = pick_harvester_target(self, vulnerable)
    if self.my_pos.distance_squared(target) != 1:
        raise TaskRejectedNotAdjacentEmptyError
    if is_allied_transport(self, self.my_pos):
        raise TaskRejectedNotAdjacentEmptyError
    if self.is_enemy_building(self.my_pos):
        raise TaskRejectedNotAdjacentEmptyError

    # Preserve original's exact sequence:
    #   1. move_random() — required so we can place turrets on the tile
    #      we just vacated (ct.can_build rejects a tile with a builder
    #      standing on it).
    #   2. compute facing direction toward enemy_core, rotate right if
    #      that collides with direction-to-target.
    #   3. count existing gunners/sentinels cardinal to target.
    #   4. place gunner at build_position if caps allow and chain
    #      facing exists.
    #   5. place sentinel at build_position if caps allow and target is
    #      on Ti ore.
    #   6. pave build_position with a road if possible.
    #   7. scout_toward_enemy.
    build_position = self.my_pos
    enemy_core = self.en_core_guess
    move_random(self, ct)
    direction = build_position.direction_to(enemy_core)
    if direction == build_position.direction_to(target):
        direction = direction.rotate_right()

    n_gunner = 0
    n_sentinel = 0
    for d in DIR4:
        n = target.add(d)
        if not self.in_bounds(n):
            continue
        nb = self.get_building(n)
        if nb is None or nb.team != self.my_team:
            continue
        if isinstance(nb, BuildingGunner):
            n_gunner += 1
        elif isinstance(nb, BuildingSentinel):
            n_sentinel += 1

    if n_gunner < 2:
        gdir = gunner_chain_facing(self, build_position)
        if gdir is not None:
            try_place(self, ct, EntityType.GUNNER, build_position, gdir)

    if n_sentinel == 0 and self.get_env(target) == Environment.ORE_TITANIUM:
        try_place(self, ct, EntityType.SENTINEL, build_position, direction)

    if ct.can_build_road(build_position):
        ct.build_road(build_position)
    scout_toward_enemy(self, ct)
