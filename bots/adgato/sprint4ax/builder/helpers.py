from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingSplitter,
)
from cambc import Controller, EntityType, Position, Direction
from util import DIR4, DIR8, DELTA_TO_DIR, Symmetry, can_afford, try_move

from .algorithms.fallback_nav import fallback_nav

if TYPE_CHECKING:
    from builder import Builder, PosInt


def find_next(
    self: Builder, ct: Controller, start: PosInt, targets: list[PosInt]
) -> PosInt:
    pos = self.nav.search(ct, self.pos(start), [self.pos(p) for p in targets])
    if pos:
        return self._idx(pos)
    return -1


def make_move(self: Builder, ct: Controller, target: PosInt) -> bool:
    start = self.my_pos
    if start == target:
        return True

    next_step = find_next(self, ct, start, [target])
    if next_step < 0:
        fallback_pos = fallback_nav(self, ct, self.pos(target))
        if fallback_pos:
            next_step = self._idx(fallback_pos)
    if next_step:
        try_move_with_road(self, ct, next_step)
        return True
    return False


def make_multi_move(self: Builder, ct: Controller, targets: list[PosInt]) -> bool:
    start = self.my_pos

    next_step = find_next(self, ct, start, targets)
    if next_step < 0:
        fallback_pos = fallback_nav(self, ct, self.pos(targets[0]))
        if fallback_pos:
            next_step = self._idx(fallback_pos)
    if next_step:
        try_move_with_road(self, ct, next_step)
        return True
    return False


def try_move_with_road(self: Builder, ct: Controller, target_pos: PosInt) -> bool:
    if ct.can_build_road(self.pos(target_pos)):
        ct.build_road(self.pos(target_pos))
    return try_move(self, ct, target_pos)


def try_move_adj_to(self: Builder, ct: Controller, target_pos: PosInt) -> bool:
    """no road built"""
    my_pos = self.my_pos
    for d in DIR8:
        adj = my_pos + d
        if self.sq_dist(target_pos, adj) <= 2 and ct.can_move(DELTA_TO_DIR[d]):
            ct.move(DELTA_TO_DIR[d])
            self.my_pos += d
            return True

    return False


def try_attack(ct: Controller) -> bool:
    position = ct.get_position()
    if ct.can_fire(position):
        ct.fire(position)
        return True
    return False


def try_place(
    ct: Controller,
    etype: EntityType,
    pos: Position,
    extra: Direction | Position | None = None,
    *,
    destroy: bool = True,
) -> bool:
    if not can_afford(ct, etype):
        return False
    # Try without destroying first — if the tile is empty or
    # buildable already, no destruction needed.
    if ct.can_build(etype, pos, extra):
        ct.build(etype, pos, extra)
        return True
    # If building failed and we're allowed to destroy, clear the
    # tile and retry. This avoids the old bug where we'd destroy a
    # road then fail to build the replacement (wrong facing, etc.),
    # leaving the tile empty and causing road-rebuild thrashing.
    if destroy and ct.can_destroy(pos):
        ct.destroy(pos)
        if ct.can_build(etype, pos, extra):
            ct.build(etype, pos, extra)
            return True
    return False


def trace_downstream(
    self: Builder,
    start_pos: PosInt,
    target_head: PosInt | None,
    path: list[PosInt] | None = None,
) -> list[PosInt]:
    if path is None:
        path = []
    current_pos = start_pos
    while True:
        path.append(current_pos)
        bld = self.get_building(self._idx(current_pos))
        match bld:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                current_pos += d
            case BuildingSplitter(direction=d):
                for sd in DIR4:
                    if sd == -d:
                        continue
                    new_pos = current_pos + sd
                    if target_head:
                        new_path = trace_downstream(
                            self, new_pos, target_head, path=path[:]
                        )
                        if new_path and target_head in new_path:
                            return new_path
                    elif self.get_building(new_pos) is None:
                        path.append(new_pos)
                        return path
                current_pos += d
            case BuildingBridge(target=t):
                current_pos = t
            case _:
                break
        if current_pos in path:
            break
    return path


def try_heal(
    self: Builder,
    ct: Controller,
    i: PosInt,
    *,
    conserve_ti: bool = True,
    heal_score=0,
) -> bool:
    if conserve_ti and heal_score < 4:
        return False
    position = self.pos(i)
    if ct.can_heal(position):
        ct.heal(position)
        return True
    return False


def get_enemy_core_pos(self: Builder) -> PosInt:
    w, h = self.w, self.h
    cp = self.pos(self.my_core)
    candidates = self.symmetry_candidates

    if Symmetry.ROT in candidates:
        return self._idx(Position(w - 1 - cp.x, h - 1 - cp.y))
    if Symmetry.VER in candidates:
        return self._idx(Position(w - 1 - cp.x, cp.y))
    if Symmetry.HOR in candidates:
        return self._idx(Position(cp.x, h - 1 - cp.y))

    return self._idx(Position(w - 1 - cp.x, h - 1 - cp.y))


def move_random(self: Builder, ct: Controller) -> bool:
    dir8 = list(DIR8)
    self.rng.shuffle(dir8)
    for d in dir8:
        if ct.can_move(DELTA_TO_DIR[d]):
            ct.move(DELTA_TO_DIR[d])
            self.my_pos += d
            return True
    return False


def trace_upstream(self: Builder, position: PosInt) -> list[PosInt]:
    path: list[PosInt] = []
    conveyors = [position]
    while len(conveyors) > 0:
        position = conveyors[0]
        conveyors = self.get_conveyors_to_here(position)
        if position in path:
            break
        path.append(position)
    return path


def is_enemy_building(self: Builder, ct: Controller, pos: PosInt) -> bool:
    b = self.get_building(pos)
    return b is not None and b.team != self.my_team
