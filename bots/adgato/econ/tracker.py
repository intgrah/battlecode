"""Track positions of specific entity types or environment types on the map."""

from __future__ import annotations

from cambc import Controller, EntityType, Environment, Position


class Tracker:
    """Maintains a set of positions matching a given entity type or environment type.

    Call ``update_tile`` from ``_update_nearby_tiles`` for each visible tile.
    When symmetry is known, the mirrored tile is also updated.
    """

    def __init__(
        self,
        w: int,
        h: int,
        *,
        entity_type: EntityType | None = None,
        environment: Environment | None = None,
        allied_only: bool = False,
    ) -> None:
        if entity_type is None and environment is None:
            raise ValueError("must specify entity_type or environment")
        self.w = w
        self.h = h
        self._entity_type = entity_type
        self._environment = environment
        self._allied_only = allied_only
        self.positions: set[int] = set()
        self._changed: bool = False

    def take_changed(self) -> bool:
        """Return whether the tracked set changed, and reset the flag."""
        changed = self._changed
        self._changed = False
        return changed

    def _matches(
        self,
        env: Environment,
        building_type: EntityType | None,
        is_allied: bool,
    ) -> bool:
        if self._environment is not None:
            return env == self._environment
        if self._entity_type is not None:
            if building_type != self._entity_type:
                return False
            if self._allied_only and not is_allied:
                return False
            return True
        return False

    def update_tile(
        self,
        i: int,
        env: Environment,
        building_type: EntityType | None,
        is_allied: bool,
    ) -> None:
        """Update tracking for tile index *i*. Called from ``_update_nearby_tiles``."""
        positions = self.positions
        old_len = len(positions)
        if self._matches(env, building_type, is_allied):
            positions.add(i)
        else:
            positions.discard(i)
        if len(positions) != old_len:
            self._changed = True

    def as_positions(self) -> list[Position]:
        """Return tracked indices as ``Position`` objects."""
        w = self.w
        return [Position(i % w, i // w) for i in self.positions]
    
    def draw_tracked(self, ct: Controller, r: int, g: int, b: int) -> None:
        """Draw an indicator dot on each tracked position."""
        w = self.w
        for i in self.positions:
            ct.draw_indicator_dot(Position(i % w, i // w), r, g, b)
