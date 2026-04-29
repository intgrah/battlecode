from cambc import Controller, EntityType, Position


class Player:
    def __init__(self) -> None:
        self.vandalised = False

    def run(self, ct: Controller) -> None:
        if not self.vandalised:
            try:
                delattr(Controller, "get_id")
                print(
                    f"[unit {ct.get_entity_type().name}] delattr(Controller, 'get_id') OK"
                )
            except Exception as e:
                print(f"[unit {ct.get_entity_type().name}] delattr failed: {e!r}")
            self.vandalised = True

        if ct.get_entity_type() == EntityType.CORE:
            pos = ct.get_position()
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    p = Position(pos.x + dx, pos.y + dy)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        return
