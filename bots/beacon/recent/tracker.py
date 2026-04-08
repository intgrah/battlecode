"""Track positions of specific environment types on the map. From adgato/mesh."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Environment, Position
from symmetry import mirror_idx

if TYPE_CHECKING:
    from util import Symmetry


class Tracker:
    def __init__(
        self,
        w: int,
        h: int,
        *,
        environment: Environment | None = None,
    ) -> None:
        self.w = w
        self.h = h
        self._environment = environment
        self.positions: set[int] = set()
        self._changed: bool = False

    def take_changed(self) -> bool:
        changed = self._changed
        self._changed = False
        return changed

    def update_tile(
        self,
        i: int,
        env: Environment,
        sym: Symmetry | None,
    ) -> None:
        positions = self.positions
        old_len = len(positions)
        if self._environment is not None and env == self._environment:
            positions.add(i)
        else:
            positions.discard(i)
        if len(positions) != old_len:
            self._changed = True

        if sym is not None and self._environment is not None:
            mi = mirror_idx(i, sym, self.w, self.h)
            old_len = len(positions)
            if env == self._environment:
                positions.add(mi)
            else:
                positions.discard(mi)
            if len(positions) != old_len:
                self._changed = True

    def mirror_known(self, sym: Symmetry) -> None:
        if self._environment is None:
            return
        w, h = self.w, self.h
        old_len = len(self.positions)
        self.positions |= {mirror_idx(i, sym, w, h) for i in self.positions}
        if len(self.positions) != old_len:
            self._changed = True

    def as_positions(self) -> list[Position]:
        w = self.w
        return [Position(i % w, i // w) for i in self.positions]
