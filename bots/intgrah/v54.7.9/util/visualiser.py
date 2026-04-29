"""Visualisation primitives.

Defines the `Dump*` family of dataclasses (each a typed payload the
viewer knows how to render) and the `Dumper` class that bots use to
emit a per-turn JSON tree of named dump nodes.

A dumpable value is always one of the `Dump*` types listed in `Dump`.
Plain Python values (positions, ints, floats, etc.) are not accepted
directly — the caller wraps them as `DumpScalar`, `DumpTile`, `DumpDot`,
etc., to remove ambiguity (e.g. a `Position` can be debugged as either
a `DumpTile` ring or a `DumpDot` filled dot — the choice is explicit).

`Dumper` owns the per-turn scope tree and the same-elision cache so
each unit/builder gets independent state without module-level globals.
"""

# ruff: noqa: UP046, UP047
# 3.11 compatible, so no PEP 695

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar

from cambc import Position

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


def _serialise_palette(p: Palette) -> dict[str, Any]:
    return {
        "stops": [
            [s.t, s.colour.r, s.colour.g, s.colour.b, s.colour.a] for s in p.stops
        ],
        "special": {str(k): [c.r, c.g, c.b, c.a] for k, c in p.special.items()},
    }


def _serialise_colour(c: Colour) -> list[int]:
    return [c.r, c.g, c.b, c.a]


# ---------------------------------------------------------------------
# Dump* types: every value passed to `Dumper.dump` is one of these.
# ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DumpBoolGrid:
    data: Sequence[bool]
    palette: Palette[bool]


@dataclass(frozen=True, slots=True)
class DumpU8Grid:
    data: Sequence[int]
    palette: Palette[int]


@dataclass(frozen=True, slots=True)
class DumpI16Grid:
    data: Sequence[int]
    palette: Palette[int]


@dataclass(frozen=True, slots=True)
class DumpU16Grid:
    data: Sequence[int]
    palette: Palette[int]


@dataclass(frozen=True, slots=True)
class DumpF32Grid:
    data: Sequence[float]
    palette: Palette[float]


@dataclass(frozen=True, slots=True)
class DumpTiles:
    """Unordered set of tiles, rendered as cell rings."""

    data: Iterable[Position]


@dataclass(frozen=True, slots=True)
class DumpTile:
    """Single tile rendered as a ring around the cell. Use when a
    `Position` should highlight a cell. `pos=None` renders as nothing
    so callers can dump the field unconditionally even when there's no
    current target."""

    pos: Position | None


@dataclass(frozen=True, slots=True)
class DumpDot:
    """Single tile rendered as a filled coloured dot. Use when a
    `Position` should highlight a point rather than the whole cell.
    `pos=None` renders as nothing."""

    pos: Position | None
    colour: Colour


@dataclass(frozen=True, slots=True)
class DumpPath:
    """Ordered list of tiles rendered as a polyline."""

    points: Sequence[Position]
    colour: Colour


@dataclass(frozen=True, slots=True)
class DumpVectorField:
    angles: Sequence[float | None]
    magnitudes: Sequence[float] | None = None


@dataclass(frozen=True, slots=True)
class DumpScalar:
    """Plain value (int / float / bool / str / None) shown verbatim."""

    value: int | float | bool | str | None


Dump = (
    DumpBoolGrid
    | DumpU8Grid
    | DumpI16Grid
    | DumpU16Grid
    | DumpF32Grid
    | DumpTiles
    | DumpTile
    | DumpDot
    | DumpPath
    | DumpVectorField
    | DumpScalar
)


_GRID_DTYPE: dict[type, str] = {
    DumpBoolGrid: "bool",
    DumpU8Grid: "u8",
    DumpI16Grid: "i16",
    DumpU16Grid: "u16",
    DumpF32Grid: "f32",
}


def _serialise_dump(v: Dump) -> dict[str, Any]:
    """Convert a `Dump` value to its tagged dict representation."""
    match v:
        case (
            DumpBoolGrid()
            | DumpU8Grid()
            | DumpI16Grid()
            | DumpU16Grid()
            | DumpF32Grid()
        ):
            return {
                "$type": f"{_GRID_DTYPE[type(v)]}grid",
                "v": list(v.data),
                "palette": _serialise_palette(v.palette),
            }
        case DumpTiles(data=d):
            return {"$type": "tiles", "v": [[p.x, p.y] for p in d]}
        case DumpTile(pos=p):
            return (
                {"$type": "tile", "x": None, "y": None}
                if p is None
                else {"$type": "tile", "x": p.x, "y": p.y}
            )
        case DumpDot(pos=p, colour=c):
            return (
                {
                    "$type": "dot",
                    "x": None,
                    "y": None,
                    "colour": _serialise_colour(c),
                }
                if p is None
                else {
                    "$type": "dot",
                    "x": p.x,
                    "y": p.y,
                    "colour": _serialise_colour(c),
                }
            )
        case DumpPath(points=ps, colour=c):
            return {
                "$type": "path",
                "v": [[p.x, p.y] for p in ps],
                "colour": _serialise_colour(c),
            }
        case DumpVectorField(angles=a, magnitudes=m):
            obj: dict[str, Any] = {"$type": "vectorfield", "angles": list(a)}
            if m is not None:
                obj["magnitudes"] = list(m)
            return obj
        case DumpScalar(value=v_):
            return {"$type": "scalar", "v": v_}


def _auto_wrap(v: object) -> dict[str, Any]:
    """Auto-wrap a raw Python value into a tagged dict for use in
    `debug()` message args. Unlike state dumps (`vis()`) which require
    explicitly-typed `Dump*` payloads, msg args are written like
    `debug("tmpl {x}", x=self.my_pos)` with raw values, and we infer
    the right widget type:
      - Position -> tile (hoverable cell ring)
      - Dump* type -> use as-is
      - int / float / bool / str / None -> scalar
      - everything else -> scalar with repr()
    """
    if isinstance(v, Position):
        return {"$type": "tile", "x": v.x, "y": v.y}
    if isinstance(
        v,
        (
            DumpBoolGrid,
            DumpU8Grid,
            DumpI16Grid,
            DumpU16Grid,
            DumpF32Grid,
            DumpTiles,
            DumpTile,
            DumpDot,
            DumpPath,
            DumpVectorField,
            DumpScalar,
        ),
    ):
        return _serialise_dump(v)
    if v is None or isinstance(v, (int, float, bool, str)):
        return {"$type": "scalar", "v": v}
    return {"$type": "scalar", "v": repr(v)}


# ---------------------------------------------------------------------
# Dumper: per-unit (per-subinterpreter) state and tree builder.
# ---------------------------------------------------------------------


class Dumper:
    """Per-unit same-elision dump emitter.

    Holds a read-only reference to the scope stack maintained by an
    external `Scope` machinery (typically the bot's `util.debug`
    module). On `dump(name, value)`, appends a vis node to the
    `children` of the current top-of-stack scope, eliding the payload
    via `{"$type": "same"}` when it equals the value emitted under the
    same name on a previous call.

    The scope stack is owned by the caller; Dumper only reads from it.
    """

    __slots__ = ("_same_cache", "_scope_stack")

    def __init__(self, scope_stack: list[dict[str, Any]]) -> None:
        self._scope_stack: Final[list[dict[str, Any]]] = scope_stack
        self._same_cache: dict[str, dict[str, Any]] = {}

    def dump(self, name: str, value: Dump) -> None:
        """Append a vis node under the current scope. If the payload is
        identical to the last value emitted under `name`, emit a
        `{"$type": "same"}` marker instead so the viewer can reuse the
        previous turn's value.
        """
        payload = _serialise_dump(value)
        if self._same_cache.get(name) == payload:
            node = {"$type": "vis", "name": name, "value": {"$type": "same"}}
        else:
            self._same_cache[name] = payload
            node = {"$type": "vis", "name": name, "value": payload}
        if self._scope_stack:
            self._scope_stack[-1]["children"].append(node)
