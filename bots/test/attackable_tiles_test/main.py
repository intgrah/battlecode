from cambc import Controller, Direction, EntityType


class Player:
    def __init__(self) -> None:
        pass

    def run(self, ct: Controller) -> None:
        match ct.get_entity_type():
            case EntityType.CORE:
                pos = ct.get_position()
                target = pos.add(Direction.SOUTH)
                if ct.can_spawn(target):
                    ct.spawn_builder(target)
            case EntityType.BUILDER_BOT:
                my_pos = ct.get_position()
                target = my_pos.add(Direction.SOUTH)
                if ct.can_build_sentinel(target, Direction.SOUTH):
                    ct.build_sentinel(target, Direction.SOUTH)
            case EntityType.SENTINEL:
                tiles = ct.get_attackable_tiles()
                pos = ct.get_position()
                direction = ct.get_direction()
                parts = [f"({t.x},{t.y})" for t in tiles]
                msg = f"pos=({pos.x},{pos.y}) dir={direction} count={len(tiles)} tiles={' '.join(parts)}"
                ct.resign(msg)
