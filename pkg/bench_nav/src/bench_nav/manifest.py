from __future__ import annotations

from typing import TYPE_CHECKING, Final

from bench_nav.spsp import astar_dial_cheb as spsp_astar_dial_cheb
from bench_nav.spsp import bfs as spsp_bfs
from bench_nav.spsp import dijkstra_heap as spsp_dijkstra_heap
from bench_nav.sssp import bfs as sssp_bfs
from bench_nav.sssp import dijkstra_dial as sssp_dijkstra_dial
from bench_nav.sssp import dijkstra_heap as sssp_dijkstra_heap

if TYPE_CHECKING:
    from bench_nav.types import SequentialSpspAlgo, SsspAlgo

SPSP_ALGOS: Final[tuple[SequentialSpspAlgo[object], ...]] = (
    spsp_bfs.ALGO,
    spsp_dijkstra_heap.ALGO,
    spsp_astar_dial_cheb.ALGO,
)

SSSP_ALGOS: Final[tuple[SsspAlgo, ...]] = (
    sssp_bfs.ALGO,
    sssp_dijkstra_heap.ALGO,
    sssp_dijkstra_dial.ALGO,
)
