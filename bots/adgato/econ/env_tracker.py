"""Track positions of specific entity types or environment types on the map."""

from __future__ import annotations

from cambc import Controller, EntityType, Environment, Position
from symmetry import Symmetry, mirror_idx


class EnvTracker:
    """Maintains a set of positions matching a given entity type or environment type.

    Call ``update_tile`` from ``_update_nearby_tiles`` for each visible tile.
    When symmetry is known, the mirrored tile is also updated.
    """

    def __init__(
        self,
        w: int,
        h: int,
        environment: Environment,
        *,
        entity_types: frozenset[EntityType] = frozenset(),
        allied_only: bool = False,
    ) -> None:
        self.w = w
        self.h = h
        self._environment = environment
        self._entity_types = entity_types
        self._allied_only = allied_only
        self.positions: dict[int, bool] = dict()
        self._changed: bool = False

    def take_changed(self) -> bool:
        """Return whether the tracked set changed, and reset the flag."""
        changed = self._changed
        self._changed = False
        return changed

    def _matches(
        self,
        building_type: EntityType | None,
        is_allied: bool,
    ) -> bool:
        return building_type in self._entity_types and (
            not self._allied_only or is_allied
        )

    def update_tile(
        self,
        i: int,
        env: Environment,
        building_type: EntityType | None,
        is_allied: bool,
        sym: Symmetry,
    ) -> None:
        """Update tracking for tile index *i*. Called from ``_update_nearby_tiles``."""

        if env != self._environment:
            return

        positions = self.positions
        matches = self._matches(building_type, is_allied)
        if i not in positions:
            self._changed |= matches
        else:
            self._changed |= positions[i] != matches
        positions[i] = matches

        # Mirror via symmetry — we only know the environment for certain,
        # not what building sits on the mirrored tile, so only mirror
        # environment-based trackers.
        if sym is not Symmetry.UNKNOWN:
            mi = mirror_idx(i, sym, self.w, self.h)
            if mi not in positions:
                self._changed = True
                positions[mi] = True

    def mirror_known(self, sym: Symmetry) -> None:
        """Add mirrored indices for all currently tracked positions.

        Only applicable to environment-based trackers, since environment
        is guaranteed symmetric but buildings are not.
        """
        positions = self.positions
        for i in list(positions):
            mi = mirror_idx(i, sym, self.w, self.h)
            if mi not in positions:
                self._changed = True
                positions[mi] = True

    def any_positions(self) -> bool:
        return any(self.positions.values())

    def as_positions(self) -> list[Position]:
        """Return tracked indices as ``Position`` objects."""
        w = self.w
        return [Position(i % w, i // w) for i, v in self.positions.items() if v]

    def draw_tracked(self, ct: Controller, r: int, g: int, b: int) -> None:
        """Draw an indicator dot on each tracked position."""
        for p in self.as_positions():
            ct.draw_indicator_dot(p, r, g, b)
