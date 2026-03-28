"""Builder bot logic — pathfind to the opposite side of the map, placing launchers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType, Position
from utils import pf_move

# One ring inside launcher action r²=26
_LAUNCHER_ACTION_R2 = 16


def run_builder(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    w = ct.get_map_width()
    h = ct.get_map_height()

    if player.core_pos is None:
        player.core_pos = pos

    # Set target to the opposite side of the map from core
    if player.target is None:
        core = player.core_pos
        player.target = Position(w - 1 - core.x, h - 1 - core.y)

    # Use core as initial reference point for the first launcher
    if player.last_launcher_pos is None:
        player.last_launcher_pos = player.core_pos

    # Once we step outside the last launcher's action range,
    # place a new launcher on the tile we were previously on
    if pos.distance_squared(player.last_launcher_pos) > _LAUNCHER_ACTION_R2:
        prev = player.prev_builder_pos
        if prev is not None:
            bid = ct.get_tile_building_id(prev)
            if bid is not None and ct.can_destroy(prev):
                ct.destroy(prev)
            if ct.can_build_launcher(prev):
                ct.build_launcher(prev)
                player.last_launcher_pos = prev
        player.prev_builder_pos = pos
        return

    player.prev_builder_pos = pos

    if pos == player.target:
        return

    player.walkable = set()
    pf_move(player, ct, player.target)
