"""Gunner turret logic for v6."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller
    from main import Player


def run_gunner(_player: Player, ct: Controller) -> None:
    """Fire only at tiles containing enemy buildings or units."""
    my_team = ct.get_team()

    for tile in ct.get_nearby_tiles():
        if not ct.can_fire(tile):
            continue
        bid = ct.get_tile_building_id(tile)
        uid = ct.get_tile_builder_bot_id(tile)
        has_enemy = False
        if bid is not None and ct.get_team(bid) != my_team:
            has_enemy = True
        if uid is not None and ct.get_team(uid) != my_team:
            has_enemy = True
        if has_enemy:
            ct.fire(tile)
            return
