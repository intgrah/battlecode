from cambc import Controller, EntityType


class Player:
    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        pos = ct.get_position()
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if ti >= cost and ct.can_spawn(pos):
            ct.spawn_builder(pos)
            print(f"Spawned at centre ({pos.x},{pos.y})")
        else:
            print(f"Cannot spawn at centre ({pos.x},{pos.y}) can_spawn={ct.can_spawn(pos)} ti={ti} cost={cost}")
