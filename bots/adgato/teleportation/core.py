"""Core unit logic — spawn one builder bot, then place markers near launchers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType, Position

# Launcher action r²=26
_LAUNCHER_ACTION_R2 = 26


def run_core(player: Player, ct: Controller) -> None:
    pos = ct.get_position()

    if player.core_pos is None:
        player.core_pos = pos

    if player.spawned < 1:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    player.spawned += 1
                    return

    # Find nearest friendly launcher
    my_team = ct.get_team()
    best_launcher = None
    best_dist = float("inf")
    for bid in ct.get_nearby_buildings():
        if (
            ct.get_entity_type(bid) != EntityType.LAUNCHER
            or ct.get_team(bid) != my_team
        ):
            continue
        lp = ct.get_position(bid)
        d = pos.distance_squared(lp)
        if d < best_dist:
            best_dist = d
            best_launcher = lp

    if best_launcher is None:
        return

    # Place a marker on a tile within the launcher's action range
    rnd = ct.get_current_round()
    for tile in ct.get_nearby_tiles():
        if tile.distance_squared(
            best_launcher,
        ) <= _LAUNCHER_ACTION_R2 and ct.can_place_marker(tile):
            ct.place_marker(tile, rnd)
            return
