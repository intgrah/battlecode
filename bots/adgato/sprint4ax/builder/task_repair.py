from __future__ import annotations

from typing import TYPE_CHECKING

from building import *
from cambc import Controller, Environment
from util import closest

if TYPE_CHECKING:
    from builder import Builder, PosInt


def is_dangling(self: Builder, ct: Controller, pos: PosInt) -> bool:

    i = pos
    if not self.in_bounds(i):
        return False

    b = self.buildings[i]
    if b is None:
        if self.env[i] == Environment.WALL:
            return False
    else:
        if b.team != self.my_team:
            return False

        match b:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                adj = pos + d
                if self.in_bounds(adj):
                    j = adj
                    c = self.buildings[j]
                    if c is None:
                        if self.env[j] != Environment.WALL:
                            return False
                    elif c.team == self.my_team:
                        match c:
                            case (
                                BuildingBarrier()
                                | BuildingLauncher()
                                | BuildingHarvester()
                            ):
                                pass
                            case (
                                BuildingConveyor(direction=d2)
                                | BuildingArmouredConveyor(direction=d2)
                            ) if d == -d2:
                                pass
                            case _:
                                return False
            case BuildingRoad():
                pass
            case _:
                return False

    
    return any(self.conveyors_to_here[j] or j in self.adjacent_to_harvester for j in self.conveyors_to_here[i]) or pos in self.adjacent_to_unconnected_harvester


def is_valid_loose_end_target(self: Builder, ct: Controller, pos: PosInt) -> bool:
    if not is_dangling(self, ct, pos):
        return False

    my_id = self.my_id
    if ct.is_in_vision(self.pos(pos)):
        bid = ct.get_tile_builder_bot_id(self.pos(pos))
        friendly = ct.get_team(bid) == self.my_team
        if bid is not None and bid != my_id and friendly:
            return False

    leading = self.get_conveyors_to_here(pos)
    for lpos in leading:
        if not ct.is_in_vision(self.pos(lpos)):
            continue
        lbid = ct.get_tile_builder_bot_id(self.pos(lpos))
        friendly = ct.get_team(lbid) == self.my_team
        if lbid is not None and lbid != my_id and friendly:
            return False
    return True


def find_dangling(self: Builder, ct: Controller) -> PosInt:

    nearby = ct.get_nearby_tiles()

    candidates = [self._idx(pos) for pos in nearby if is_valid_loose_end_target(self, ct, self._idx(pos))]

    if not candidates:
        return -1

    my_pos = self.my_pos
    return closest(self, my_pos, candidates)
