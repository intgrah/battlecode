"""Heal a damaged friendly bridge.

Navigates to the nearest damaged friendly bridge and heals it.
This mirrors trollbot_expand's behavior of prioritizing bridge
healing to maintain the transport network.
"""

from cambc import Controller, Direction, EntityType, Position
from util import INF

from .build import Action, Heal
from .helpers import move_toward_with_road
from .state import State


def find_damaged_bridge(ct: Controller) -> Position | None:
    """Find nearest damaged friendly bridge visible to this builder."""
    my_team = ct.get_team()
    pos = ct.get_position()
    best: Position | None = None
    best_dist = INF

    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.BRIDGE:
            continue
        if ct.get_team(bid) != my_team:
            continue
        if ct.get_hp(bid) >= ct.get_max_hp(bid):
            continue
        bp = ct.get_position(bid)
        # Skip if another builder is already adjacent/on it
        other = ct.get_tile_builder_bot_id(bp)
        if other is not None and other != ct.get_id():
            continue
        dist = abs(pos.x - bp.x) + abs(pos.y - bp.y)
        if dist < best_dist:
            best_dist = dist
            best = bp

    return best


def heal_bridge(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Navigate to damaged bridge and heal it."""
    target = find_damaged_bridge(ct)
    if target is None:
        return None

    # If we can heal from current position, do so
    if ct.can_heal(target):
        return Direction.CENTRE, Heal(target)

    # Navigate to bridge
    move, build = move_toward_with_road(state, ct, target)
    state.debug_target = (target, 0, 255, 128)
    return move, build
