from bench_nav.stepped.bug.bug0 import Bug0
from bench_nav.stepped.bug.bug1 import Bug1
from bench_nav.stepped.bug.bug2 import Bug2
from bench_nav.stepped.bug.bug2_bounded import Bug2Bounded
from bench_nav.stepped.bug.distbug import DistBug
from bench_nav.stepped.bug.fast_bug import FastBug
from bench_nav.stepped.bug.lookahead_bug import LookaheadBug
from bench_nav.stepped.bug.step_bug import StepBug
from bench_nav.stepped.bug.tangentbug import TangentBug
from bench_nav.stepped.bug.visbug21 import VisBug21
from bench_nav.stepped.bug.visbug22 import VisBug22
from bench_nav.types import Stepped

ALGOS: tuple[type[Stepped], ...] = (
    Bug0,
    Bug1,
    Bug2,
    Bug2Bounded,
    DistBug,
    TangentBug,
    VisBug21,
    VisBug22,
    FastBug,
    StepBug,
    LookaheadBug,
)
