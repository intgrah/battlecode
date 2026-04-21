from cambc import Controller, EntityType


class Player:
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() == EntityType.CORE:
            pos = ct.get_position()
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
