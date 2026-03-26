"""Launcher unit logic for trollbot — yeet enemy builders as far away as possible."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType
from utils import king_dist


def run_launcher(_player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    my_team = ct.get_team()

    print("running launcher")

    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) == my_team:
            continue
        bp = ct.get_position(uid)

        print(f"bot found at {bp}")
        best = None
        best_dist = 0
        for tile in ct.get_nearby_tiles():
            if not ct.can_launch(bp, tile):
                continue
            bid = ct.get_tile_building_id(tile)
            if bid is not None and ct.get_entity_type(bid) == EntityType.BRIDGE:
                continue
            d = king_dist(tile, pos)
            if d > best_dist:
                best_dist = d
                best = tile

        if best is not None:
            ct.launch(bp, best)
            return
