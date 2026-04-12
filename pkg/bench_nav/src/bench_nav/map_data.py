from __future__ import annotations

import heapq
from pathlib import Path
from typing import TYPE_CHECKING

from proto.cambc_pb2 import Map

from bench_nav.common import CE, CR, DIR8, INF

if TYPE_CHECKING:
    from bench_nav.hpastar import GatewayGraph
    from bench_nav.spsp.apsp import ApspTable


def load_map(path: str | Path) -> Map:
    m = Map()
    m.ParseFromString(Path(path).read_bytes())
    return m


class MapData:
    """
    Different algorithms require different precomputed values. Some of these are doable incrementally.
    """

    __slots__ = (
        "apsp",
        "bfs_h_cache",
        "cost",
        "h",
        "hpa_graph",
        "n",
        "name",
        "nb",
        "offsets_card",
        "offsets_diag",
        "passable",
        "pnb",
        "pnb1",
        "pnb3",
        "pnb_navbfs_push",
        "pnb_navbfs_set",
        "pnbc",
        "tiles",
        "w",
    )

    @staticmethod
    def build_nb(w: int, h: int) -> list[list[int]]:
        """Neighbours, including walls"""
        n = w * h
        nb: list[list[int]] = [[] for _ in range(n)]
        for i in range(n):
            cx, cy = i % w, i // w
            for dx, dy in DIR8:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h:
                    nb[i].append(ny * w + nx)
        return nb

    @staticmethod
    def build_pnb(nb: list[list[int]], cost: list[int]) -> list[list[int]]:
        """Passable neighbours, excluding walls"""
        return [[ni for ni in nb[i] if cost[ni] < INF] for i in range(len(nb))]

    @staticmethod
    def build_pnbc(nb: list[list[int]], cost: list[int]) -> list[list[tuple[int, int]]]:
        """Passable neighbours, excluding walls, also bundling the edge cost"""
        return [
            [(ni, cost[ni]) for ni in nb[i] if cost[ni] < INF] for i in range(len(nb))
        ]

    @staticmethod
    def build_pnb_navbfs(
        w: int, h: int, cost: list[int]
    ) -> tuple[list[list[int]], list[list[int]]]:
        """Split passable neighbours into push (always enqueue) and set (no enqueue).

        Cardinals can be in `set` (visited via diagonal expansion) when both
        bracketing diagonals are passable; otherwise they go in `push`. All
        diagonals always go in `push`.
        """
        n = w * h
        push: list[list[int]] = [[] for _ in range(n)]
        aset: list[list[int]] = [[] for _ in range(n)]
        for i in range(n):
            if cost[i] >= INF:
                continue
            cx, cy = i % w, i // w
            # Booleans for each of the 4 diagonals
            has_ne = cy > 0 and cx < w - 1 and cost[(cy - 1) * w + (cx + 1)] < INF
            has_se = cy < h - 1 and cx < w - 1 and cost[(cy + 1) * w + (cx + 1)] < INF
            has_sw = cy < h - 1 and cx > 0 and cost[(cy + 1) * w + (cx - 1)] < INF
            has_nw = cy > 0 and cx > 0 and cost[(cy - 1) * w + (cx - 1)] < INF
            if has_ne:
                push[i].append((cy - 1) * w + (cx + 1))
            if has_se:
                push[i].append((cy + 1) * w + (cx + 1))
            if has_sw:
                push[i].append((cy + 1) * w + (cx - 1))
            if has_nw:
                push[i].append((cy - 1) * w + (cx - 1))
            # Cardinals
            if cy > 0 and cost[(cy - 1) * w + cx] < INF:  # N
                (aset if has_ne and has_nw else push)[i].append((cy - 1) * w + cx)
            if cx < w - 1 and cost[cy * w + (cx + 1)] < INF:  # E
                (aset if has_ne and has_se else push)[i].append(cy * w + (cx + 1))
            if cy < h - 1 and cost[(cy + 1) * w + cx] < INF:  # S
                (aset if has_se and has_sw else push)[i].append((cy + 1) * w + cx)
            if cx > 0 and cost[cy * w + (cx - 1)] < INF:  # W
                (aset if has_sw and has_nw else push)[i].append(cy * w + (cx - 1))
        return push, aset

    @staticmethod
    def build_pnb_dual(
        nb: list[list[int]], cost: list[int]
    ) -> tuple[list[list[int]], list[list[int]]]:
        n = len(nb)
        pnb1: list[list[int]] = [[] for _ in range(n)]
        pnb3: list[list[int]] = [[] for _ in range(n)]
        for i in range(n):
            for ni in nb[i]:
                c = cost[ni]
                if c == CR:
                    pnb1[i].append(ni)
                elif c == CE:
                    pnb3[i].append(ni)
        return pnb1, pnb3

    def __init__(self, map_path: Path) -> None:
        self.name: str = map_path.stem
        m = load_map(map_path)
        self.tiles: list[int] = [tile for row in m.rows for tile in row.tiles]
        self.w = m.width
        self.h = m.height
        self.n: int = self.w * self.h
        self.cost: list[int] = [
            INF if self.tiles[i] in (1, 2, 3) else CE for i in range(self.n)
        ]
        self.nb: list[list[int]] = MapData.build_nb(self.w, self.h)
        self.pnb: list[list[int]] = MapData.build_pnb(self.nb, self.cost)
        self.pnbc: list[list[tuple[int, int]]] = MapData.build_pnbc(self.nb, self.cost)
        self.pnb1: list[list[int]]
        self.pnb3: list[list[int]]
        self.pnb1, self.pnb3 = MapData.build_pnb_dual(self.nb, self.cost)
        self.pnb_navbfs_push: list[list[int]]
        self.pnb_navbfs_set: list[list[int]]
        self.pnb_navbfs_push, self.pnb_navbfs_set = MapData.build_pnb_navbfs(
            self.w,
            self.h,
            self.cost,
        )
        self.passable: list[int] = [i for i in range(self.n) if self.cost[i] < INF]
        self.offsets_card: tuple[int, ...] = (-self.w, -1, 1, self.w)
        w = self.w
        self.offsets_diag: tuple[int, ...] = (-w - 1, -w + 1, w - 1, w + 1)
        self.apsp: ApspTable | None = None
        self.hpa_graph: GatewayGraph | None = None
        self.bfs_h_cache: dict[int, list[int]] = {}

    def reset_cost_no_roads(self) -> None:
        self.cost = [INF if self.tiles[i] in (1, 2, 3) else CE for i in range(self.n)]
        self.pnb = MapData.build_pnb(self.nb, self.cost)
        self.pnbc = MapData.build_pnbc(self.nb, self.cost)
        self.pnb1, self.pnb3 = MapData.build_pnb_dual(self.nb, self.cost)
        self.pnb_navbfs_push, self.pnb_navbfs_set = MapData.build_pnb_navbfs(
            self.w,
            self.h,
            self.cost,
        )
        self.passable = [i for i in range(self.n) if self.cost[i] < INF]
        self.hpa_graph = None
        self.bfs_h_cache = {}

    def place_roads(self) -> int:
        n, nb = self.n, self.nb
        cost = self.cost
        tiles = self.tiles
        ores: list[int] = [i for i in range(n) if tiles[i] in (2, 3)]
        ore_adj: set[int] = set()
        for oi in ores:
            for ni in nb[oi]:
                if cost[ni] < INF:
                    ore_adj.add(ni)
        targets = list(ore_adj)[:5]
        core_i = self.passable[0] if self.passable else 0
        roads: set[int] = set()
        for target in targets:
            dist: list[int] = [INF] * n
            parent: list[int] = [-1] * n
            dist[core_i] = 0
            heap: list[tuple[int, int]] = [(0, core_i)]
            while heap:
                d, node = heapq.heappop(heap)
                if d > dist[node]:
                    continue
                if node == target:
                    break
                for ni in nb[node]:
                    c = cost[ni]
                    if c >= INF:
                        continue
                    nd = d + c
                    if nd < dist[ni]:
                        dist[ni] = nd
                        parent[ni] = node
                        heapq.heappush(heap, (nd, ni))
            if dist[target] < INF:
                cur = target
                while cur not in (-1, core_i):
                    roads.add(cur)
                    cur = parent[cur]
        for ri in roads:
            cost[ri] = CR
        self.pnb = MapData.build_pnb(self.nb, cost)
        self.pnbc = MapData.build_pnbc(self.nb, cost)
        self.pnb1, self.pnb3 = MapData.build_pnb_dual(self.nb, cost)
        self.pnb_navbfs_push, self.pnb_navbfs_set = MapData.build_pnb_navbfs(
            self.w,
            self.h,
            cost,
        )
        self.passable = [i for i in range(n) if cost[i] < INF]
        self.hpa_graph = None
        self.bfs_h_cache = {}
        return len(roads)
