from bench_nav.spsp.astar.dial_apsp import AstarDialApsp
from bench_nav.spsp.astar.dial_cheb import AstarDialChebSpsp
from bench_nav.spsp.astar.dial_cheb_bw_dijkstra import AstarDialChebBwDijkstra
from bench_nav.spsp.astar.dial_landmark import AstarDialLandmark
from bench_nav.spsp.astar.dial_precomp import AstarDialPrecomp
from bench_nav.spsp.astar.dial_precomp_lifo import AstarDialPrecompLifo
from bench_nav.spsp.astar.heap_apsp import AstarHeapApsp
from bench_nav.spsp.astar.heap_bfs import AstarHeapBfs
from bench_nav.spsp.astar.heap_cheb import AstarHeapCheb
from bench_nav.spsp.astar.jps import AstarJps
from bench_nav.spsp.astar.jps_dial import AstarJpsDial
from bench_nav.spsp.astar.jps_precomp import AstarJpsPrecomp
from bench_nav.types import Spsp

ALGOS: tuple[type[Spsp], ...] = (
    AstarHeapCheb,
    AstarHeapBfs,
    AstarHeapApsp,
    AstarDialChebSpsp,
    AstarDialApsp,
    AstarDialLandmark,
    AstarDialPrecomp,
    AstarDialPrecompLifo,
    AstarDialChebBwDijkstra,
    AstarJps,
    AstarJpsDial,
    AstarJpsPrecomp,
)
