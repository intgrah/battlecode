from cambc import Controller, EntityType, Position


class Player:
    def run(self, ct: Controller) -> None:
        try:
            uid = ct.get_id()
            print(f"[victim {ct.get_entity_type().name}] get_id() = {uid}")
        except Exception as e:
            print(
                f"[victim {ct.get_entity_type().name}] get_id() raised {type(e).__name__}: {e}"
            )

        if ct.get_entity_type() == EntityType.CORE:
            pos = ct.get_position()
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    p = Position(pos.x + dx, pos.y + dy)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        return
