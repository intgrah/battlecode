"""Launcher unit logic — relay max marker value along the chain."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType
from pathfinding import _ALL_DIRS
from utils import in_bounds


def run_launcher(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    my_team = ct.get_team()

    # Read max marker value from all visible markers
    max_val = 0
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER or ct.get_team(bid) != my_team:
            continue
        val = ct.get_marker_value(bid)
        max_val = max(max_val, val)

    # Write max value to our own marker
    for d in _ALL_DIRS:
        adj = pos.add(d)
        if in_bounds(ct, adj) and ct.can_place_marker(adj):
            ct.place_marker(adj, max_val)
            return
