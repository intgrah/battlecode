from bench_nav.sssp.bfs.alloc import BfsAlloc
from bench_nav.sssp.bfs.bfs import Bfs
from bench_nav.sssp.bfs.jps import ALGOS as JPS_ALGOS
from bench_nav.sssp.bfs.skip import BfsSkip
from bench_nav.sssp.bfs.skip_alloc import BfsSkipAlloc
from bench_nav.sssp.bfs.skip_swap import BfsSkipSwap
from bench_nav.sssp.bfs.skip_unrolled import BfsSkipUnrolled
from bench_nav.sssp.bfs.swap import BfsSwap
from bench_nav.sssp.bfs.unrolled import BfsUnrolled
from bench_nav.types import Sssp

ALGOS: tuple[type[Sssp], ...] = (
    Bfs,
    BfsAlloc,
    BfsSwap,
    BfsUnrolled,
    BfsSkip,
    BfsSkipAlloc,
    BfsSkipSwap,
    BfsSkipUnrolled,
    *JPS_ALGOS,
)
