"""Map symmetry detection via incremental tile observation."""

from __future__ import annotations

from enum import Enum

from cambc import Environment, Position


class Symmetry(Enum):
    UNKNOWN = 0
    ROTATIONAL = 1
    HORIZONTAL = 2
    VERTICAL = 3


def mirror_idx(i: int, sym: Symmetry, w: int, h: int) -> int:
    y = i // w
    x = i - y * w
    if sym is Symmetry.HORIZONTAL:
        return y * w + (w - 1 - x)
    if sym is Symmetry.VERTICAL:
        return (h - 1 - y) * w + x
    return (h - 1 - y) * w + (w - 1 - x)


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
        ci = core.y * w + core.x
        cx, cy = core.x, core.y
        self._candidates: list[Symmetry] = []
        for sym in (Symmetry.HORIZONTAL, Symmetry.VERTICAL, Symmetry.ROTATIONAL):
            mi = mirror_idx(ci, sym, w, h)
            mx, my = mi % w, mi // w
            if max(abs(mx - cx), abs(my - cy)) > 1:
                self._candidates.append(sym)

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
            mi = mirror_idx(tile_idx, sym, w, h)
            if mi in known and known[mi] != env:
                continue
            remaining.append(sym)
        self._candidates = remaining

        # Check for resolution
        ci = self._core.y * w + self._core.x
        if len(self._candidates) == 1:
            self._resolved = self._candidates[0]
            ei = mirror_idx(ci, self._resolved, w, h)
            self._enemy_core = Position(ei % w, ei // w)
        elif len(self._candidates) > 1:
            positions = {mirror_idx(ci, sym, w, h) for sym in self._candidates}
            if len(positions) == 1:
                self._resolved = self._candidates[0]
                ei = positions.pop()
                self._enemy_core = Position(ei % w, ei // w)
