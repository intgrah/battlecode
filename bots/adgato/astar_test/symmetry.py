"""Map symmetry detection via incremental tile observation."""

from __future__ import annotations

from enum import Enum

from cambc import Environment, Position
from utils import chebyshev


class Symmetry(Enum):
    UNKNOWN = 0
    ROTATIONAL = 1
    HORIZONTAL = 2
    VERTICAL = 3


def mirror(a: Position, sym: Symmetry, w: int, h: int) -> Position:
    if sym is Symmetry.HORIZONTAL:
        return Position(w - 1 - a.x, a.y)
    if sym is Symmetry.VERTICAL:
        return Position(a.x, h - 1 - a.y)
    return Position(w - 1 - a.x, h - 1 - a.y)


class SymmetryDetector:
    """Incrementally eliminates map symmetries by comparing observed tile environments."""

    def __init__(self, w: int, h: int, core: Position) -> None:
        self.w = w
        self.h = h
        self._core = core
        self._known_env: dict[int, Environment] = {}
        self._resolved: Symmetry = Symmetry.UNKNOWN
        self._enemy_core: Position | None = None

        # Only keep symmetries that don't map the core onto itself
        self._candidates: list[Symmetry] = [
            sym
            for sym in (Symmetry.HORIZONTAL, Symmetry.VERTICAL, Symmetry.ROTATIONAL)
            if chebyshev(mirror(core, sym, w, h), core) > 1
        ]

    @property
    def resolved(self) -> Symmetry:
        return self._resolved

    @property
    def enemy_core(self) -> Position | None:
        return self._enemy_core

    @property
    def known_env(self) -> dict[int, Environment]:
        return self._known_env

    def update(self, tile_idx: int, tile: Position, env: Environment) -> None:
        """Observe a tile and eliminate incompatible symmetries."""
        if self._resolved is not Symmetry.UNKNOWN:
            return

        known = self._known_env
        if tile_idx in known:
            return
        known[tile_idx] = env

        w, h = self.w, self.h
        remaining: list[Symmetry] = []
        for sym in self._candidates:
            m = mirror(tile, sym, w, h)
            mi = m.y * w + m.x
            if mi in known and known[mi] != env:
                continue
            remaining.append(sym)
        self._candidates = remaining

        # Check for resolution
        if len(self._candidates) == 1:
            self._resolved = self._candidates[0]
            self._enemy_core = mirror(self._core, self._resolved, w, h)
        elif len(self._candidates) > 1:
            positions = {mirror(self._core, sym, w, h) for sym in self._candidates}
            if len(positions) == 1:
                self._resolved = self._candidates[0]
                self._enemy_core = positions.pop()
