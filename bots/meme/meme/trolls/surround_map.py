from __future__ import annotations

from typing import TYPE_CHECKING, Generator

from cambc import Position, Direction
from rust import Game, RawMem, EntityBuilderBot, EntitySentinel, GameDiffPlaceEntity
from god_mode import GodMode
import random

INF = 1_000_000_000

if TYPE_CHECKING:
    from main import Player

def surround_map(p: Player) -> Generator:

    w = p.map.width
    h = p.map.height

    if p.boundary_built >= 2 * (w + h) or p.turret_id is None:
        return

    turret_id = p.turret_id

    def build_sentinel(pos: Position, dir: Direction):
        GodMode.clone_in_replay(p, turret_id, pos)
        place_diff = p.g.replay_recorder.last_place_entity.as_variant
        assert isinstance(place_diff, GameDiffPlaceEntity)
        sentinel_diff = place_diff.entity.as_variant
        assert isinstance(sentinel_diff, EntitySentinel)
        sentinel_diff.direction = dir
        p.boundary_built += 1

    assert p.boundary_built >= 0
    offset = p.boundary_built
    for x in range(offset, w):
        build_sentinel(Position(x, h), Direction.SOUTH)
        yield

    assert p.boundary_built >= w
    offset = p.boundary_built - w
    for x in range(offset, w):
        build_sentinel(Position(x, -1), Direction.NORTH)
        yield
        
    assert p.boundary_built >= 2 * w
    offset = p.boundary_built - 2 * w
    for y in range(offset, h):
        build_sentinel(Position(w, y), Direction.EAST)
        yield

    assert p.boundary_built >= 2 * w + h
    offset = p.boundary_built - 2 * w - h
    for y in range(offset, h):
        build_sentinel(Position(-1, y), Direction.WEST)
        yield