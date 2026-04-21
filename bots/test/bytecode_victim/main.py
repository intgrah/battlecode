from cambc import Controller, EntityType, Position

SECRET_STRATEGY = 42


class Player:
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            pos = ct.get_position()
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    p = Position(pos.x + dx, pos.y + dy)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        return
