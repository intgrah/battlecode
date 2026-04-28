"""Visualisation primitives.

These are thin wrappers around list/scalar payloads that the debug
tree's `vis()` helper routes into the per-turn JSON tree. There is no
longer a separate stdout channel — every line of bot stdout IS the
debug tree (one JSON object per turn).

Use `vis(name, X)` from `util.debug` instead of the previous `emit()`
sentinel-line API. The classes here exist for ergonomic construction
of structured grid / scalar / tile payloads with palette metadata.
"""

# ruff: noqa: UP046, UP047
# 3.11 compatible, so no PEP 695

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

T = TypeVar("T", int, float, bool)


@dataclass(frozen=True, slots=True)
class Colour:
    r: int
    g: int
    b: int
    a: int


TRANSPARENT = Colour(0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class PaletteStop(Generic[T]):
    t: T
    colour: Colour


@dataclass(frozen=True, slots=True)
class Palette(Generic[T]):
    stops: Sequence[PaletteStop[T]]
    special: dict[T, Colour] = field(default_factory=dict)


# Pre-built palettes
GREEN_RED = Palette(
    stops=[
        PaletteStop(0, Colour(50, 200, 50, 140)),
        PaletteStop(100, Colour(200, 50, 50, 140)),
    ],
)
BLUE_RED = Palette(
    stops=[
        PaletteStop(0, Colour(50, 50, 200, 140)),
        PaletteStop(100, Colour(200, 50, 50, 140)),
    ],
)
FOG = Palette(
    stops=[
        PaletteStop(t=False, colour=TRANSPARENT),
        PaletteStop(t=True, colour=Colour(0, 0, 0, 180)),
    ],
)


def with_special(palette: Palette[T], special: dict[T, Colour]) -> Palette[T]:
    """Return a copy of the palette with additional special values."""
    merged = {**palette.special, **special}
    return Palette(stops=palette.stops, special=merged)


def serialize_palette(p: Palette) -> dict[str, Any]:
    return {
        "stops": [
            [s.t, s.colour.r, s.colour.g, s.colour.b, s.colour.a] for s in p.stops
        ],
        "special": {str(k): [c.r, c.g, c.b, c.a] for k, c in p.special.items()},
    }


@dataclass(frozen=True, slots=True)
class BoolGrid:
    data: Sequence[bool]
    palette: Palette[bool]


@dataclass(frozen=True, slots=True)
class U8Grid:
    data: Sequence[int]
    palette: Palette[int]


@dataclass(frozen=True, slots=True)
class I16Grid:
    data: Sequence[int]
    palette: Palette[int]


@dataclass(frozen=True, slots=True)
class U16Grid:
    data: Sequence[int]
    palette: Palette[int]


@dataclass(frozen=True, slots=True)
class F32Grid:
    data: Sequence[float]
    palette: Palette[float]


GridType = BoolGrid | U8Grid | I16Grid | U16Grid | F32Grid


@dataclass(frozen=True, slots=True)
class Tiles:
    data: Iterable[tuple[int, int]]


@dataclass(frozen=True, slots=True)
class VectorField:
    angles: Sequence[float | None]
    magnitudes: Sequence[float] | None = None


_GRID_DTYPE: dict[type, str] = {
    BoolGrid: "bool",
    U8Grid: "u8",
    I16Grid: "i16",
    U16Grid: "u16",
    F32Grid: "f32",
}


def serialize(v: object) -> dict[str, Any]:
    """Convert a vis-primitive value into a tagged dict for the debug
    tree. Returns `{"$type": <type>, ...}`. The debug module's `vis()`
    helper dispatches here when the value is one of these dataclasses
    rather than a plain Python value.
    """

    match v:
        case BoolGrid() | U8Grid() | I16Grid() | U16Grid() | F32Grid():
            return {
                "$type": f"{_GRID_DTYPE[type(v)]}grid",
                "v": list(v.data),
                "palette": serialize_palette(v.palette),
            }
        case Tiles(data=d):
            return {"$type": "tiles", "v": [list(t) for t in d]}
        case VectorField(angles=a, magnitudes=m):
            obj: dict[str, Any] = {"$type": "vectorfield", "angles": list(a)}
            if m is not None:
                obj["magnitudes"] = list(m)
            return obj
    msg = f"unsupported vis type {type(v).__name__}"
    raise TypeError(msg)
