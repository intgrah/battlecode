from __future__ import annotations

from typing import TYPE_CHECKING

from blueprint import BlueprintEntry, mirror_entry
from cambc import EntityType, Position, Team
from hardcode.blueprints import BLUEPRINTS
from hardcode.known import KnownMap
from hardcode.map import CANDIDATES, CORE_A, CORE_B, DIMENSIONS, SYMMETRY, TILES, decode

if TYPE_CHECKING:
    from cambc import Controller

__all__ = ["find_core", "identify_map", "load_mirrored_blueprint"]


# (w, h, team) -> list of candidate KnownMaps.
_BY_WH_TEAM: dict[tuple[int, int, Team], list[KnownMap]] = {}
for _km, _wh in DIMENSIONS.items():
    _BY_WH_TEAM.setdefault((*_wh, Team.A), []).append(_km)
    _BY_WH_TEAM.setdefault((*_wh, Team.B), []).append(_km)


def find_core(ct: Controller, my_team: Team) -> Position | None:
    """Return the team's core position if visible, else None."""
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) == my_team and ct.get_entity_type(bid) == EntityType.CORE:
            return ct.get_position(bid)
    return None


def identify_map(
    ct: Controller,
    w: int,
    h: int,
    my_team: Team,
    my_core: Position | None,
) -> KnownMap | None:
    """Identify the map by (w, h, core) if core is visible, else by
    disambiguating on visible terrain tiles."""
    if my_core is not None:
        return CANDIDATES.get((w, h, my_core))
    candidates = _BY_WH_TEAM.get((w, h, my_team), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    for pos in ct.get_nearby_tiles():
        env = ct.get_tile_env(pos)
        survivors = []
        for km in candidates:
            tiles = decode(TILES[km](), w * h)
            if tiles[pos.y * w + pos.x] == env:
                survivors.append(km)
        candidates = survivors
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            return None
    return candidates[0] if candidates else None


def load_mirrored_blueprint(
    known: KnownMap | None,
    w: int,
    h: int,
    my_team: Team,
) -> tuple[tuple[BlueprintEntry, ...], frozenset[Position]]:
    """Load the blueprint and mirror it to our team's side."""
    if known is None:
        return (), frozenset()
    raw = BLUEPRINTS.get(known, ())
    if my_team == Team.A:
        entries = raw
    else:
        sym = SYMMETRY[known].value
        entries = tuple(mirror_entry(e, w, h, sym) for e in raw)
    positions = frozenset(Position(*e.pos) for e in entries)
    return entries, positions


def core_for(known: KnownMap, my_team: Team) -> Position:
    return CORE_A[known] if my_team == Team.A else CORE_B[known]
