import random

from cambc import Controller, Direction, EntityType


class Player:
    def __init__(self) -> None:
        self.round_no = 0
        self.spawned = 0
        self.msg = "GG"
        self.idx = 0

    def run(self, ct: Controller) -> None:
        self.round_no = ct.get_current_round()
        etype = ct.get_entity_type()

        if etype == EntityType.CORE:
            if self.spawned < 4 and ct.get_action_cooldown() == 0:
                pos = ct.get_position()
                for d in [
                    Direction.NORTH,
                    Direction.EAST,
                    Direction.SOUTH,
                    Direction.WEST,
                ]:
                    sp = pos.add(d)
                    if ct.can_spawn(sp):
                        ct.spawn_builder(sp)
                        self.spawned += 1
                        return

        elif etype == EntityType.BUILDER_BOT:
            pos = ct.get_position()
            # Place markers spelling out the message
            if ct.get_action_cooldown() == 0:
                char_val = ord(self.msg[self.idx % len(self.msg)])
                if ct.can_place_marker(pos):
                    ct.place_marker(pos, char_val)
                    self.idx += 1

            # Wander randomly
            if ct.get_move_cooldown() == 0:
                dirs = [
                    Direction.NORTH,
                    Direction.EAST,
                    Direction.SOUTH,
                    Direction.WEST,
                    Direction.NORTHEAST,
                    Direction.SOUTHEAST,
                    Direction.SOUTHWEST,
                    Direction.NORTHWEST,
                ]
                random.shuffle(dirs)
                for d in dirs:
                    if ct.can_move(d):
                        ct.move(d)
                        return
