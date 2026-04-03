"""Heal damaged friendly buildings and self.

Priority: self (if low HP) > turrets > harvesters > transport.
Turrets are expensive to replace, harvesters are critical for econ,
transport can be rebuilt by connect_excess.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, EntityType, GameConstants, Position

from .action import Action, Heal
from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .state import State

_TURRET_TYPES = frozenset((
    EntityType.GUNNER,
    EntityType.SENTINEL,
    EntityType.BREACH,
    EntityType.LAUNCHER,
))

_TRANSPORT_TYPES = frozenset((
    EntityType.CONVEYOR,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.SPLITTER,
    EntityType.BRIDGE,
))


def heal(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos

    # Self-heal if missing 4+ HP (heal restores 4 per action)
    hp = ct.get_hp()
    max_hp = ct.get_max_hp()
    if max_hp - hp >= 4 and ct.can_heal(pos):
        return Direction.CENTRE, Heal(pos)

    # Find best damaged friendly building to heal
    target = _find_heal_target(ct)
    if target is None:
        return None

    if pos.distance_squared(target) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(target):
        return Direction.CENTRE, Heal(target)

    result = move_toward_with_road(state, ct, target)
    if result is None:
        return None
    move, build = result
    # Heal immediately if we arrive adjacent
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(target) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(target):
            build = Heal(target)
    return move, build


def _find_heal_target(ct: Controller) -> Position | None:
    my_team = ct.get_team()
    best: Position | None = None
    best_priority = -1
    best_hp_frac = 1.0

    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != my_team:
            continue
        hp = ct.get_hp(bid)
        max_hp = ct.get_max_hp(bid)
        if hp >= max_hp:
            continue

        etype = ct.get_entity_type(bid)
        if etype in _TURRET_TYPES:
            priority = 3
        elif etype == EntityType.HARVESTER:
            priority = 2
        elif etype in _TRANSPORT_TYPES:
            priority = 1
        else:
            continue

        frac = hp / max_hp
        if priority > best_priority or (priority == best_priority and frac < best_hp_frac):
            best_priority = priority
            best_hp_frac = frac
            best = ct.get_position(bid)

    return best
