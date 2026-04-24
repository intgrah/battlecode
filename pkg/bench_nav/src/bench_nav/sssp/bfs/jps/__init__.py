from bench_nav.sssp.bfs.jps.jps import BfsJps
from bench_nav.sssp.bfs.jps.list import BfsJpsList
from bench_nav.sssp.bfs.jps.list_dbl import BfsJpsListDbl
from bench_nav.sssp.bfs.jps.list_defer import BfsJpsListDefer
from bench_nav.sssp.bfs.jps.list_merge import BfsJpsListMerge
from bench_nav.sssp.bfs.jps.list_merge_off import BfsJpsListMergeOff
from bench_nav.sssp.bfs.jps.list_off import BfsJpsListOff
from bench_nav.types import Sssp

ALGOS: tuple[type[Sssp], ...] = (
    BfsJps,
    BfsJpsList,
    BfsJpsListDbl,
    BfsJpsListDefer,
    BfsJpsListMerge,
    BfsJpsListMergeOff,
    BfsJpsListOff,
)
