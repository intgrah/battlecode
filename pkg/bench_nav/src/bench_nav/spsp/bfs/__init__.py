from bench_nav.spsp.bfs.bfs import BfsSpsp
from bench_nav.spsp.bfs.bfs_01 import Bfs01
from bench_nav.spsp.bfs.bfs_dist import BfsDist
from bench_nav.spsp.bfs.bfs_expand import BfsExpand
from bench_nav.spsp.bfs.bfs_roadopt import BfsRoadopt
from bench_nav.spsp.bfs.skip import BfsSkip
from bench_nav.spsp.bfs.skip_swap import BfsSkipSwap
from bench_nav.types import Spsp

ALGOS: tuple[type[Spsp], ...] = (
    BfsSpsp,
    Bfs01,
    BfsDist,
    BfsExpand,
    BfsRoadopt,
    BfsSkip,
    BfsSkipSwap,
)
