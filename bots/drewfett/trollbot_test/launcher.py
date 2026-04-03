"""Launcher unit logic for trollbot — yeet enemy builders as far away as possible."""

from cambc import Controller, EntityType
from utils import king_dist


def run_launcher(player, ct: Controller) -> None:
    pos = ct.get_position()
    my_team = ct.get_team()

    # try throw off bridge first
    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) == my_team:
            continue
        bp = ct.get_position(uid)

        bid = ct.get_tile_building_id(bp)
        if bid is None or ct.get_entity_type(bid) != EntityType.BRIDGE:
            continue

        print(f"bot found on bridge at {bp}")
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

    # try throw any away second
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
