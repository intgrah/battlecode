from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingGunner, BuildingSentinel
from cambc import Environment
from util.constants import INF, MAX_WIDTH
from util.directions import DIR4, DIR8

if TYPE_CHECKING:
    from builder import Builder


def update_ore_denial(self: Builder) -> None:
    self.deny_ore_neighbours = set()
    for pos in self.nearby_tiles:
        env = self.env[pos.y * MAX_WIDTH + pos.x]
        if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            continue
        has_enemy = False
        for d in DIR8:
            n = pos.add(d)
            if not self.in_bounds(n):
                continue
            nb = self.buildings[n.y * MAX_WIDTH + n.x]
            if nb is not None and nb.team != self.my_team:
                has_enemy = True
                break
            if n in self.enemy_bots:
                has_enemy = True
                break
        if has_enemy:
            for d in DIR4:
                n = pos.add(d)
                if self.in_bounds(n):
                    self.deny_ore_neighbours.add(n)


def update_enemy_turrets(self: Builder) -> None:
    if self.nearest_enemy_turret:
        i = self.nearest_enemy_turret.y * MAX_WIDTH + self.nearest_enemy_turret.x
        match self.buildings[i]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if t != self.my_team:
                pass
            case _:
                self.nearest_enemy_turret = None

    min_dist = INF
    for pos in self.nearby_tiles:
        match self.buildings[pos.y * MAX_WIDTH + pos.x]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if t != self.my_team:
                dist = self.my_pos.distance_squared(pos)
                if dist < min_dist:
                    min_dist = dist
                    self.nearest_enemy_turret = pos
