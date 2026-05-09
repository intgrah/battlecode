"""Hide a just-emitted entity spawn from the replay.

Rewrites the most recent `PlaceEntity` diff with a substitute entity's
bytes (typically the core), so the replay shows a re-placement of the
substitute at its existing position instead of revealing the new spawn.
Engine state retains the real spawn — only the replay is masked.
"""

from __future__ import annotations

from rust import Game, GameDiffPlaceEntity


def hide_last(g: Game, substitute_bid: int) -> None:
    """Mask the latest `PlaceEntity` diff using `substitute_bid`'s bytes."""
    bid = substitute_bid
    entity = g.entities[bid]
    pos = entity.base.position
    tile = g.game_map.tile(pos.x, pos.y)
    if tile.builder_bot == bid:
        tile.builder_bot = None
    if tile.building == bid:
        tile.building = None

    entity_bytes = g._raw.read_bytes(entity._addr + 8, 64)
    diff_variant = g.replay_recorder.last_place_entity.as_variant
    assert isinstance(diff_variant, GameDiffPlaceEntity)
    g._raw.write_bytes(diff_variant._addr, entity_bytes)
    spawn_base = diff_variant.entity.base
    spawn_base.id = bid
    spawn_base.position = g.entities[bid].base.position
