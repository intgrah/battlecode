"""Test launcher — dump tile state from launcher's perspective."""

import sys

from cambc import Controller, Direction, EntityType, Position


class Player:
    def __init__(self) -> None:
        self.phase = 0
        self.spawned = 0
        self.roads_built = 0
        self.dumped = False

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        rnd = ct.get_current_round()
        pos = ct.get_position()

        if etype == EntityType.CORE:
            if self.spawned == 0 and ct.get_action_cooldown() == 0:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        p = Position(pos.x + dx, pos.y + dy)
                        if ct.can_spawn(p):
                            ct.spawn_builder(p)
                            self.spawned = 1
                            return

        elif etype == EntityType.BUILDER_BOT:
            if self.phase == 0:
                if ct.get_move_cooldown() > 0 or ct.get_action_cooldown() > 0:
                    return
                for d in [
                    Direction.EAST,
                    Direction.SOUTH,
                    Direction.NORTH,
                    Direction.WEST,
                    Direction.SOUTHEAST,
                    Direction.SOUTHWEST,
                    Direction.NORTHEAST,
                    Direction.NORTHWEST,
                ]:
                    tp = pos.add(d)
                    if ct.can_build_road(tp):
                        ct.build_road(tp)
                        if ct.can_move(d):
                            ct.move(d)
                        self.roads_built += 1
                        if self.roads_built >= 5:
                            self.phase = 1
                        return
                    if ct.can_move(d):
                        ct.move(d)
                        self.roads_built += 1
                        if self.roads_built >= 5:
                            self.phase = 1
                        return
            elif self.phase == 1:
                if ct.get_action_cooldown() > 0:
                    return
                if ct.can_build_road(pos):
                    ct.build_road(pos)
                self.phase = 2
            elif self.phase == 2:
                if ct.get_action_cooldown() > 0:
                    return
                for d in Direction:
                    if d == Direction.CENTRE:
                        continue
                    lp = pos.add(d)
                    if ct.can_build_launcher(lp):
                        ct.build_launcher(lp)
                        print(f"L@{lp} bot@{pos}")
                        self.phase = 3
                        return

        elif etype == EntityType.LAUNCHER:
            if self.dumped:
                return
            my_team = ct.get_team()
            bot_pos = None
            for uid in ct.get_nearby_units():
                if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                    continue
                if ct.get_team(uid) != my_team:
                    continue
                bp = ct.get_position(uid)
                if bp.distance_squared(pos) <= 2:
                    bot_pos = bp
                    break
            if bot_pos is None:
                return

            self.dumped = True
            tiles = list(ct.get_nearby_tiles())
            print(f"nearby_tiles={len(tiles)} type={type(tiles[0])} first={tiles[0]}")
            for t in tiles:
                bid = ct.get_tile_building_id(t)
                if bid is None:
                    continue
                bt = ct.get_entity_type(bid)
                d2 = t.distance_squared(pos)
                cl = ct.can_launch(bot_pos, t)
                print(f"{t} d2={d2} {bt} cl={cl}", file=sys.stderr)

            n = sum(1 for t in tiles if ct.can_launch(bot_pos, t)) > 0
            print(
                f"R{rnd} bot_pos={bot_pos} can_launch={n} cooldown={ct.get_action_cooldown()}",
            )
