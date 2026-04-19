from __future__ import annotations

from typing import TYPE_CHECKING, Final

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Environment, Position
from util.constants import INF, MAX_WIDTH
from util.directions import DIR4

from builder.helpers import find_dangling, is_dangling, ore_available, pick_ore_target

if TYPE_CHECKING:
    from builder import Builder


_FLOW_PENALTY: Final = (0, 0, 0, 0, 1, 3, 10, 50, 500)


def can_place_junction(self: Builder, pos: Position) -> bool:
    match self.get_building(pos):
        case (
            None | BuildingConveyor(team=self.my_team) | BuildingRoad(team=self.my_team)
        ):
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
        if not self.in_bounds(new_pos):
            continue
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
    self.adjacent_to_unconnected_harvester = {
        p for p in self.adjacent_to_unconnected_harvester if not ct.is_in_vision(p)
    }
    self.adjacent_to_harvester = {
        p for p in self.adjacent_to_harvester if not ct.is_in_vision(p)
    }
    for pos in self.nearby_tiles:
        i = pos.y * MAX_WIDTH + pos.x
        bld = self.get_building(pos)
        match bld:
            case BuildingHarvester():
                adjacent_conveyor = False
                for d in DIR4:
                    n = pos.add(d)
                    if not self.in_bounds(n):
                        continue
                    match self.get_building(n):
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
        if self.cost_grid[i] is not INF:
            if pos in self.adjacent_to_enemy_launcher:
                self.cost_grid[i] += 20
            if pos in self.enemy_turret_ray_tiles:
                self.cost_grid[i] += 15

        match bld:
            case (
                BuildingConveyor(team=self.my_team)
                | BuildingArmouredConveyor(team=self.my_team)
                | BuildingSplitter(team=self.my_team)
                | BuildingBridge(team=self.my_team)
            ):
                occupied = sum(r is not None for r in self.flow_history[i])
                self.conveyor_cost_grid[i] += _FLOW_PENALTY[occupied]


def update_dangling(self: Builder) -> None:
    if is_dangling(self, self.my_pos):
        self.dangling_output = self.my_pos
    else:
        match self.get_building(self.my_pos):
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                target = self.my_pos.add(d)
                if is_dangling(self, target):
                    self.dangling_output = target
            case _:
                for n in self.neighbours_8:
                    if is_dangling(self, n):
                        self.dangling_output = n
                        break
    if self.pending_bridge:
        self.dangling_output = self.pending_bridge
    elif self.dangling_output is None or not is_dangling(self, self.dangling_output):
        self.dangling_output = find_dangling(self)


def update_ore_target(self: Builder) -> None:
    candidate_ore = pick_ore_target(self)
    if (
        not self.ore_target
        or not ore_available(self, self.ore_target)
        or (
            candidate_ore
            and candidate_ore.distance_squared(self.my_pos) <= 2
            and self.ore_target.distance_squared(self.my_pos) > 2
        )
    ):
        self.ore_target = candidate_ore
