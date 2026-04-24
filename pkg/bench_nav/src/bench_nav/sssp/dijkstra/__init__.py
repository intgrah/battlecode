from bench_nav.sssp.dijkstra.dial import DijkstraDialSssp
from bench_nav.sssp.dijkstra.dial_dual import DijkstraDialDual
from bench_nav.sssp.dijkstra.dial_np_dual2 import DijkstraDialNpDual2
from bench_nav.sssp.dijkstra.dial_pnbc import DijkstraDialPnbc
from bench_nav.sssp.dijkstra.dial_skip import DijkstraDialSkip
from bench_nav.sssp.dijkstra.dial_skip_pnbc import DijkstraDialSkipPnbc
from bench_nav.sssp.dijkstra.dial_unrolled import DijkstraDialUnrolled
from bench_nav.sssp.dijkstra.flat import DijkstraFlat
from bench_nav.sssp.dijkstra.flat_prealloc import DijkstraFlatPrealloc
from bench_nav.sssp.dijkstra.heap import DijkstraHeapSssp
from bench_nav.types import Sssp

ALGOS: tuple[type[Sssp], ...] = (
    DijkstraHeapSssp,
    DijkstraDialSssp,
    DijkstraDialDual,
    DijkstraDialNpDual2,
    DijkstraDialPnbc,
    DijkstraDialSkip,
    DijkstraDialSkipPnbc,
    DijkstraDialUnrolled,
    DijkstraFlat,
    DijkstraFlatPrealloc,
)
