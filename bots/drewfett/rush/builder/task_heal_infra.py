"""Heal damaged friendly infrastructure (harvesters, conveyors, roads)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, EntityType, GameConstants, Position

from .action import Action, Heal
from .helpers import move_toward_with_road

if TYPE_CHECKING:
    from .state import State


def heal_infra(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Find nearest damaged friendly building and heal it.

    Skips targets if another friendly builder is closer (let them handle it).
    """
    _t0 = ct.get_cpu_time_elapsed()
    my_team = ct.get_team()
    my_id = ct.get_id()
    pos = state.pos

    # Collect positions of other friendly builders
    other_builders: list[Position] = []
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if (
            ct.get_team(uid) == my_team
            and ct.get_entity_type(uid) == EntityType.BUILDER_BOT
        ):
            other_builders.append(ct.get_position(uid))

    best_pos: Position | None = None
    best_ratio = 1.0
    best_dist = 1_000_000

    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype == EntityType.CORE:
            continue  # heal_core handles this
        hp = ct.get_hp(bid)
        max_hp = ct.get_max_hp(bid)
        if hp >= max_hp:
            continue
        bp = ct.get_position(bid)
        dist = pos.distance_squared(bp)
        # Skip if another builder is closer to this target
        if any(ob.distance_squared(bp) < dist for ob in other_builders):
            continue
        ratio = hp / max_hp
        # Prefer most damaged, then closest
        if ratio < best_ratio or (ratio == best_ratio and dist < best_dist):
            best_ratio = ratio
            best_dist = dist
            best_pos = bp

    if best_pos is None:
        return None

    if pos.distance_squared(best_pos) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(
        best_pos
    ):
        return Direction.CENTRE, Heal(best_pos)

    return move_toward_with_road(state, ct, best_pos)
