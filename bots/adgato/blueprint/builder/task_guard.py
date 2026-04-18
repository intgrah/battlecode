from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingBarrier
from cambc import Controller, EntityType, Position, Team

from builder.helpers import try_move_to, try_place
from builder.role import Role

if TYPE_CHECKING:
    from builder import Builder


def _posts(self: Builder) -> tuple[Position, Position]:
    if self.role == Role.SOCKET_GUARD_1:
        if self.my_team.value == 0:
            return Position(11, 16), Position(12, 16)
        return Position(11, 3), Position(12, 3)
    if self.role == Role.SOCKET_GUARD_2:
        if self.my_team.value == 0:
            return Position(11, 17), Position(12, 17)
        return Position(11, 2), Position(12, 2)
    if self.role == Role.TILES_GUARD_1:
        if self.my_team.value == 0:
            return Position(18, 4), Position(18, 3)
        return Position(18, 25), Position(18, 26)
    if self.role == Role.TILES_GUARD_2:
        if self.my_team.value == 0:
            return Position(8, 10), Position(8, 11)
        return Position(8, 19), Position(8, 18)
    if self.my_team.value == 0:
        return Position(12, 10), Position(12, 11)
    return Position(12, 19), Position(12, 18)


def run_guard(self: Builder, ct: Controller) -> bool:
    guard_pos, barrier_pos = _posts(self)

    if self.my_pos == guard_pos:
        bld = self.get_building(barrier_pos)
        if bld is None or not isinstance(bld, BuildingBarrier) or bld.team != self.my_team:
            try_place(self, ct, EntityType.BARRIER, barrier_pos)
            return True
        b_id = ct.get_tile_building_id(barrier_pos)
        if b_id is not None and ct.get_hp(b_id) < ct.get_max_hp(b_id) and ct.can_heal(barrier_pos):
            ct.heal(barrier_pos)
            return True
        if ct.get_hp() < ct.get_max_hp() and ct.can_heal(self.my_pos):
            ct.heal(self.my_pos)
            return True
        return True

    try_move_to(self, ct, guard_pos)
    return True
