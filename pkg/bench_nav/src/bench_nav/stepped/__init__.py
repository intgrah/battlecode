from bench_nav.stepped.astar import AstarStepped
from bench_nav.stepped.bfs import (
    Bfs8Cost,
    Bfs8Hop,
    Bfs8Raw,
    BfsFdCost,
    BfsFdHop,
    BfsFdRaw,
)
from bench_nav.stepped.bug import ALGOS as BUG_ALGOS
from bench_nav.stepped.jps import JpsStepped
from bench_nav.types import Stepped

ALGOS: tuple[type[Stepped], ...] = (
    AstarStepped,
    BfsFdRaw,
    BfsFdHop,
    BfsFdCost,
    Bfs8Raw,
    Bfs8Hop,
    Bfs8Cost,
    JpsStepped,
    *BUG_ALGOS,
)
