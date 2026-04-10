from cambc import Controller, Direction, EntityType


class Player:
    def __init__(self) -> None:
        self.done = False
        self.direction = Direction.NORTH

    def run(self, ct: Controller) -> None:
        match ct.get_entity_type():
            case EntityType.CORE:
                pos = ct.get_position()
                target = pos.add(Direction.NORTH)
                if ct.can_spawn(target):
                    ct.spawn_builder(target)
            case EntityType.BUILDER_BOT:
                if not self.done:
                    pos = ct.get_position()
                    target = pos.add(Direction.NORTH)
                    if ct.can_build(EntityType.GUNNER, target, Direction.NORTH):
                        ct.build(EntityType.GUNNER, target, Direction.NORTH)
                        self.done = True
            case EntityType.GUNNER:
                d = self.direction.rotate_right()
                if ct.can_rotate(d):
                    ct.rotate(d)
                    self.direction = d
