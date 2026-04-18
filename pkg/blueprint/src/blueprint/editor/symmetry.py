from __future__ import annotations

from enum import StrEnum

from blueprint.editor.map_io import MapData

__all__ = ["Symmetry", "detect_symmetry", "mirror_delta", "mirror_pos"]


class Symmetry(StrEnum):
    ROT = "rot"
    HOR = "hor"
    VER = "ver"


def mirror_pos(pos: tuple[int, int], w: int, h: int, sym: Symmetry) -> tuple[int, int]:
    x, y = pos
    match sym:
        case Symmetry.HOR:
            return (x, h - 1 - y)
        case Symmetry.VER:
            return (w - 1 - x, y)
        case Symmetry.ROT:
            return (w - 1 - x, h - 1 - y)


def mirror_delta(dx: int, dy: int, sym: Symmetry) -> tuple[int, int]:
    match sym:
        case Symmetry.HOR:
            return (dx, -dy)
        case Symmetry.VER:
            return (-dx, dy)
        case Symmetry.ROT:
            return (-dx, -dy)


def _tiles_match(m: MapData, sym: Symmetry) -> bool:
    w, h = m.w, m.h
    for y in range(h):
        for x in range(w):
            mx, my = mirror_pos((x, y), w, h, sym)
            if m.tiles[y * w + x] != m.tiles[my * w + mx]:
                return False
    return True


def detect_symmetry(m: MapData) -> Symmetry:
    """A map is symmetric under `sym` iff:
      - mirroring core_a produces core_b, AND
      - every tile equals its mirror.

    Core positions alone are ambiguous on maps where cores lie on two
    symmetry axes simultaneously. Tile patterns alone are ambiguous when
    the tile set is symmetric under multiple reflections (e.g. fully
    empty maps). Both together give a unique answer.
    """
    w, h = m.w, m.h
    for sym in Symmetry:
        if mirror_pos(m.core_a, w, h, sym) != m.core_b:
            continue
        if _tiles_match(m, sym):
            return sym
    msg = f"no symmetry detected for {m.name}"
    raise ValueError(msg)
