"""Translation of `bots/intgrah/v54.7.9/launcher/__init__.py`."""

from __future__ import annotations

from typing import Final

from unit import in_bounds
from cambc import EntityType, Environment, GameConstants
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position
from unit import UnitState
from util.directions import DIR4

PASSABLE_BUILDINGS: Final[list[EntityType]] = [
    EntityType.CONVEYOR,
    EntityType.ROAD,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.BRIDGE,
]


class Launcher:
    state: UnitState

    def __init__(self):
        self.state = UnitState()

    def is_empty_walkable(self, ct, pos):
        return self.is_walkable(ct, pos) and not (pos in self.state.all_bots)

    def is_walkable(self, ct, pos):
        if not self.in_bounds(pos) or not ct.is_in_vision(pos):
            return False
        if ct.get_tile_env(pos) == Environment.WALL:
            return False
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            return False
        et = ct.get_entity_type(bid)
        return et in PASSABLE_BUILDINGS

    def find_harvester_attack_tiles(self, ct):
        targets: list[Position] = []
        nearby = list(self.state.nearby_tiles)
        my_team = self.state.my_team
        for pos in nearby:
            bid = ct.get_tile_building_id(pos)
            if bid is None:
                continue
            if ct.get_entity_type(bid) != EntityType.HARVESTER:
                continue
            if ct.get_team(bid) == my_team:
                continue
            for d in DIR4:
                adj = pos.add(d)
                if not self.is_empty_walkable(ct, adj):
                    continue
                adj_bid = ct.get_tile_building_id(adj)
                if adj_bid is None:
                    continue
                if ct.get_team(adj_bid) == my_team:
                    continue
                targets.append(adj)
        return targets

    def find_enemy_throw_tile(self, ct):
        best: Position | None = None
        best_dist: int = 0
        nearby = list(self.state.nearby_tiles)
        my_team = self.state.my_team
        my_pos = self.state.my_pos
        for pos in nearby:
            bid = ct.get_tile_building_id(pos)
            if not self.is_empty_walkable(ct, pos):
                continue
            b = bid
            if b is not None and (ct.get_team(b) == my_team):
                continue
            dist = my_pos.distance_squared(pos)
            if dist > best_dist:
                best_dist = dist
                best = pos
        return (best, best_dist)

    def unit_state(self):
        return self.state

    def unit_state_mut(self):
        return self.state

    def run(self, ct):
        self.state.cache_per_turn_state(ct)
        self.state.check_symmetry_marker(ct)
        enemy_throw_tile, enemy_throw_dist = self.find_enemy_throw_tile(ct)
        harvester_targets = self.find_harvester_attack_tiles(ct)
        harvest_dest: Position | None = (
            harvester_targets[0] if harvester_targets else None
        )
        best_bot: Position | None = None
        best_dest: Position | None = None
        best_score: int = 0
        my_team = self.state.my_team
        for uid in ct.get_nearby_units(GameConstants.ACTION_RADIUS_SQ):
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            score: int = 0
            dest: Position | None = None
            team = ct.get_team(uid)
            if team == my_team:
                hd = harvest_dest
                if hd is not None:
                    score = 8
                    dest = hd
            else:
                et = enemy_throw_tile
                if et is not None:
                    score = enemy_throw_dist
                    dest = et
            if score > best_score:
                best_bot = ct.get_position(uid)
                best_dest = dest
                best_score = score
        bb = best_bot
        bd = best_dest
        if bb is not None and bd is not None and (ct.can_launch(bb, bd)):
            ct.launch(bb, bd)

    def post_init(self, ct):
        """
        ct-dependent init. Runs once on first turn for this unit. Mirrors
        Python `Unit.post_init`.
        """
        s = self.unit_state_mut()
        s.init_static_state(ct)
        s.narrow_symmetry_from_vision(ct)

    def idx(self, pos):
        """
        Position to flat index. Stride is `MAX_WIDTH=50` regardless of actual
        map size.
        """
        return int(pos.y) * 50 + int(pos.x)

    def in_bounds(self, pos):
        """Is in bounds of the actual map."""
        s = self.unit_state()
        return in_bounds(pos, s.width, s.height)
