from __future__ import annotations

from collections.abc import Callable

from bench_nav.common import Path_
from bench_nav.map_data import MapData
from bench_nav.spsp.apsp import spsp_astar_heap_apsp
from bench_nav.spsp.astar import (
    spsp_astar_dial_bfs,
    spsp_astar_dial_cheb,
    spsp_astar_heap_cheb,
)
from bench_nav.spsp.bfs import (
    spsp_bfs,
    spsp_bfs_expand,
    spsp_bfs_roadopt,
    spsp_bibfs,
    spsp_navbfs,
    spsp_navbfs_noextract,
)
from bench_nav.spsp.biastar import (
    spsp_astar_dial_cheb_bw_dijkstra,
    spsp_biastar_dial_cheb,
    spsp_biastar_dial_cheb_ft,
)
from bench_nav.spsp.dijkstra import (
    spsp_dijkstra_dial,
    spsp_dijkstra_dial_np,
    spsp_dijkstra_dial_np2,
    spsp_dijkstra_dial_np_dual,
    spsp_dijkstra_dial_np_dual2,
    spsp_dijkstra_dial_np_dual3,
    spsp_dijkstra_dial_np_dual4,
    spsp_dijkstra_heap,
)
from bench_nav.spsp.gbfs import spsp_gbfs
from bench_nav.spsp.hpastar import spsp_hpastar
from bench_nav.sssp.bfs import sssp_bfs, sssp_bfs_expand
from bench_nav.sssp.dijkstra import (
    sssp_dijkstra_dial,
    sssp_dijkstra_dial_inline,
    sssp_dijkstra_dial_np,
    sssp_dijkstra_dial_np2,
    sssp_dijkstra_dial_np5,
    sssp_dijkstra_dial_np_beacon,
    sssp_dijkstra_dial_np_dual,
    sssp_dijkstra_dial_np_dual2,
    sssp_dijkstra_dial_np_dual3,
    sssp_dijkstra_dial_np_dual4,
    sssp_dijkstra_dial_np_dual5,
    sssp_dijkstra_dial_pnbc,
    sssp_dijkstra_heap,
)

type AlgoFn = Callable[[MapData, int, int], Path_]
type AlgoEntry = tuple[str, AlgoFn, bool]
type SsspFn = Callable[[MapData, int], list[int]]


def _make_algos() -> list[AlgoEntry]:
    algos: list[AlgoEntry] = []

    algos.extend(
        (
            f"astar-heap-cheb{w}",
            lambda md, si, gi, _w=w: spsp_astar_heap_cheb(md, si, gi, weight=_w),
            False,
        )
        for w in [1, 3]
    )

    algos.extend(
        (
            f"astar-dial-cheb{w}",
            lambda md, si, gi, _w=w: spsp_astar_dial_cheb(md, si, gi, weight=_w),
            False,
        )
        for w in [1, 3]
    )

    algos.append(("astar-heap-apsp", spsp_astar_heap_apsp, True))
    algos.append(("bfs", spsp_bfs, False))
    algos.append(("bfs-expand", spsp_bfs_expand, False))
    algos.append(("bfs-roadopt", spsp_bfs_roadopt, False))
    algos.append(("navbfs", spsp_navbfs, False))
    algos.append(("navbfs-noextract", spsp_navbfs_noextract, False))
    algos.append(("bibfs", spsp_bibfs, False))
    algos.append(("gbfs", spsp_gbfs, False))
    algos.append(("dijkstra-heap", spsp_dijkstra_heap, False))
    algos.append(("dijkstra-dial", spsp_dijkstra_dial, False))
    algos.append(("dijkstra-dial-np", spsp_dijkstra_dial_np, False))
    algos.append(("dijkstra-dial-np-dual", spsp_dijkstra_dial_np_dual, False))
    algos.append(("dijkstra-dial-np-dual2", spsp_dijkstra_dial_np_dual2, False))
    algos.append(("dijkstra-dial-np2", spsp_dijkstra_dial_np2, False))
    algos.append(("dijkstra-dial-np-dual3", spsp_dijkstra_dial_np_dual3, False))
    algos.append(("dijkstra-dial-np-dual4", spsp_dijkstra_dial_np_dual4, False))
    algos.append(("hpastar", spsp_hpastar, True))
    algos.append(("astar-dial-bfs", spsp_astar_dial_bfs, False))

    algos.append(("biastar-dial-cheb", spsp_biastar_dial_cheb, False))
    algos.append(("biastar-dial-cheb-ft", spsp_biastar_dial_cheb_ft, False))
    algos.append(("astar-cheb+bw-dijkstra", spsp_astar_dial_cheb_bw_dijkstra, False))

    return algos


ALGOS: list[AlgoEntry] = _make_algos()


SSSP_ALGOS: list[tuple[str, SsspFn]] = [
    ("bfs", sssp_bfs),
    ("bfs-expand", sssp_bfs_expand),
    ("dijkstra-heap", sssp_dijkstra_heap),
    ("dijkstra-dial", sssp_dijkstra_dial),
    ("dijkstra-dial-inline", sssp_dijkstra_dial_inline),
    ("dijkstra-dial-pnbc", sssp_dijkstra_dial_pnbc),
    ("dijkstra-dial-np", sssp_dijkstra_dial_np),
    ("dijkstra-dial-np-dual", sssp_dijkstra_dial_np_dual),
    ("dijkstra-dial-np-dual2", sssp_dijkstra_dial_np_dual2),
    ("dijkstra-dial-np2", sssp_dijkstra_dial_np2),
    ("dijkstra-dial-np-beacon", sssp_dijkstra_dial_np_beacon),
    ("dijkstra-dial-np-dual3", sssp_dijkstra_dial_np_dual3),
    ("dijkstra-dial-np-dual4", sssp_dijkstra_dial_np_dual4),
    ("dijkstra-dial-np5", sssp_dijkstra_dial_np5),
    ("dijkstra-dial-np-dual5", sssp_dijkstra_dial_np_dual5),
]
