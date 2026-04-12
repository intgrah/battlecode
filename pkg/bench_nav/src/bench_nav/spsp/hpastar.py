from __future__ import annotations

from typing import TYPE_CHECKING

from bench_nav.hpastar import GatewayGraph

if TYPE_CHECKING:
    from bench_nav.common import Path_
    from bench_nav.map_data import MapData


def precompute_hpa(md: MapData) -> None:
    def tile_cost(x: int, y: int) -> int:
        return md.cost[y * md.w + x]

    md.hpa_graph = GatewayGraph(md.w, md.h, tile_cost, cluster_size=7)


def spsp_hpastar(md: MapData, si: int, gi: int) -> Path_:
    assert md.hpa_graph is not None
    sx, sy = si % md.w, si // md.w
    gx, gy = gi % md.w, gi // md.w
    return md.hpa_graph.find_path(sx, sy, gx, gy)
