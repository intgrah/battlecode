from __future__ import annotations

import random
from typing import Final

from bench_nav.types import SequentialQuery, SsspQuery

DEFAULT_SEED: Final = 42


def sssp_queries(passable: list[int], n: int, seed: int) -> tuple[SsspQuery, ...]:
    rng = random.Random(seed)
    return tuple(SsspQuery(start=rng.choice(passable)) for _ in range(n))


def spsp_queries(passable: list[int], n: int, seed: int) -> tuple[SequentialQuery, ...]:
    rng = random.Random(seed)
    return tuple(
        SequentialQuery(
            start=rng.choice(passable),
            goals=(rng.choice(passable),),
        )
        for _ in range(n)
    )


def multi_waypoint_queries(
    passable: list[int],
    n_queries: int,
    n_waypoints: int,
    seed: int,
) -> tuple[SequentialQuery, ...]:
    rng = random.Random(seed)
    return tuple(
        SequentialQuery(
            start=rng.choice(passable),
            goals=tuple(rng.choice(passable) for _ in range(n_waypoints)),
        )
        for _ in range(n_queries)
    )
