"""Translation of `bots/intgrah/v54.7.9/sentinel/__init__.py`."""
from __future__ import annotations

from typing import Final

from unit import in_bounds
from cambc import Direction, EntityType, GameConstants
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position, Team
from unit import UnitState
SELF_DESTRUCT_THRESHOLD: Final[int] = 16

def is_enemy_combat(et):
    return (et == EntityType.CORE or et == EntityType.BREACH or et == EntityType.SENTINEL or et == EntityType.GUNNER or et == EntityType.LAUNCHER)

def is_transport(et):
    return (et == EntityType.CONVEYOR or et == EntityType.ARMOURED_CONVEYOR or et == EntityType.SPLITTER or et == EntityType.BRIDGE)

def priority(et):
    match et:
        case EntityType.SPLITTER:
            return 9
        case EntityType.BRIDGE:
            return 8
        case EntityType.BREACH:
            return 7
        case EntityType.SENTINEL:
            return 6
        case EntityType.GUNNER:
            return 5
        case EntityType.LAUNCHER:
            return 4
        case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR:
            return 3
        case EntityType.CORE | EntityType.FOUNDRY:
            return 2
        case EntityType.BARRIER | EntityType.ROAD:
            return 1
        case _:
            return 0

def rotate_right(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHEAST
        case Direction.NORTHEAST:
            return Direction.EAST
        case Direction.EAST:
            return Direction.SOUTHEAST
        case Direction.SOUTHEAST:
            return Direction.SOUTH
        case Direction.SOUTH:
            return Direction.SOUTHWEST
        case Direction.SOUTHWEST:
            return Direction.WEST
        case Direction.WEST:
            return Direction.NORTHWEST
        case Direction.NORTHWEST:
            return Direction.NORTH
        case Direction.CENTRE:
            return Direction.CENTRE

def rotate_left(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHWEST
        case Direction.NORTHEAST:
            return Direction.NORTH
        case Direction.EAST:
            return Direction.NORTHEAST
        case Direction.SOUTHEAST:
            return Direction.EAST
        case Direction.SOUTH:
            return Direction.SOUTHEAST
        case Direction.SOUTHWEST:
            return Direction.SOUTH
        case Direction.WEST:
            return Direction.SOUTHWEST
        case Direction.NORTHWEST:
            return Direction.WEST
        case Direction.CENTRE:
            return Direction.CENTRE

def _builder_score(hp):
    if hp <= GameConstants.SENTINEL_DAMAGE:
        return 15
    if hp < GameConstants.BUILDER_BOT_MAX_HP:
        return 7
    return 5

def _transport_outputs(ct, bid, pos, etype):
    if etype == EntityType.BRIDGE:
        return [ct.get_bridge_target(bid)]
    d = ct.get_direction(bid)
    if etype == EntityType.SPLITTER:
        return [pos.add(d), pos.add(rotate_right(rotate_right(d))), pos.add(rotate_left(rotate_left(d)))]
    return [pos.add(d)]

def _feeds_enemy_combat(ct, my_team, outputs):
    for out in outputs:
        if not ct.is_in_vision(out):
            continue
        out_bid = ct.get_tile_building_id(out)
        if out_bid is None:
            continue
        if ct.get_team(out_bid) == my_team:
            continue
        if is_enemy_combat(ct.get_entity_type(out_bid)):
            return True
    return False

class Sentinel:
    state: UnitState
    idle_turns: int

    def __init__(self):
        self.state = UnitState()
        self.idle_turns = 0

    def try_self_destruct(self, ct):
        my_team = self.state.my_team
        has_ally = False
        for uid in ct.get_nearby_units(None):
            if ct.get_team(uid) == my_team:
                has_ally = True
            else:
                return
        if has_ally:
            ct.self_destruct()

    def unit_state(self):
        return self.state

    def unit_state_mut(self):
        return self.state

    def run(self, ct):
        self.state.cache_per_turn_state(ct)
        self.state.check_symmetry_marker(ct)
        if ct.get_action_cooldown() > 0:
            return
        my_team = self.state.my_team
        best_score: int = -1
        best_target: Position | None = None
        attackable = ct.get_attackable_tiles()
        for tile in attackable:
            bid = ct.get_tile_building_id(tile)
            uid = self.state.all_bots.get(tile)
            if (tile in self.state.enemy_bots):
                hp = ct.get_hp(uid)
                score = _builder_score(hp)
                if score > best_score:
                    best_score = score
                    best_target = tile
                continue
            if (tile in self.state.friendly_bots):
                continue
            bid = bid
            if bid is None:
                continue
            if ct.get_team(bid) == my_team:
                continue
            etype = ct.get_entity_type(bid)
            if (etype == EntityType.MARKER or etype == EntityType.HARVESTER):
                continue
            score = priority(etype)
            if is_transport(etype):
                outputs = _transport_outputs(ct, bid, tile, etype)
                if _feeds_enemy_combat(ct, my_team, outputs):
                    score = 12
            if ct.get_hp(bid) <= GameConstants.SENTINEL_DAMAGE:
                score += 1
            if score > best_score:
                best_score = score
                best_target = tile
        target = best_target
        if target is not None and (ct.can_fire(target)):
            ct.fire(target)
            self.idle_turns = 0
        else:
            self.idle_turns += 1
            if self.idle_turns > 16:
                self.try_self_destruct(ct)

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
