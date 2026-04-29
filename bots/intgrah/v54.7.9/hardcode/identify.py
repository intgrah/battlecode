from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType, Position, Team

from hardcode.map import CANDIDATES, CORE_A, CORE_B

if TYPE_CHECKING:
    from cambc import Controller

    from hardcode.known import KnownMap

__all__ = ["core_for", "find_core", "identify_map"]


def find_core(ct: Controller, my_team: Team) -> Position | None:
    """Return the team's core position if visible, else None."""
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) == my_team and ct.get_entity_type(bid) == EntityType.CORE:
            return ct.get_position(bid)
    return None


def identify_map(w: int, h: int, my_core: Position) -> KnownMap | None:
    """Identify the map by (width, height, own-core position)."""
    return CANDIDATES.get((w, h, my_core))


def core_for(known: KnownMap, my_team: Team) -> Position:
    return CORE_A[known] if my_team == Team.A else CORE_B[known]
