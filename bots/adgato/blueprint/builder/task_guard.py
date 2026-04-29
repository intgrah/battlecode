from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingBarrier,
    BuildingBreach,
    BuildingGunner,
    BuildingLauncher,
    BuildingSentinel,
)
from cambc import Controller, Direction, EntityType, Position, Team

from builder.helpers import make_move, try_place
from builder.role import Role

if TYPE_CHECKING:
    from builder import Builder


_ENTITY_BUILDING = {
    EntityType.BARRIER: BuildingBarrier,
    EntityType.GUNNER: BuildingGunner,
    EntityType.SENTINEL: BuildingSentinel,
    EntityType.BREACH: BuildingBreach,
    EntityType.LAUNCHER: BuildingLauncher,
}


def _plan(
    self: Builder,
) -> tuple[Position, tuple[tuple[EntityType, Position, Direction | None], ...]]:
    is_a = self.my_team == Team.A
    if self.role == Role.SOCKET_GUARD_1:
        if is_a:
            return Position(11, 16), ((EntityType.BARRIER, Position(12, 16), None),)
        return Position(11, 3), ((EntityType.BARRIER, Position(12, 3), None),)
    if self.role == Role.SOCKET_GUARD_2:
        if is_a:
            return Position(11, 17), ((EntityType.BARRIER, Position(12, 17), None),)
        return Position(11, 2), ((EntityType.BARRIER, Position(12, 2), None),)
    if self.role == Role.TILES_GUARD_1:
        if is_a:
            return Position(18, 4), ((EntityType.BARRIER, Position(18, 3), None),)
        return Position(18, 25), ((EntityType.BARRIER, Position(18, 26), None),)
    if self.role == Role.TILES_GUARD_2:
        if is_a:
            return Position(8, 10), ((EntityType.BARRIER, Position(8, 11), None),)
        return Position(8, 19), ((EntityType.BARRIER, Position(8, 18), None),)
    if self.role == Role.TILES_GUARD_3:
        if is_a:
            return Position(12, 10), ((EntityType.BARRIER, Position(12, 11), None),)
        return Position(12, 19), ((EntityType.BARRIER, Position(12, 18), None),)
    if self.role == Role.WINDOW_SHOPPING_GUARD:
        if is_a:
            return Position(15, 18), (
                (EntityType.BARRIER, Position(16, 18), None),
                (EntityType.GUNNER, Position(16, 19), Direction.EAST),
            )
        return Position(26, 18), (
            (EntityType.BARRIER, Position(25, 18), None),
            (EntityType.GUNNER, Position(25, 19), Direction.WEST),
        )
    raise AssertionError(self.role)


def run_guard(self: Builder, ct: Controller) -> bool:
    guard_pos, targets = _plan(self)

    if self.my_pos != guard_pos:
        make_move(self, ct, guard_pos)
        return True

    for etype, tpos, direction in targets:
        bld = self.get_building(tpos)
        expected_cls = _ENTITY_BUILDING[etype]
        need_place = (
            bld is None
            or not isinstance(bld, expected_cls)
            or bld.team != self.my_team
            or (direction is not None and getattr(bld, "direction", None) != direction)
        )
        if need_place:
            try_place(self, ct, etype, tpos, direction)
            return True
        b_id = ct.get_tile_building_id(tpos)
        if (
            b_id is not None
            and ct.get_hp(b_id) < ct.get_max_hp(b_id)
            and ct.can_heal(tpos)
        ):
            ct.heal(tpos)
            return True

    if ct.get_hp() < ct.get_max_hp() and ct.can_heal(self.my_pos):
        ct.heal(self.my_pos)
    return True
