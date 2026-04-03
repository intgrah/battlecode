from util import Symmetry


class ApspTable:
    def __init__(self, w: int, h: int, sym: Symmetry, data: bytes) -> None:
        self._w = w
        self._h = h
        self._n = w * h
        self._sym = sym
        self._data = data
        self._half_w = (w + 1) // 2
        self._half_h = (h + 1) // 2
        self._half_n = (w * h + 1) // 2

    def _mirror(self, i: int) -> int:
        match self._sym:
            case Symmetry.ROT:
                return self._n - 1 - i
            case Symmetry.HOR:
                x, y = i % self._w, i // self._w
                return (self._h - 1 - y) * self._w + x
            case Symmetry.VER:
                x, y = i % self._w, i // self._w
                return y * self._w + (self._w - 1 - x)

    def _row(self, i: int) -> int:
        match self._sym:
            case Symmetry.ROT | Symmetry.HOR:
                return i
            case Symmetry.VER:
                x, y = i % self._w, i // self._w
                return y * self._half_w + x

    def _is_stored(self, i: int) -> bool:
        match self._sym:
            case Symmetry.ROT:
                return i < self._half_n
            case Symmetry.HOR:
                return i // self._w < self._half_h
            case Symmetry.VER:
                return i % self._w < self._half_w

    def dist(self, a: int, b: int) -> int:
        if self._is_stored(a):
            return self._data[self._row(a) * self._n + b]
        ma = self._mirror(a)
        mb = self._mirror(b)
        return self._data[self._row(ma) * self._n + mb]
