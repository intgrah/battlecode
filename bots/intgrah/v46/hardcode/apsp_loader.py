import base64
import zlib

from cambc import Position
from util import Symmetry

from .apsp import APSP


class ApspTable:
    def __init__(
        self, w: int, h: int, sym: Symmetry, data: bytearray, stored: list[int]
    ) -> None:
        self._w = w
        self._h = h
        self._n = w * h
        self._sym = sym
        self._data = data
        self._index_map = {idx: pos for pos, idx in enumerate(stored)}

    def _mirror(self, i: int) -> int:
        x, y = i % self._w, i // self._w
        match self._sym:
            case Symmetry.ROT:
                return (self._h - 1 - y) * self._w + (self._w - 1 - x)
            case Symmetry.HOR:
                return (self._h - 1 - y) * self._w + x
            case Symmetry.VER:
                return y * self._w + (self._w - 1 - x)
        return i

    def dist(self, a: int, b: int) -> int:
        if a in self._index_map:
            row = self._index_map[a]
            return self._data[row * self._n + b]
        ma = self._mirror(a)
        mb = self._mirror(b)
        if ma in self._index_map:
            row = self._index_map[ma]
            return self._data[row * self._n + mb]
        return 255


_cache: dict[tuple[int, int, Position], ApspTable] = {}


def get_apsp(w: int, h: int, core_a: Position) -> ApspTable | None:
    key = (w, h, core_a)
    if key in _cache:
        return _cache[key]
    entry = APSP.get(key)
    if entry is None:
        return None
    sym, data_b64, stored_b64 = entry
    data = bytearray(zlib.decompress(base64.b64decode(data_b64)))
    stored_raw = zlib.decompress(base64.b64decode(stored_b64))
    stored = [
        int.from_bytes(stored_raw[i : i + 2], "little")
        for i in range(0, len(stored_raw), 2)
    ]
    table = ApspTable(w, h, sym, data, stored)
    _cache[key] = table
    return table
