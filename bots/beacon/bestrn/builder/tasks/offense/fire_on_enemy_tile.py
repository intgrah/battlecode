"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/fire_on_enemy_tile.py`.

Standing on an enemy building cardinal to a vulnerable enemy
harvester: fire on it (2 Ti for 2 dmg). Tracks `last_fire = (pos,
expected_hp)` so a future visit can detect enemy heals.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import make_move, try_attack
from builder.tasks.offense.helpers import is_allied_transport, pick_attack_destination, pick_harvester_target, should_attack, vulnerable_harvesters
from builder.tasks.rejected import TaskRejected
if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult

def fire_on_enemy_tile(self_, ct):
    vulnerable = vulnerable_harvesters(self_)
    if (not vulnerable):
        return TaskRejected("not cardinally adjacent to a vulnerable harvester")
    target = pick_harvester_target(self_, vulnerable)
    if self_.my_pos.distance_squared(target) != 1:
        return TaskRejected("not cardinally adjacent to a vulnerable harvester")
    if is_allied_transport(self_, self_.my_pos):
        return TaskRejected("standing on friendly transport — fire would break own chain")
    if not self_.is_enemy_building(self_.my_pos):
        return TaskRejected("not standing on an enemy building")
    being_healed = False
    __opt_pos_expected_hp = self_.last_fire
    pos = __opt_pos_expected_hp[0] if __opt_pos_expected_hp is not None else None
    expected_hp = __opt_pos_expected_hp[1] if __opt_pos_expected_hp is not None else None
    if __opt_pos_expected_hp is not None and (pos == self_.my_pos):
        bid_here = ct.get_tile_building_id(self_.my_pos)
        bid = bid_here
        if bid is not None:
            current_hp = ct.get_hp(bid)
            if current_hp > expected_hp:
                being_healed = True
    my_pos = self_.my_pos
    if being_healed:
        self_.attack_tile_blacklist[my_pos] = 5
        self_.last_fire = None
        alt = pick_attack_destination(self_, target, True)
        a = alt
        if a is not None and (a != my_pos):
            make_move(self_, ct, a)
        self_.offense_target = my_pos
        self_.offense_turns = 0
        return None
    if not should_attack(self_, my_pos):
        self_.last_fire = None
        alt = pick_attack_destination(self_, target, True)
        a = alt
        if a is not None and (a != my_pos):
            make_move(self_, ct, a)
        self_.offense_target = my_pos
        self_.offense_turns = 0
        return None
    bid_here = ct.get_tile_building_id(my_pos)
    bid = bid_here
    if bid is not None:
        pre_hp = ct.get_hp(bid)
        self_.last_fire = (my_pos, max(pre_hp - 2, 0))
    try_attack(ct, my_pos)
    self_.offense_target = my_pos
    self_.offense_turns = 0
    return None
