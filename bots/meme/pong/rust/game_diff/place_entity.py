from __future__ import annotations

from rust.entity import Entity
from rust.game_diff.variant import GameDiffVariant


class GameDiffPlaceEntity(GameDiffVariant):
    """
    GameDiff::PlaceEntity (72 B): niche variant — its bytes ARE the
    inner Entity. The Entity's own niche encoding lives at GameDiff[0..8],
    overlapping the GameDiff discriminant.

    `Entity`/`EntityVariant` are written for HashMap bucket layout, which
    prepends a 4 B key + 4 B pad before the Entity itself. A PlaceEntity
    diff has no such prefix, so we offset the Entity view by -8 to make
    its `_ENTITY_OFF=8` land on the diff's actual entity bytes.
    """

    @property
    def entity(self) -> Entity:
        return Entity(self._raw, self._addr - 8)

    def __repr__(self) -> str:
        return f"GameDiffPlaceEntity({self.entity!r})"
