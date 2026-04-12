"""Declarative state visualisation for the replay viewer.

Usage in builder code:

    from visualiser import Grid, Scalar, Tiles, Palette, VectorField, emit

    emit(
        dist=Grid(
            state.dist,
            palette=Palette(
                stops=[(0.0, 0, 200, 0, 120), (1.0, 200, 0, 0, 180)],
                special={-1: (0, 0, 0, 0), INF: (80, 80, 80, 100)},
            ),
        ),
        bfs=VectorField(angles),
        scale=Scalar(142.5),
        goals=Tiles([(3, 5), (7, 2)]),
    )

The replay viewer parses lines prefixed with ##VIS## from bot stdout.
Each call to emit() replaces the previous vis state for that bot on that turn.

Palette stops: list of (t, r, g, b, a) where t in [0, 1].
    Values are auto-scaled to [min, max] of non-special data, then interpolated.

Special values: dict mapping value -> (r, g, b, a).
    Use (0, 0, 0, 0) for transparent. Matched values bypass the palette.
    Special values are excluded from min/max auto-scaling.

VectorField: per-tile arrows.
    angles: radians per tile, None = no arrow.
    magnitudes: optional, scales arrow length. None = uniform length.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

VIS_PREFIX = "##VIS## "


@dataclass(frozen=True, slots=True)
class Palette:
    stops: Sequence[tuple[float, int, int, int, int]]
    special: dict[float | int, tuple[int, int, int, int]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Grid:
    data: Sequence[float | int | bool | None]
    palette: Palette


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


def _serialize_field(v: Grid | Scalar | Tiles | VectorField) -> dict:
    match v:
        case Grid(data=d, palette=p):
            return {
                "type": "grid",
                "data": list(d),
                "palette": {
                    "stops": [list(s) for s in p.stops],
                    "special": {str(k): list(c) for k, c in p.special.items()},
                },
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


def emit(**fields: Grid | Scalar | Tiles | VectorField) -> None:
    obj = {name: _serialize_field(v) for name, v in fields.items()}
    print(f"{VIS_PREFIX}{json.dumps(obj, separators=(',', ':'))}")


def emit_dict(fields: dict[str, Grid | Scalar | Tiles | VectorField]) -> None:
    obj = {name: _serialize_field(v) for name, v in fields.items()}
    print(f"{VIS_PREFIX}{json.dumps(obj, separators=(',', ':'))}")
