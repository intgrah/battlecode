from cambc import Controller, EntityType
from unit import Unit


class Launcher(Unit):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

        for uid in ct.get_nearby_units():
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(uid) == my_team:
                continue
            bp = ct.get_position(uid)
            if bp.distance_squared(pos) > 2:
                continue

            best = None
            best_dist = 0
            for tile in ct.get_nearby_tiles():
                if not ct.can_launch(bp, tile):
                    continue
                bid = ct.get_tile_building_id(tile)
                if bid is not None and ct.get_entity_type(bid) == EntityType.BRIDGE:
                    continue
                d = max(abs(tile.x - pos.x), abs(tile.y - pos.y))
                if d > best_dist:
                    best_dist = d
                    best = tile

            if best is not None:
                ct.launch(bp, best)
            return
