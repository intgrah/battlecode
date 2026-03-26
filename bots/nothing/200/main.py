from cambc import Controller, EntityType, Position


class Player:
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() == EntityType.CORE and ct.get_current_round() >= 200:
            pos = ct.get_position()
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    p = Position(pos.x + dx, pos.y + dy)
                    bid = ct.get_tile_building_id(p)
                    if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
                        ct.destroy(p)
                        return
