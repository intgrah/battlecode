from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingHarvester,
    BuildingSplitter,
)
from cambc import ResourceType
from util.constants import FLOW_HISTORY_LEN, INF, MAX_WIDTH
from util.directions import DIR4

if TYPE_CHECKING:
    from builder import Builder


def update_patrol_queue(self: Builder) -> None:
    """Per-turn refresh of the defensive patrol target set.

    Two classes of targets:
      - friendly harvesters / foundries (high base score, structure to guard)
      - friendly transport tiles with observed flow in the recent window
        (lower base, weighted by Ti / Ax / RAx throughput)

    Both pick up a small bonus the closer they are to our core. Entries
    landed each turn carry the round they were last seen so
    `run_patrol`'s `(round - seen) * score` selection ages-out coverage.
    Pruning of in-vision entries happens earlier in `prune_stale`.
    """
    rnd = self.round
    my_team = self.my_team
    my_core = self.my_core

    for pos in self.nearby_tiles:
        i = pos.y * MAX_WIDTH + pos.x
        bld = self.buildings[i]
        if bld is None or bld.team != my_team:
            continue

        core_bonus = 0.0
        if my_core is not None:
            d = my_core.distance_squared(pos)
            core_bonus = max(0, 100 - d) / 100 * 0.25

        if isinstance(bld, BuildingHarvester | BuildingFoundry):
            # Harvesters and foundries are impassable buildings — bugnav
            # rejects them as a goal. Patrol an adjacent passable tile
            # instead (priority still reflects the building's value).
            target_pos = None
            best_cost = INF
            for d in DIR4:
                n = pos.add(d)
                if not self.in_bounds(n):
                    continue
                ni = n.y * MAX_WIDTH + n.x
                c = self.cost_grid[ni]
                if c < best_cost:
                    best_cost = c
                    target_pos = n
            if target_pos is None:
                continue
            self.patrol_queue.append((target_pos, rnd, 1.0 + core_bonus))
            continue

        if not isinstance(
            bld,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingBridge
            | BuildingSplitter,
        ):
            continue

        ti_n = 0
        ax_n = 0
        rax_n = 0
        for r, _rid in self.flow_history[i]:
            if r == ResourceType.TITANIUM:
                ti_n += 1
            elif r == ResourceType.RAW_AXIONITE:
                ax_n += 1
            elif r == ResourceType.REFINED_AXIONITE:
                rax_n += 1
        if ti_n == 0 and ax_n == 0 and rax_n == 0:
            continue

        ti_bonus = ti_n / FLOW_HISTORY_LEN * 0.25
        ax_bonus = ax_n / FLOW_HISTORY_LEN * 0.15
        rax_bonus = rax_n / FLOW_HISTORY_LEN * 0.35
        self.patrol_queue.append(
            (pos, rnd, 0.5 + ti_bonus + ax_bonus + rax_bonus + core_bonus),
        )
