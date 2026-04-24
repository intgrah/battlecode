from bench_nav.sssp.bellman_ford import BellmanFord
from bench_nav.sssp.bfs import ALGOS as BFS_ALGOS
from bench_nav.sssp.bfs_bitmap import BfsBitmap
from bench_nav.sssp.bfs_buckets import BfsBuckets
from bench_nav.sssp.bfs_expand import BfsExpand
from bench_nav.sssp.dijkstra import ALGOS as DIJKSTRA_ALGOS
from bench_nav.sssp.spfa_slf import SpfaSlf
from bench_nav.types import Sssp

ALGOS: tuple[type[Sssp], ...] = (
    *BFS_ALGOS,
    BfsBuckets,
    BfsExpand,
    BfsBitmap,
    BellmanFord,
    SpfaSlf,
    *DIJKSTRA_ALGOS,
)
