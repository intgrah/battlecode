from bench_nav.spsp.biastar.dial_cheb import BiastarDialCheb
from bench_nav.spsp.biastar.dial_cheb_ft import BiastarDialChebFt
from bench_nav.types import Spsp

ALGOS: tuple[type[Spsp], ...] = (
    BiastarDialCheb,
    BiastarDialChebFt,
)
