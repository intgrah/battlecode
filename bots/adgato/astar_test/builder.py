"""Builder bot logic — A* pathfind to random targets."""

from __future__ import annotations

import random

from astar import COST_IMPASSABLE, NavAstar
from cambc import Controller, EntityType, Position
from symmetry import Symmetry, SymmetryDetector
from unit import Unit
from utils import try_move_smart


def _update_nearby_tiles(nav: NavAstar, sym: Symmetry, ct: Controller) -> None:
    """Read nearby tiles from the controller and feed raw data to nav."""
    w = nav.w
    my_id = ct.get_id()
    my_team = ct.get_team()
    nav.begin_update()
    for tile in ct.get_nearby_tiles():
        i = tile.y * w + tile.x
        env = ct.get_tile_env(tile)
        bid = ct.get_tile_building_id(tile)
        building_type = ct.get_entity_type(bid) if bid is not None else None
        is_allied = bid is not None and ct.get_team(bid) == my_team
        bbid = ct.get_tile_builder_bot_id(tile)
        is_builder = bbid is not None and bbid != my_id
        nav.update_tile(i, env, building_type, is_allied, is_builder, sym)


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()
        self.nav = NavAstar(w, h)
        self.sym: SymmetryDetector | None = None
        self.core_pos: Position | None = None
        self.target: Position | None = None
        self.w = w
        self.h = h

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()

        # Initialize symmetry detector once we know our core position
        if self.core_pos is None:
            my_team = ct.get_team()
            for tile in ct.get_nearby_tiles():
                bid = ct.get_tile_building_id(tile)
                if bid is not None and ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) == my_team:
                    self.core_pos = tile
                    self.sym = SymmetryDetector(self.w, self.h, tile)
                    break
            assert self.core_pos is not None

        # Run symmetry detection
        if self.sym.resolved is Symmetry.UNKNOWN:
            for tile in ct.get_nearby_tiles():
                self.sym.update(tile.y * self.w + tile.x, tile, ct.get_tile_env(tile))

        # Pick a new random target when needed
        if self.target is None or pos == self.target:
            self.target = Position(random.randint(0, self.w - 1), random.randint(0, self.h - 1))
        # Re-pick if target is known to be impassable
        cost = self.nav.get_cost(self.target)
        if cost is not None and cost >= COST_IMPASSABLE:
            self.target = Position(random.randint(0, self.w - 1), random.randint(0, self.h - 1))

        self.nav.set_goal(self.target)

        resolved = self.sym.resolved if self.sym is not None else Symmetry.UNKNOWN
        t0 = ct.get_cpu_time_elapsed()
        _update_nearby_tiles(self.nav, resolved, ct)
        t1 = ct.get_cpu_time_elapsed()
        next_pos = self.nav.step(pos, lambda: ct.get_cpu_time_elapsed() < 400)
        t2 = ct.get_cpu_time_elapsed()

        print(f"sym={resolved.name} enemy={self.sym.enemy_core}")
        print(f"update={t1 - t0}us step={t2 - t1}us total={t2 - t0}us")

        if next_pos is None:
            return

        direction = pos.direction_to(next_pos)
        try_move_smart(ct, pos, direction)

        ct.draw_indicator_line(ct.get_position(), self.target, 255, 0, 0)
        remaining = self.nav.get_remaining_path()
        if ct.get_id() == 3:
            for i in range(len(remaining) - 1):
                ct.draw_indicator_line(remaining[i], remaining[i + 1], 0, 255, 0)
