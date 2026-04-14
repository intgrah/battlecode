from __future__ import annotations

from typing import TYPE_CHECKING

from building import BuildingGunner, BuildingSentinel
from cambc import Controller, Environment
from util import DIR4, DIR8, INF

if TYPE_CHECKING:
    from builder import Builder


def update_ore_denial(self: Builder, ct: Controller) -> None:
    w = self.w
    my_team = ct.get_team()
    self.deny_ore_neighbours = set()
    for pos in self.nearby_positions:
        env = self.env[pos.y * w + pos.x]
        if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            continue
        has_enemy = False
        for d in DIR8:
            n = pos.add(d)
            if not (0 <= n.x < self.w and 0 <= n.y < self.h):
                continue
            nb = self.buildings[n.y * w + n.x]
            if nb is not None and nb.team != my_team:
                has_enemy = True
                break
            if ct.is_in_vision(n):
                uid = ct.get_tile_builder_bot_id(n)
                if uid is not None and ct.get_team(uid) != my_team:
                    has_enemy = True
                    break
        if has_enemy:
            for d in DIR4:
                n = pos.add(d)
                if 0 <= n.x < self.w and 0 <= n.y < self.h:
                    self.deny_ore_neighbours.add(n)


def update_enemy_turrets(self: Builder, ct: Controller) -> None:
    w = self.w
    my_pos = ct.get_position()

    if self.nearest_enemy_turret:
        i = self.nearest_enemy_turret.y * w + self.nearest_enemy_turret.x
        match self.buildings[i]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != ct.get_team()
            ):
                pass
            case _:
                self.nearest_enemy_turret = None

    min_dist = INF
    for pos in self.nearby_positions:
        if not (0 <= pos.x < self.w and 0 <= pos.y < self.h):
            continue
        match self.buildings[pos.y * w + pos.x]:
            case BuildingGunner(team=t) | BuildingSentinel(team=t) if (
                t != ct.get_team()
            ):
                dist = (pos.x - my_pos.x) ** 2 + (pos.y - my_pos.y) ** 2
                if dist < min_dist:
                    min_dist = dist
                    self.nearest_enemy_turret = pos
