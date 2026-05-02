"""
Translation of `bots/intgrah/v54.7.9/util/visualiser.py`.

Visualisation primitives. Defines the `Dump` enum (each variant a typed
payload the viewer knows how to render) and the `Dumper` struct that bots
use to emit a per-turn JSON tree of named dump nodes.
"""
from __future__ import annotations

from typing import Final
from dataclasses import dataclass

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Position

class Colour:
    r: int
    g: int
    b: int
    a: int

    def __init__(self, r, g, b, a):
        self.r = r
        self.g = g
        self.b = b
        self.a = a

    def as_array(self):
        return [self.r, self.g, self.b, self.a]
TRANSPARENT: Final[Colour] = Colour(0, 0, 0, 0)

class PaletteStop:
    """One stop in a `Palette`, generic over the scalar type `T` (bool / int / float)."""
    t: T
    colour: Colour

    def __init__(self, t: T, colour: Colour):
        self.t = t
        self.colour = colour

class Palette:
    """Linearly interpolated colour palette over scalar values of type `T`."""
    stops: list[PaletteStop]
    special: list[tuple[T, Colour]]

    def __init__(self, stops, special):
        self.stops = stops
        self.special = special

def green_red():
    return Palette([PaletteStop(t=0, colour=Colour(50, 200, 50, 140)), PaletteStop(t=100, colour=Colour(200, 50, 50, 140))], [])

def blue_red():
    return Palette([PaletteStop(t=0, colour=Colour(50, 50, 200, 140)), PaletteStop(t=100, colour=Colour(200, 50, 50, 140))], [])

def fog():
    return Palette([PaletteStop(t=False, colour=TRANSPARENT), PaletteStop(t=True, colour=Colour(0, 0, 0, 180))], [])

"""A scalar value carried by a `DumpScalar` node."""
@dataclass(frozen=True, slots=True)
class ScalarValueInt:
    _0: int

@dataclass(frozen=True, slots=True)
class ScalarValueFloat:
    _0: float

@dataclass(frozen=True, slots=True)
class ScalarValueBool:
    _0: bool

@dataclass(frozen=True, slots=True)
class ScalarValueStr:
    _0: str

@dataclass(frozen=True, slots=True)
class ScalarValueNull:
    pass

type ScalarValue = ScalarValueInt | ScalarValueFloat | ScalarValueBool | ScalarValueStr | ScalarValueNull

"""
All dumpable payload types. Each variant matches one Python `Dump*`
dataclass; serialisation produces the exact `{"$type": "...", ...}` shape
the Python viewer expects.
"""
@dataclass(frozen=True, slots=True)
class DumpBoolGrid:
    data: list[bool]
    palette: Palette

@dataclass(frozen=True, slots=True)
class DumpU8Grid:
    data: list[int]
    palette: Palette

@dataclass(frozen=True, slots=True)
class DumpI16Grid:
    data: list[int]
    palette: Palette

@dataclass(frozen=True, slots=True)
class DumpU16Grid:
    data: list[int]
    palette: Palette

@dataclass(frozen=True, slots=True)
class DumpF32Grid:
    data: list[float]
    palette: Palette

@dataclass(frozen=True, slots=True)
class DumpTiles:
    """Unordered set of tiles, rendered as cell rings."""
    data: list[Position]

@dataclass(frozen=True, slots=True)
class DumpTile:
    """
    Single tile rendered as a ring around the cell. `pos = None` renders
    as nothing so callers can dump unconditionally.
    """
    pos: Position | None

@dataclass(frozen=True, slots=True)
class DumpDot:
    """Single tile rendered as a filled coloured dot."""
    pos: Position | None
    colour: Colour

@dataclass(frozen=True, slots=True)
class DumpPath:
    """Ordered list of tiles rendered as a polyline."""
    points: list[Position]
    colour: Colour

@dataclass(frozen=True, slots=True)
class DumpVectorField:
    angles: list[float | None]
    magnitudes: list[float] | None

@dataclass(frozen=True, slots=True)
class DumpScalar:
    """Plain value (int / float / bool / str / None) shown verbatim."""
    value: ScalarValue

type Dump = DumpBoolGrid | DumpU8Grid | DumpI16Grid | DumpU16Grid | DumpF32Grid | DumpTiles | DumpTile | DumpDot | DumpPath | DumpVectorField | DumpScalar

def serialise_palette_t(p):
    stops: list[Value] = list(([s.t, s.colour.as_array()[0], s.colour.as_array()[1], s.colour.as_array()[2], s.colour.as_array()[3]] for s in p.stops))
    special_obj = {}
    for k, c in p.special:
        key = str(k)
        special_obj[key] = [c.as_array()[0], c.as_array()[1], c.as_array()[2], c.as_array()[3]]
    obj = {}
    obj[str("stops")] = stops
    obj[str("special")] = special_obj
    return obj

def pos_xy(p):
    return [p.x, p.y]

def serialise_dump(v):
    """
    Convert a `Dump` value to its tagged dict representation. Mirrors the
    `_serialise_dump` function in the Python source.
    """
    match v:
        case DumpBoolGrid(data=data, palette=palette):
            return {"$type": "boolgrid", "v": data, "palette": serialise_palette_t(palette)}
        case DumpU8Grid(data=data, palette=palette):
            return {"$type": "u8grid", "v": data, "palette": serialise_palette_t(palette)}
        case DumpI16Grid(data=data, palette=palette):
            return {"$type": "i16grid", "v": data, "palette": serialise_palette_t(palette)}
        case DumpU16Grid(data=data, palette=palette):
            return {"$type": "u16grid", "v": data, "palette": serialise_palette_t(palette)}
        case DumpF32Grid(data=data, palette=palette):
            return {"$type": "f32grid", "v": data, "palette": serialise_palette_t(palette)}
        case DumpTiles(data=data):
            return {"$type": "tiles", "v": list((pos_xy(__x) for __x in data))}
        case DumpTile(pos=pos):
            return ({"$type": "tile", "x": p.x, "y": p.y} if (p := pos) is not None else {"$type": "tile", "x": None, "y": None})
        case DumpDot(pos=pos, colour=colour):
            arr = colour.as_array()
            c = [arr[0], arr[1], arr[2], arr[3]]
            match pos:
                case None:
                    return {"$type": "dot", "x": None, "y": None, "colour": c}
                case p if p is not None:
                    return {"$type": "dot", "x": p.x, "y": p.y, "colour": c}
        case DumpPath(points=points, colour=colour):
            arr = colour.as_array()
            return {"$type": "path", "v": list((pos_xy(__x) for __x in points)), "colour": [arr[0], arr[1], arr[2], arr[3]]}
        case DumpVectorField(angles=angles, magnitudes=magnitudes):
            obj = {}
            obj[str("$type")] = "vectorfield"
            obj[str("angles")] = angles
            m = magnitudes
            if m is not None:
                obj[str("magnitudes")] = m
            return obj
        case DumpScalar(value=value):
            match value:
                case ScalarValueInt(_0=i):
                    v = i
                case ScalarValueFloat(_0=f):
                    v = f
                case ScalarValueBool(_0=b):
                    v = b
                case ScalarValueStr(_0=s):
                    v = s
                case ScalarValueNull():
                    v = None
            return {"$type": "scalar", "v": v}

def auto_wrap_position(p):
    """
    Auto-wrap a raw value into a tagged dict for use in `debug()` message args.

    Mirrors the Python `_auto_wrap`. Position values become hoverable cell rings;
    `Dump` values are used as-is; anything else is a scalar.
    """
    return {"$type": "tile", "x": p.x, "y": p.y}

def auto_wrap_scalar(v):
    return serialise_dump(DumpScalar(value=v))

def auto_wrap_dump(d):
    return serialise_dump(d)

class Dumper:
    """
    Per-unit same-elision dump emitter. Mirrors the Python `Dumper` class.

    Holds a per-name cache of the most recently emitted serialised payload.
    `dump(name, value)` either appends a fresh node to the current scope's
    `children`, or emits a `{"$type": "same"}` marker if the payload is
    byte-identical to the last value emitted under `name`.

    The scope stack is owned externally; `Dumper` only mutates the top frame's
    `children` list.
    """
    same_cache: dict[str, Value]

    def __init__(self):
        self.same_cache = {}

    def dump(self, scope_children, name, value):
        """
        Append a vis node to `scope_children`. If the payload equals the last
        value emitted under `name`, write a `{"$type": "same"}` marker so the
        viewer can reuse the previous turn's value.
        """
        payload = serialise_dump(value)
        same = self.same_cache.get(name) == payload
        if not same:
            self.same_cache[str(name)] = list(payload)
        value_field = {"$type": "same"} if same else payload
        node = {"$type": "vis", "name": name, "value": value_field}
        scope_children.append(node)

    @staticmethod
    def default():
        return Dumper()
