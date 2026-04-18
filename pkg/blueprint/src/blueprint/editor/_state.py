"""Editor-only in-memory blueprint state with undo support."""

from __future__ import annotations

from dataclasses import dataclass, replace

from blueprint import DIRECTIONAL, BlueprintEntry, Direction, Entity

__all__ = ["State"]

_DIR4 = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
_DIR8 = tuple(Direction)
_CARDINAL_ONLY: frozenset[Entity] = frozenset(
    {Entity.CONVEYOR, Entity.SPLITTER, Entity.ARMOURED_CONVEYOR},
)


@dataclass
class State:
    """In-memory blueprint during editing. Keyed on pos for O(1) edits."""

    entries: dict[tuple[int, int], BlueprintEntry]
    history: list[tuple[str, BlueprintEntry | None, BlueprintEntry | None]]
    """Undo stack: each record is (op, before, after)."""
    dirty: bool = False

    @classmethod
    def empty(cls) -> State:
        return cls(entries={}, history=[])

    def place(self, entry: BlueprintEntry) -> None:
        prev = self.entries.get(entry.pos)
        self.entries[entry.pos] = entry
        self.history.append(("place", prev, entry))
        self.dirty = True

    def erase(self, pos: tuple[int, int]) -> None:
        prev = self.entries.pop(pos, None)
        if prev is None:
            return
        self.history.append(("erase", prev, None))
        self.dirty = True

    def rotate(self, pos: tuple[int, int], step: int = 1) -> None:
        entry = self.entries.get(pos)
        if entry is None or entry.kind not in DIRECTIONAL:
            return
        dirs = _DIR4 if entry.kind in _CARDINAL_ONLY else _DIR8
        cur = entry.direction or dirs[0]
        if cur not in dirs:
            cur = dirs[0]
        new = dirs[(dirs.index(cur) + step) % len(dirs)]
        updated = replace(entry, direction=new)
        self.entries[pos] = updated
        self.history.append(("rotate", entry, updated))
        self.dirty = True

    def undo(self) -> None:
        if not self.history:
            return
        _op, before, after = self.history.pop()
        if before is None:
            if after is not None:
                self.entries.pop(after.pos, None)
        else:
            self.entries[before.pos] = before
        self.dirty = True
