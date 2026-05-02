from __future__ import annotations

from cambc import EntityType, Environment
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from builder import Builder
from util.constants import INF, MAX_WIDTH
from util.directions import DIR4, DIR8

def update_ore_denial(builder):
    builder.deny_ore_neighbours = set()
    nearby = list(builder.state.nearby_tiles)
    my_team = builder.state.my_team
    for pos in nearby:
        env = builder.env[int(pos.y) * 50 + int(pos.x)]
        if env != Environment.ORE_TITANIUM and env != Environment.ORE_AXIONITE:
            continue
        has_enemy = False
        for d in DIR8:
            n = pos.add(d)
            if not builder.in_bounds(n):
                continue
            ni = int(n.y) * 50 + int(n.x)
            team = builder.building_team[ni]
            if team is not None and (team != my_team):
                has_enemy = True
                break
            if (n in builder.state.enemy_bots):
                has_enemy = True
                break
        if has_enemy:
            for d in DIR4:
                n = pos.add(d)
                if builder.in_bounds(n):
                    builder.deny_ore_neighbours.add(n)

def update_enemy_turrets(builder):
    my_team = builder.state.my_team
    t = builder.nearest_enemy_turret
    if t is not None:
        i = int(t.y) * 50 + int(t.x)
        valid = ((builder.building_kind[i] is not None) and (builder.building_kind[i] == EntityType.GUNNER or builder.building_kind[i] == EntityType.SENTINEL)) and builder.building_team[i] != my_team
        if not valid:
            builder.nearest_enemy_turret = None
    min_dist = 1000000
    nearby = list(builder.state.nearby_tiles)
    for pos in nearby:
        i = int(pos.y) * 50 + int(pos.x)
        is_enemy_turret = ((builder.building_kind[i] is not None) and (builder.building_kind[i] == EntityType.GUNNER or builder.building_kind[i] == EntityType.SENTINEL)) and builder.building_team[i] != my_team and (builder.building_team[i] is not None)
        if is_enemy_turret:
            dist = builder.state.my_pos.distance_squared(pos)
            if dist < min_dist:
                min_dist = dist
                builder.nearest_enemy_turret = pos
