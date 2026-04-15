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


def extract_parent(parent: list[int], start: int, node: int) -> Path_:
    path: list[int] = []
    cur = node
    while cur != start:
        path.append(cur)
        cur = parent[cur]
        if cur == -1:
            return None
    path.append(start)
    path.reverse()
    return path


def extract_dist(
    dist: list[int], cost: list[int], pnb: list[list[int]], start: int, goal: int
) -> Path_:
    if dist[goal] >= INF:
        return None
    path = [goal]
    cur = goal
    while cur != start:
        d = dist[cur]
        for nb in pnb[cur]:
            if dist[nb] + cost[cur] == d:
                path.append(nb)
                cur = nb
                break
        else:
            return None
    path.reverse()
    return path


def bfs_dist(n: int, pnb: list[list[int]], start: int) -> list[int]:
    dist = [INF] * n
    dist[start] = 0
    q = [start]
    append = q.append
    for node in q:
        d1 = dist[node] + 1
        for nb in pnb[node]:
            if dist[nb] is INF:
                dist[nb] = d1
                append(nb)
    return dist
