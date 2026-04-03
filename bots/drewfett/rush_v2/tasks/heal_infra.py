"""HOME: heal damaged friendly infrastructure near our base."""

from __future__ import annotations

from typing import TYPE_CHECKING

from action import Heal
from cambc import Controller, GameConstants, Position
from turn import ActionOnly, Turn
from util import INF

from ._helpers import move_toward

if TYPE_CHECKING:
    from state import State


def run(state: State, ct: Controller) -> Turn | None:
    """Find the most damaged nearby friendly building and heal it."""
    pos = state.pos
    w = state.w
    my_team = state.my_team

    best_pos: Position | None = None
    best_ratio: float = 1.0  # only consider buildings below full HP
    best_dist: int = INF

    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_team(bid) != my_team:
            continue
        # Skip the core (handled by heal_core task) and markers
        i = tile.y * w + tile.x
        if i in state.my_core_tiles:
            continue

        hp = ct.get_hp(bid)
        max_hp = ct.get_max_hp(bid)
        if max_hp <= 0 or hp >= max_hp:
            continue

        ratio = hp / max_hp
        dist = pos.distance_squared(tile)

        # Prefer lowest HP ratio; break ties by distance
        if ratio < best_ratio or (ratio == best_ratio and dist < best_dist):
            best_ratio = ratio
            best_dist = dist
            best_pos = tile

    if best_pos is None:
        return None

    # If within action radius, heal it
    if pos.distance_squared(best_pos) <= GameConstants.ACTION_RADIUS_SQ and ct.can_heal(
        best_pos
    ):
        return ActionOnly(Heal(best_pos))

    # Otherwise walk toward it
    return move_toward(state, ct, best_pos)
