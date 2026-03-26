"""Sentinel turret logic for trollbot — shoot the nearest enemy harvester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType
from utils import _DIR_IDX


def run_sentinel(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    my_team = ct.get_team()

    any_adjacent = False

    facing = _DIR_IDX[ct.get_direction()]

    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.HARVESTER:
            continue

        hp = ct.get_position(bid)
        d = pos.distance_squared(hp)
        if d > 1:
            continue
        if ct.get_team(bid) == my_team:
            continue

        direction = _DIR_IDX[pos.direction_to(hp)]
        if (direction - facing + 8) % 8 > 1:
            continue

        any_adjacent = True
        if ct.can_fire(hp):
            ct.fire(hp)
            return

    if not any_adjacent:
        ct.self_destruct()
