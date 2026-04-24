from bench_nav.spsp.astar import ALGOS as ASTAR_ALGOS
from bench_nav.spsp.bfs import ALGOS as BFS_ALGOS
from bench_nav.spsp.biastar import ALGOS as BIASTAR_ALGOS
from bench_nav.spsp.bibfs import BiBfs
from bench_nav.spsp.dijkstra import ALGOS as DIJKSTRA_ALGOS
from bench_nav.spsp.gbfs import Gbfs
from bench_nav.spsp.hpastar import HpaStar
from bench_nav.types import Spsp

ALGOS: tuple[type[Spsp], ...] = (
    *BFS_ALGOS,
    BiBfs,
    Gbfs,
    *DIJKSTRA_ALGOS,
    *ASTAR_ALGOS,
    *BIASTAR_ALGOS,
    HpaStar,
)
