"""Teleport an existing building to a new tile, optionally with replay fixup.

Snapshots the moving entity's bytes, clears the source tile, and (when
`in_replay` is set) places a marker at the destination to generate a
`PlaceEntity` diff that we then overwrite with the moved entity's bytes —
so the replay shows the entity appearing at the destination rather than a
stray marker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rust import Game, GameDiffPlaceEntity

from trolls.place_marker import place_marker_anywhere

if TYPE_CHECKING:
    from cambc import Controller, Position


def teleport(
    g: Game,
    ct: Controller,
    builder_id: int,
    from_pos: Position,
    to_pos: Position,
    *,
    in_replay: bool = True,
) -> None:
    """Move whatever building is at `from_pos` to `to_pos`. No-op if the
    source tile has no building, the move is a no-op, or the building
    isn't tracked in `g.entities`."""
    from_tile = g.game_map.tile(from_pos.x, from_pos.y)
    bid = from_tile.building
    if bid is None or from_pos == to_pos or bid not in g.entities:
        return

    entity_bytes = g._raw.read_bytes(g.entities[bid]._addr + 8, 64)

    from_tile.building = None
    to_tile = g.game_map.tile(to_pos.x, to_pos.y)

    if in_replay:
        if not place_marker_anywhere(g, ct, builder_id, to_pos):
            return
        place_diff = g.replay_recorder.last_diff.as_variant
        assert isinstance(place_diff, GameDiffPlaceEntity)
        g._raw.write_bytes(place_diff._addr, entity_bytes)
        place_diff.entity.base.position = to_pos

    to_tile.building = bid
    g.entities[bid].base.position = to_pos
