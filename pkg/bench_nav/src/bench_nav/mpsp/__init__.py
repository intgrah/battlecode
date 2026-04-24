from bench_nav.mpsp.astar_jps_mpsp import AstarJpsMpsp
from bench_nav.types import Mpsp

ALGOS: tuple[type[Mpsp], ...] = (AstarJpsMpsp,)
