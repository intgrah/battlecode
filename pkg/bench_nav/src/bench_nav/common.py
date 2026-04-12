from __future__ import annotations

from pathlib import Path
from typing import Final

INF: Final[int] = 1_000_000
CR: Final[int] = 1
CE: Final[int] = 3
DIR8: Final[tuple[tuple[int, int], ...]] = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)

N_PAIRS: Final[int] = 1000
SEED: Final[int] = 42

SCENARIOS: Final[tuple[str, ...]] = ("no_roads", "with_roads")

type Path_ = list[int] | None


def find_maps_dir() -> Path:
    d = Path(__file__).resolve().parent
    while d != d.parent:
        candidate = d / "maps"
        if candidate.is_dir():
            return candidate
        d = d.parent
    msg = "Could not find maps/ directory"
    raise FileNotFoundError(msg)


MAPS_DIR: Path = find_maps_dir()


def extract_parent(parent: list[int], si: int, node: int) -> Path_:
    if parent[node] == -1 and node != si:
        return None
    path: list[int] = []
    cur = node
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path
