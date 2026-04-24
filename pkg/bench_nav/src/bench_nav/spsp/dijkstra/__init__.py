from bench_nav.spsp.dijkstra.dial import DijkstraDial
from bench_nav.spsp.dijkstra.dial_dual import DijkstraDialDual
from bench_nav.spsp.dijkstra.heap import DijkstraHeapSpsp
from bench_nav.types import Spsp

ALGOS: tuple[type[Spsp], ...] = (
    DijkstraHeapSpsp,
    DijkstraDial,
    DijkstraDialDual,
)
