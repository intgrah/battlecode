from cambc import *

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

DIRECTIONS_AND_C = [d for d in Direction]

DIRECTIONS_CARDINAL = [Direction.NORTH, Direction.EAST, Direction.WEST, Direction.SOUTH]

class Base:
    ct: Controller

    def __init__(self, ct: Controller):
        self.ct = ct
        self.id = -1
        self.team = ct.get_team()

        self.try_moved = False
        self.tiles = []
        self.parent_pos = None
        self.parent_id = None
        self.W = ct.get_map_width()
        self.H = ct.get_map_height()

        nearby = ct.get_nearby_entities()
        for e in nearby:
            if ct.get_team(e) == self.team and ct.get_entity_type(e) == EntityType.CORE:
                self.parent_pos = ct.get_position(e)
                self.parent_id = e
                break

    def is_inside(self, p: Position):
        return p.x >= 0 and p.y >= 0 and p.x < self.W and p.y < self.H

    def reset(self):
        self.id = self.ct.get_id()
        self.try_moved = False
        self.tiles = self.ct.get_nearby_tiles()
from base import *
import random

class Builder(Base):
    def __init__(self, ct):
        super().__init__(ct)

        self.explore_timer = -1
        self.explore_pos = Position(0, 0)

    def run(self, ct):
        self.ct = ct
        self.reset()

        self.try_build_harvester()
        self.repair()
        if self.suicide(): return
        self.support_ore()
        self.explore()

    def suicide(self):
        # suicide if we find a good attack square
        ct = self.ct
        me = ct.get_position()
        enemy = ct.get_tile_building_id(me)
        if enemy:
            if ct.get_team(enemy) != self.team:
                ct.self_destruct()
                return True

    def repair(self):
        # if our conveyor points to empty or enemy: fix it
        ct = self.ct
        best = []
        score = -1
        vision = ct.get_vision_radius_sq()
        me = ct.get_position()
        for t in self.tiles:
            bid = ct.get_tile_building_id(t)
            team = ct.get_team(bid)
            et = ct.get_entity_type(bid)
            if team == self.team and et == EntityType.CONVEYOR:
                cdir = ct.get_direction(bid)
                point = t.add(cdir)
                if point.distance_squared(me) < vision:
                    bid_point = ct.get_tile_building_id(point)
                    # bid_point should be one of our conveyors
                    s = -1e9

                    if bid_point is None:
                        s = 1000
                    elif ct.get_team(bid_point) != self.team:
                        s = 2000

                    s -= me.distance_squared(point)
                    if s > score:
                        score = s
                        best = [point]
                    elif s == score:
                        best.append(point)

        if len(best) > 0:
            loc = random.choice(best)
            ct.draw_indicator_dot(loc, 255, 255, 0)
            self.move_to(loc, 0)
            self.try_build_at(loc)

    def explore(self):
        ct = self.ct
        if self.try_moved:
            return
        if self.explore_timer < 0:
            self.explore_timer = 35
            self.explore_pos = Position(random.randrange(self.W), random.randrange(self.H))
        if ct.get_position().distance_squared(self.explore_pos) <= 5:
            self.explore_timer = -1
            self.explore()
        self.explore_timer -= 1
        ct.draw_indicator_line(ct.get_position(), self.explore_pos, 0, 255, 0)
        self.move_to(self.explore_pos)

    def support_ore(self):
        ct = self.ct
        tiles = ct.get_nearby_tiles()
        for t in tiles:
            env = ct.get_tile_env(t)
            if env.value[:3] == 'ore' and ct.get_tile_building_id(t) is None:
                ct.draw_indicator_line(ct.get_position(), t, 255, 0, 0)
                self.move_to(t)
                return

    def try_build_at(self, pos: Position):
        # build pointing towards base (best)
        # towards own position (ok)
        # towards own conveyors (may fail)
        # towards enemy conveyors (use roads at this point)
        ct = self.ct
        ct.draw_indicator_dot(pos, 255, 255, 255)
        ti, ax = ct.get_global_resources()
        if ti < 85 * ct.get_scale_percent() / 100.0 and ct.get_current_round() < 300:
            return
        cdirs = []
        score = -1
        me = ct.get_position()
        for c in DIRECTIONS_CARDINAL:
            if not ct.can_build_conveyor(pos, c):
                continue

            point = pos.add(c)
            bid = ct.get_tile_building_id(point) if self.is_inside(point) else None
            s = -1e9
            if bid is None:
                s = 1
            else:
                team = ct.get_team(bid)
                t = ct.get_entity_type(bid)
                if team == self.team:
                    if t == EntityType.CORE:
                        s = 5
                    elif t == EntityType.CONVEYOR:
                        if point == me:
                            s = 4
                        else:
                            s = 3
                    else:
                        s = 0
                else:
                    s = 0

            if s == score:
                cdirs.append(c)
            elif s > score:
                cdirs = [c]
                score = s

        if len(cdirs) > 0:
            if score == 0:
                ct.build_road(pos)
            else:
                ct.build_conveyor(pos, random.choice(cdirs))

    def move_to(self, pos, limit=2):
        if self.try_moved:
            return
        self.try_moved = True
        ct = self.ct
        me = ct.get_position()
        to = me.direction_to(pos)
        dirs = [
            to,
            to.rotate_left(),
            to.rotate_right(),
            to.rotate_left().rotate_left(),
            to.rotate_right().rotate_right(),
        ]
        if me.distance_squared(pos) <= limit: return
        for dir in dirs:
            if dir in DIRECTIONS_CARDINAL:
                self.try_build_at(me.add(dir))

                if ct.can_move(dir):
                    ct.move(dir)
                    return

    def try_build_harvester(self):
        ct = self.ct
        for d in DIRECTIONS:
            check_pos = ct.get_position().add(d)
            if ct.can_build_harvester(check_pos):
                ct.build_harvester(check_pos)
                return
from base import *
import random

class Core(Base):
    def __init__(self, ct):
        super().__init__(ct)

    def run(self, ct):
        self.ct = ct
        ti, ax = ct.get_global_resources()
        round = ct.get_current_round()
        if ti < (2.0 - round / 2000.0) * 220 * ct.get_scale_percent() / 100.0: return
        random.shuffle(DIRECTIONS)
        for d in DIRECTIONS:
            spawn_pos = ct.get_position().add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
from base import *

class Gunner(Base):
    def __init__(self, ct):
        super().__init__(ct)

    def run(self, ct):
        self.ct = ct
        self.reset()
from core import *
from builder import *
from gunner import *

class Player:
    def __init__(self):
        self.bot = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            if self.bot is None:
                self.bot = Core(ct)
        elif etype == EntityType.BUILDER_BOT:
            if self.bot is None:
                self.bot = Builder(ct)
        elif etype == EntityType.GUNNER:
            if self.bot is None:
                self.bot = Gunner(ct)
        self.bot.run(ct)
class Symmetry:
    def __init__(self, ct):
        self.ct = ct

    def run(self, ct):
        pass
