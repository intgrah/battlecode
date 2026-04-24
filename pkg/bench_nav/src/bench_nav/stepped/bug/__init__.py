from bench_nav.stepped.bug.bfsbug import BfsBug
from bench_nav.stepped.bug.bug0 import Bug0
from bench_nav.stepped.bug.bug1 import Bug1, Bug1Los
from bench_nav.stepped.bug.bug2 import Bug2
from bench_nav.stepped.bug.distbug import DistBug
from bench_nav.stepped.bug.fast_bug import FastBug
from bench_nav.stepped.bug.lookahead_bug import LookaheadBug, LookaheadBugFullMap
from bench_nav.stepped.bug.mem_astar import MemAstar
from bench_nav.stepped.bug.mem_bfs import MemBfs
from bench_nav.stepped.bug.pruned_bug import (
    PrunedBestB1B2,
    PrunedBestB1Db,
    PrunedBestOf3,
    PrunedBug1,
    PrunedBug2,
    PrunedDistBug,
)
from bench_nav.stepped.bug.step_bug import StepBug
from bench_nav.stepped.bug.tangentbug import TangentBug
from bench_nav.stepped.bug.visbug21 import VisBug21
from bench_nav.stepped.bug.visbug22 import VisBug22
from bench_nav.types import Stepped

ALGOS: tuple[type[Stepped], ...] = (
    Bug0,
    Bug1,
    Bug1Los,
    Bug2,
    DistBug,
    TangentBug,
    VisBug21,
    VisBug22,
    BfsBug,
    MemBfs,
    MemAstar,
    FastBug,
    StepBug,
    PrunedBug1,
    PrunedBug2,
    PrunedDistBug,
    PrunedBestB1B2,
    PrunedBestB1Db,
    PrunedBestOf3,
    LookaheadBug,
    LookaheadBugFullMap,
)
