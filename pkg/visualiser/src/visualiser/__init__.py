# ruff: noqa: UP046, UP047
# 3.11 compatible, so no PEP 695
"""Declarative state visualisation for the replay viewer.

Usage in builder code:

    from visualiser import (
        BoolGrid, I16Grid, Scalar, Tiles, Palette, PaletteStop,
        Colour, VectorField, emit, TRANSPARENT,
    )

    P_DIST = Palette(
        stops=[PaletteStop(0, Colour(50, 200, 50, 140)), PaletteStop(100, Colour(200, 50, 50, 140))],
        special={INF: TRANSPARENT},
    )

    emit(
        dist=I16Grid(state.dist, palette=P_DIST),
        fog=BoolGrid([e is None for e in self.env], palette=P_FOG),
        scale=Scalar(142.5),
        goals=Tiles([(3, 5), (7, 2)]),
    )

The replay viewer parses lines prefixed with ##VIS## from bot stdout.
Each call to emit() replaces the previous vis state for that bot on that turn.

Palette stops use actual data values (not normalised). Interpolation is
clamped outside the stop range.

Special values: dict mapping value -> Colour.
    Use TRANSPARENT for invisible. Matched values bypass the gradient.

Supported grid types: BoolGrid, U8Grid, I16Grid, U16Grid, F32Grid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

T = TypeVar("T", int, float, bool)

VIS_PREFIX = "##VIS## "


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


def _serialize_palette(p: Palette) -> dict:
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
class Scalar:
    data: float | int | str


@dataclass(frozen=True, slots=True)
class Tiles:
    data: Iterable[tuple[int, int]]


@dataclass(frozen=True, slots=True)
class VectorField:
    angles: Sequence[float | None]
    magnitudes: Sequence[float] | None = None


type VisField = GridType | Scalar | Tiles | VectorField

_GRID_DTYPE: dict[type[VisField], str] = {
    BoolGrid: "bool",
    U8Grid: "u8",
    I16Grid: "i16",
    U16Grid: "u16",
    F32Grid: "f32",
}


def _serialize_field(v: VisField) -> dict:
    match v:
        case BoolGrid() | U8Grid() | I16Grid() | U16Grid() | F32Grid():
            return {
                "type": "grid",
                "dtype": _GRID_DTYPE[type(v)],
                "data": list(v.data),
                "palette": _serialize_palette(v.palette),
            }
        case Scalar(data=d):
            return {"type": "scalar", "data": d}
        case Tiles(data=d):
            return {"type": "tiles", "data": [list(t) for t in d]}
        case VectorField(angles=a, magnitudes=m):
            obj: dict = {"type": "vectorfield", "angles": list(a)}
            if m is not None:
                obj["magnitudes"] = list(m)
            return obj


def emit(**fields: VisField) -> None:
    obj = {name: _serialize_field(v) for name, v in fields.items()}
    print(f"{VIS_PREFIX}{json.dumps(obj, separators=(',', ':'))}")
