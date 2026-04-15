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


def can_place_junction(self: Builder, pos: Position) -> bool:
    match self.get_building(pos):
        case None:
            pass
        case BuildingConveyor(team=self.my_team) | BuildingRoad(team=self.my_team):
            pass
        case _:
            return False

    conv = self.get_conveyors_to_here(pos)
    conv_adj = [c for c in conv if c.distance_squared(pos) <= 2]
    if len(conv_adj) >= 2 or len(conv) == 0:
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
            case b if b.team == self.my_team:
                buildable_count += 1

    return buildable_count >= 1


def update_map_econ(self: Builder, ct: Controller) -> None:
    pad = self.pad
    pad_w = self.pad_w
    self.adjacent_to_unconnected_harvester = {
        p for p in self.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)
    }
    self.adjacent_to_harvester = {
        p for p in self.adjacent_to_harvester if not ct.is_in_vision(p)
    }
    for pos in self.nearby_positions:
        pi = (pos.y + pad) * pad_w + (pos.x + pad)
        bld = self.get_building(pos)
        match bld:
            case BuildingHarvester():
                adjacent_conveyor = False
                for d in DIR4:
                    match self.get_building(pos.add(d)):
                        case (
                            BuildingConveyor(team=self.my_team)
                            | BuildingBridge(team=self.my_team)
                            | BuildingSplitter(team=self.my_team)
                            | BuildingArmouredConveyor(team=self.my_team)
                        ):
                            adjacent_conveyor = True
                            break
                if not adjacent_conveyor:
                    for d in DIR4:
                        n = pos.add(d)
                        if self.in_bounds(n):
                            self.adjacent_to_unconnected_harvester.add(n)
                for d in DIR4:
                    n = pos.add(d)
                    if self.in_bounds(n):
                        self.adjacent_to_harvester.add(n)
        if pos in self.adjacent_to_enemy_launcher:
            self.cost_grid[pi] += 20
        if pos in self.enemy_turret_ray_tiles:
            self.cost_grid[pi] += 15

        match bld:
            case (
                BuildingConveyor(team=self.my_team)
                | BuildingArmouredConveyor(team=self.my_team)
                | BuildingSplitter(team=self.my_team)
                | BuildingBridge(team=self.my_team)
            ):
                i = pos.y * self.w + pos.x
                fh = self.flow_history[i]
                occupied = sum((fh >> s) & 0b11 != 0 for s in range(0, 16, 2))
                self.conveyor_cost_grid[pi] += _FLOW_PENALTY[occupied]

    if self.nearest_junction_site and not self.can_place_junction(
        self.nearest_junction_site,
    ):
        self.nearest_junction_site = None
    for pos in self.nearby_positions:
        if (
            self.nearest_junction_site is None
            or (
                self.nearest_junction_site.distance_squared(self.my_pos)
                < pos.distance_squared(self.my_pos)
            )
        ) and self.can_place_junction(pos):
            self.nearest_junction_site = pos


def update_dangling(self: Builder, ct: Controller) -> None:
    if is_dangling(self, self.my_pos):
        self.dangling_output = self.my_pos
    else:
        match self.get_building(self.my_pos):
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                target = self.my_pos.add(d)
                if is_dangling(self, target):
                    self.dangling_output = target
            case _:
                for d in DIR8:
                    n = self.my_pos.add(d)
                    if is_dangling(self, n):
                        self.dangling_output = n
                        break
    if self.pending_bridge:
        self.dangling_output = self.pending_bridge
    elif self.dangling_output is None or not is_dangling(self, self.dangling_output):
        self.dangling_output = find_dangling(self, ct)


def update_ore_target(self: Builder, ct: Controller) -> None:
    candidate_ore = pick_ore_target(self, ct)
    if (
        not self.ore_target
        or not ore_available(self, ct, self.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(self.my_pos) <= 2
            and self.ore_target.distance_squared(self.my_pos) > 2
        )
    ):
        self.ore_target = candidate_ore
