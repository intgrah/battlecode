from cambc import Controller, EntityType


class Player:
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() == EntityType.CORE and ct.get_current_round() >= 100:
            ct.destroy(ct.get_position())
