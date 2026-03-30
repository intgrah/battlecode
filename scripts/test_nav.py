import random
import sys
import types
from pathlib import Path

_cambc = types.ModuleType("cambc")


class _Env:
    EMPTY = 0
    WALL = 1
    ORE_TITANIUM = 2
    ORE_AXIONITE = 3


class _Pos:
    __slots__ = ("x", "y")

    def __init__(self, x, y) -> None:
        self.x = x
        self.y = y

    def __eq__(self, o):
        return isinstance(o, _Pos) and self.x == o.x and self.y == o.y

    def __hash__(self):
        return hash((self.x, self.y))


class _Dir:
    pass


_cambc.Environment = _Env
_cambc.Position = _Pos
_cambc.Direction = _Dir
sys.modules["cambc"] = _cambc
_util = types.ModuleType("util")
_util.Symmetry = type(
    "S",
    (),
    {
        "ROT": type("S", (), {"name": "ROT"})(),
        "HOR": type("S", (), {"name": "HOR"})(),
        "VER": type("S", (), {"name": "VER"})(),
    },
)()
sys.modules["util"] = _util

from _nav_c import find_path_raw as c_find
from nav import find_path_raw as py_find

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from proto.cambc_pb2 import Map as PbMap

_INF = 1000000


def path_cost(w, cost, path):
    t = 0
    for i in range(len(path) - 1):
        x0, y0 = path[i] % w, path[i] // w
        x1, y1 = path[i + 1] % w, path[i + 1] // w
        c = cost[path[i + 1]]
        if x0 != x1 and y0 != y1:
            c += 1
        t += c
    return t


def main() -> None:
    maps_dir = ROOT / "maps"
    maps = sorted(maps_dir.glob("*.map26"))

    total = 0
    match = 0
    mismatch = 0
    rng = random.Random(42)

    for mf in maps:
        m = PbMap()
        m.ParseFromString(mf.read_bytes())
        w, h = m.width, m.height
        tiles = [t for row in m.rows for t in row.tiles]
        cost = [_INF if t in (1, 2, 3) else 10 for t in tiles]

        passable = [i for i in range(w * h) if cost[i] < _INF]
        if len(passable) < 2:
            continue
        for _ in range(20):
            a, b = rng.choice(passable), rng.choice(passable)
            cost[a] = 2
            cost[b] = 2

        for _ in range(100):
            a, b = rng.choice(passable), rng.choice(passable)
            sx, sy = a % w, a // w
            gx, gy = b % w, b // w

            py_result = py_find(w, h, cost, sx, sy, gx, gy)
            c_result = c_find(w, h, cost, sx, sy, gx, gy)

            total += 1

            if py_result is None and c_result is None:
                match += 1
            elif py_result is not None and c_result is not None:
                if list(py_result) == list(c_result):
                    match += 1
                else:
                    pc = path_cost(w, cost, py_result)
                    cc = path_cost(w, cost, c_result)
                    if pc == cc:
                        match += 1
                    else:
                        mismatch += 1
                        if mismatch <= 5:
                            print(
                                f"  MISMATCH {mf.stem} ({sx},{sy})->({gx},{gy}):"
                                f" py_cost={pc} c_cost={cc}"
                                f" py_len={len(py_result)} c_len={len(c_result)}"
                            )
            else:
                mismatch += 1
                if mismatch <= 5:
                    print(
                        f"  MISMATCH {mf.stem} ({sx},{sy})->({gx},{gy}):"
                        f" py={'path' if py_result else 'None'}"
                        f" c={'path' if c_result else 'None'}"
                    )

    print(f"Total: {total}  Match: {match}  Mismatch: {mismatch}")
    if mismatch == 0:
        print("ALL MATCH")
    else:
        print(f"FAILURES: {mismatch}")


if __name__ == "__main__":
    main()
