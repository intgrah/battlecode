"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/parasitic/approach_harvester.py`.

Walk toward a vulnerable enemy harvester so a follow-up turn can fire
on it. Picks a cardinal-of-target destination via `pick_attack_destination`
(prefers no-healer, low-HP, close), optionally stages a launcher en route,
and walks via the launcher / cached `offense_target` / direct-to-target
cascade.
"""

from __future__ import annotations

from cambc import EntityType, GameConstants
from util.directions import DIR4
from util.metrics import closest

from builder.helpers import make_move, try_attack, try_place
from builder.tasks.offense.helpers import (
    buildable,
    is_allied_transport,
    open_tiles,
    pick_attack_destination,
    pick_harvester_target,
    should_attack,
    vulnerable_harvesters,
    without_allied_transport,
)
from builder.tasks.rejected import TaskRejected


def approach_harvester(self_, ct):
    vulnerable = vulnerable_harvesters(self_)
    if not vulnerable:
        return TaskRejected("no vulnerable enemy harvesters in vision")
    target = pick_harvester_target(self_, vulnerable)
    on_friendly_conveyor = is_allied_transport(self_, self_.my_pos)
    if self_.my_pos.distance_squared(target) == 1 and not on_friendly_conveyor:
        return TaskRejected(
            "already adjacent to target (fire/turret task handles this)"
        )
    destination = pick_attack_destination(self_, target, False)
    if destination is None:
        cardinal_positions: list[object] = [target.add(d) for d in DIR4]
        opens = open_tiles(self_, cardinal_positions)
        filtered = without_allied_transport(self_, opens)
        destination = closest(self_.my_pos, filtered)
        if destination is None:
            return TaskRejected("no walkable cardinal of target")
    destination = destination
    neighbours_8 = list(self_.neighbours_8)
    buildable_8 = buildable(self_, neighbours_8)
    launcher_location = closest(destination, buildable_8)
    adjacent_launchers: list[object] = [
        p
        for p in self_.neighbours_8
        if self_.building_kind[self_.idx(p)] == EntityType.LAUNCHER
    ]
    best_adjacent_launcher = closest(destination, adjacent_launchers)
    if (
        self_.my_pos.distance_squared(destination) <= 2
        or self_.my_pos.distance_squared(target) < 9
    ):
        make_move(self_, ct, destination)
    else:
        bal = best_adjacent_launcher
        if (
            bal is not None
            and (self_.is_walkable(destination))
            and (
                bal.distance_squared(destination)
                <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
            )
        ):
            pass
        else:
            loc = launcher_location
            if (
                loc is not None
                and (best_adjacent_launcher is None)
                and (self_.is_walkable(destination))
                and (
                    loc.distance_squared(destination)
                    <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
                )
                and (try_place(self_, ct, EntityType.LAUNCHER, loc, None, True))
            ):
                self_.offense_launcher = loc
            else:
                ol = self_.offense_launcher
                if ol is not None and (ol.distance_squared(self_.my_pos) < 25):
                    make_move(self_, ct, ol)
                else:
                    ot = self_.offense_target
                    if ot is not None and (ot.distance_squared(self_.my_pos) < 20):
                        make_move(self_, ct, ot)
                    else:
                        make_move(self_, ct, target)
    cur_pos = ct.get_position(None)
    if (
        cur_pos.distance_squared(target) == 1
        and self_.is_enemy_building(cur_pos)
        and should_attack(self_, cur_pos)
    ):
        try_attack(ct, cur_pos)
    return None
