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
from cambc import Controller, Environment, Position
from util import DIR4, DIR8

from builder.helpers import find_dangling, is_dangling, ore_available, pick_ore_target

if TYPE_CHECKING:
    from builder import Builder


_FLOW_PENALTY = (0, 0, 0, 0, 1, 3, 10, 50, 500)


def can_place_junction(self: Builder, ct: Controller, pos: Position) -> bool:
    match self.get_building(pos):
        case None:
            pass
        case BuildingConveyor(team=t) | BuildingRoad(team=t) if t == ct.get_team():
            pass
        case _:
            return False

    conv = self.get_conveyors_to_here(pos)
    adj_conv = [c for c in conv if c.distance_squared(pos) <= 2]
    if len(adj_conv) >= 2 or len(conv) == 0:
        return False
    buildable_count = 0
    for d in DIR4:
        new_pos = pos.add(d)
        if self.get_env(new_pos) != Environment.EMPTY:
            continue
        match self.get_building(new_pos):
            case None:
                buildable_count += 1
            case BuildingConveyor() | BuildingBridge() | BuildingSplitter():
                pass
            case b if b.team == ct.get_team():
                buildable_count += 1

    return buildable_count >= 1


def update_map_econ(self: Builder, ct: Controller) -> None:
    pad = self.pad
    pw = self.pw
    self.adjacent_to_unconnected_harvester = {
        p for p in self.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)
    }
    self.adjacent_to_harvester = {
        p for p in self.adjacent_to_harvester if not ct.is_in_vision(p)
    }
    my_team = ct.get_team()
    for pos in self.nearby_positions:
        if not (0 <= pos.x < self.w and 0 <= pos.y < self.h):
            continue
        pi = (pos.y + pad) * pw + (pos.x + pad)
        bld = self.get_building(pos)
        match bld:
            case BuildingHarvester():
                adjacent_conveyor = False
                for d in DIR4:
                    match self.get_building(pos.add(d)):
                        case (
                            BuildingConveyor(team=t)
                            | BuildingBridge(team=t)
                            | BuildingSplitter(team=t)
                            | BuildingArmouredConveyor(team=t)
                        ) if t == my_team:
                            adjacent_conveyor = True
                            break
                if not adjacent_conveyor:
                    for d in DIR4:
                        n = pos.add(d)
                        if 0 <= n.x < self.w and 0 <= n.y < self.h:
                            self.adjacent_to_unconnected_harvester.add(n)
                for d in DIR4:
                    n = pos.add(d)
                    if 0 <= n.x < self.w and 0 <= n.y < self.h:
                        self.adjacent_to_harvester.add(n)
        if pos in self.adjacent_to_enemy_launcher:
            self.cost_grid[pi] += 20
        if pos in self.enemy_turret_ray_tiles:
            self.cost_grid[pi] += 15

        match bld:
            case (
                BuildingConveyor(team=t)
                | BuildingArmouredConveyor(team=t)
                | BuildingSplitter(team=t)
                | BuildingBridge(team=t)
            ) if t == my_team:
                i = pos.y * self.w + pos.x
                fh = self.flow_history[i]
                occupied = sum((fh >> s) & 0b11 != 0 for s in range(0, 16, 2))
                self.conveyor_cost_grid[pi] += _FLOW_PENALTY[occupied]

    my_position = ct.get_position()
    if self.nearest_junction_site and not can_place_junction(
        self,
        ct,
        self.nearest_junction_site,
    ):
        self.nearest_junction_site = None
    for pos in self.nearby_positions:
        if not (0 <= pos.x < self.w and 0 <= pos.y < self.h):
            continue
        if (
            self.nearest_junction_site is None
            or (
                self.nearest_junction_site.distance_squared(my_position)
                < pos.distance_squared(my_position)
            )
        ) and can_place_junction(self, ct, pos):
            self.nearest_junction_site = pos


def update_dangling(self: Builder, ct: Controller) -> None:
    my_pos = ct.get_position()
    if is_dangling(self, ct, my_pos):
        self.dangling_output = my_pos
    else:
        match self.get_building(my_pos):
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                target = my_pos.add(d)
                if is_dangling(self, ct, target):
                    self.dangling_output = target
            case _:
                for d in DIR8:
                    n = my_pos.add(d)
                    if is_dangling(self, ct, n):
                        self.dangling_output = n
                        break
    if self.pending_bridge:
        self.dangling_output = self.pending_bridge
    elif self.dangling_output is None or not is_dangling(
        self,
        ct,
        self.dangling_output,
    ):
        self.dangling_output = find_dangling(self, ct)


def update_ore_target(self: Builder, ct: Controller) -> None:
    my_pos = ct.get_position()
    candidate_ore = pick_ore_target(self, ct)
    if (
        not self.ore_target
        or not ore_available(self, ct, self.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(my_pos) <= 2
            and self.ore_target.distance_squared(my_pos) > 2
        )
    ):
        self.ore_target = candidate_ore
