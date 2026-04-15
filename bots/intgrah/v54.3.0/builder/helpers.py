from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from util import DIR4, DIR8, INF, Symmetry, can_afford, closest, try_move

from builder.algorithms.astar import pathfind_blocked
from builder.algorithms.bugnav import bugnav

if TYPE_CHECKING:
    from builder import Builder


def make_move(self: Builder, ct: Controller, target: Position) -> bool:
    if self.my_pos == target:
        return True

    path = pathfind_blocked(self, ct, self.my_pos, target)
    if path is not None and len(path) > 1:
        next_step = path[1]
        try_move_with_road(self, ct, next_step)
        return True
    next_move = bugnav(self, ct, target)
    if next_move:
        try_move_with_road(self, ct, next_move)
        return True
    return False


def try_move_with_road(self: Builder, ct: Controller, target_pos: Position) -> bool:
    if self.get_cost(target_pos) > 1 and ct.can_build_road(target_pos):
        ct.build_road(target_pos)
    return try_move(ct, target_pos)


def try_attack(ct: Controller, pos: Position) -> bool:
    if ct.can_fire(pos):
        ct.fire(pos)
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
    if destroy and ct.can_destroy(pos):
        ct.destroy(pos)
    if ct.can_build(etype, pos, extra):
        ct.build(etype, pos, extra)
        return True
    return False


def trace_downstream(
    self: Builder,
    start_pos: Position,
    target_head: Position | None,
    path: list[Position] | None = None,
) -> list[Position]:
    if path is None:
        path = []
    current_pos = start_pos
    while True:
        path.append(current_pos)
        bld = self.get_building(current_pos)
        match bld:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                current_pos = current_pos.add(d)
            case BuildingSplitter(direction=d):
                for sd in DIR4:
                    if sd == d.opposite():
                        continue
                    new_pos = current_pos.add(sd)
                    if target_head:
                        new_path = trace_downstream(
                            self,
                            new_pos,
                            target_head,
                            path=path.copy(),
                        )
                        if new_path and target_head in new_path:
                            return new_path
                    elif self.get_building(new_pos) is None:
                        path.append(new_pos)
                        return path
                current_pos = current_pos.add(d)
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
    position: Position,
    *,
    conserve_ti: bool = True,
) -> bool:
    if conserve_ti and self.repair_pos is not None:
        i = self.idx(self.repair_pos)
        if not self.buildings[i] or self.hp[i] > self.max_hp[i] - 4:
            return False
    if ct.can_heal(position):
        ct.heal(position)
        return True
    return False


def get_enemy_core_pos(self: Builder) -> Position:
    w, h = self.w, self.h
    cp = self.my_core
    candidates = self.symmetry_candidates

    if Symmetry.ROT in candidates:
        return Position(w - 1 - cp.x, h - 1 - cp.y)
    if Symmetry.VER in candidates:
        return Position(w - 1 - cp.x, cp.y)
    if Symmetry.HOR in candidates:
        return Position(cp.x, h - 1 - cp.y)

    return Position(w - 1 - cp.x, h - 1 - cp.y)


def move_random(self: Builder, ct: Controller) -> bool:
    dir8 = DIR8.copy()
    self.rng.shuffle(dir8)
    for direction in dir8:
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


def trace_upstream(self: Builder, position: Position) -> list[Position]:
    path: list[Position] = []
    conveyors = [position]
    while len(conveyors) > 0:
        position = conveyors[0]
        conveyors = self.get_conveyors_to_here(position)
        if position in path:
            break
        path.append(position)
    return path


def ore_available(self: Builder, ct: Controller, pos: Position) -> bool:
    b = self.get_building(pos)
    if b is not None and not isinstance(b, BuildingRoad):
        return False
    if ct.is_in_vision(pos):
        worker_id = ct.get_tile_builder_bot_id(pos)
        if worker_id is not None and worker_id != self.my_id:
            return False
    return True


def pick_ore_target(self: Builder, ct: Controller) -> Position | None:
    best_target = None
    min_dist = INF
    for pos in ct.get_nearby_tiles():
        terrain = self.get_env(pos)
        if terrain == Environment.ORE_TITANIUM:
            match self.get_building(pos):
                case BuildingHarvester():
                    continue
                case None | BuildingRoad():
                    pass
                case _:
                    continue
            d = self.bfs_dist[pos.y * self.w + pos.x]
            if d >= INF:
                continue
            if ore_available(self, ct, pos) and d < min_dist:
                min_dist = d
                best_target = pos
    return best_target


def is_dangling(self: Builder, pos: Position) -> bool:
    if not self.in_bounds(pos):
        return False
    i = pos.y * self.w + pos.x
    b = self.buildings[i]
    if b is None:
        if self.env[i] == Environment.WALL:
            return False
    elif not isinstance(b, BuildingRoad) or b.team != self.my_team:
        return False
    if self.conveyors_to_here[i]:
        return True
    return pos in self.adjacent_to_unconnected_harvester


def is_valid_loose_end_target(self: Builder, ct: Controller, pos: Position) -> bool:
    if not is_dangling(self, pos):
        return False
    if ct.is_in_vision(pos):
        bid = ct.get_tile_builder_bot_id(pos)
        friendly = ct.get_team(bid) == self.my_team
        if bid is not None and bid != self.my_id and friendly:
            return False
    leading = self.get_conveyors_to_here(pos)
    for lpos in leading:
        if not ct.is_in_vision(lpos):
            continue
        lbid = ct.get_tile_builder_bot_id(lpos)
        friendly = ct.get_team(lbid) == self.my_team
        if lbid is not None and lbid != self.my_id and friendly:
            return False
    return True


def find_dangling(self: Builder, ct: Controller) -> Position | None:
    w = self.w
    candidates = [
        pos
        for pos in ct.get_nearby_tiles()
        if is_valid_loose_end_target(self, ct, pos)
        and self.bfs_dist[pos.y * w + pos.x] < INF
    ]
    if not candidates:
        return None
    return closest(self.my_pos, candidates)
