"""Teleport an existing entity to a new tile, optionally with replay fixup.

Snapshots the entity's bytes, silent-builds a phantom road at its current
position to generate a `PlaceEntity` diff, then overwrites that diff with
the entity's bytes plus the new position — so the replay shows the entity
appearing at the destination instead of a stray road.

`move_last_in_replay` is the diff-only primitive: it patches whatever
`PlaceEntity` diff was emitted most recently, without touching engine state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType
from rust import Game, GameDiffPlaceEntity

from cheats.build import build_anywhere

if TYPE_CHECKING:
    from cambc import Controller, Position


def teleport(
    g: Game,
    ct: Controller,
    builder_id: int,
    bid: int,
    to_pos: Position,
    *,
    in_replay: bool = True,
) -> None:
    """Move entity `bid` to `to_pos`. No-op if `bid` doesn't exist or
    the move is to the same tile."""
    if bid not in g.entities:
        return

    entity = g.entities[bid]
    from_pos = entity.base.position
    if from_pos == to_pos:
        return

    if in_replay:
        entity_bytes = g._raw.read_bytes(entity._addr + 8, 64)
        if (
            build_anywhere(g, ct, builder_id, EntityType.ROAD, from_pos, silent=True)
            is None
        ):
            return
        place_diff = g.replay_recorder.last_place_entity.as_variant
        assert isinstance(place_diff, GameDiffPlaceEntity)
        g._raw.write_bytes(place_diff._addr, entity_bytes)
        place_diff.entity.base.position = to_pos

    from_tile = g.game_map.tile(from_pos.x, from_pos.y)
    if from_tile.building == bid:
        from_tile.building = None
    g.game_map.tile(to_pos.x, to_pos.y).building = bid
    g.entities[bid].base.position = to_pos


def move_last_in_replay(g: Game, to_pos: Position) -> None:
    """Patch the most recent `PlaceEntity` diff so the replay viewer
    shows the placed entity at `to_pos`. Engine state is untouched."""
    place_diff = g.replay_recorder.last_place_entity.as_variant
    assert isinstance(place_diff, GameDiffPlaceEntity)
    bid = place_diff.entity.base.id

    if bid not in g.entities:
        return

    entity = g.entities[bid]
    entity_bytes = g._raw.read_bytes(entity._addr + 8, 64)

    g._raw.write_bytes(place_diff._addr, entity_bytes)
    place_diff.entity.base.position = to_pos
