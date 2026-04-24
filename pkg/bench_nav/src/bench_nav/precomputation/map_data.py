import heapq
from pathlib import Path

from proto.cambc_pb2 import Map

from bench_nav.common import CE, CR, DIR8, INF


def load_map(path: str | Path) -> Map:
    m = Map()
    m.ParseFromString(Path(path).read_bytes())
    return m


def build_cost(tiles: list[int], n: int) -> list[int]:
    return [INF if tiles[i] in (1, 2, 3) else CE for i in range(n)]


def build_nb(w: int, h: int) -> list[list[int]]:
    n = w * h
    nb: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        cx, cy = i % w, i // w
        for dx, dy in DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                nb[i].append(ny * w + nx)
    return nb


def build_pnb(nb: list[list[int]], cost: list[int]) -> list[list[int]]:
    return [[ni for ni in nb[i] if cost[ni] < INF] for i in range(len(nb))]


def build_pnbc(nb: list[list[int]], cost: list[int]) -> list[list[tuple[int, int]]]:
    return [[(ni, cost[ni]) for ni in nb[i] if cost[ni] < INF] for i in range(len(nb))]


def build_pnb_skip(
    w: int, h: int, cost: list[int]
) -> tuple[list[list[int]], list[list[int]]]:
    n = w * h
    push: list[list[int]] = [[] for _ in range(n)]
    aset: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        if cost[i] >= INF:
            continue
        cx, cy = i % w, i // w
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
        if cy > 0 and cost[(cy - 1) * w + cx] < INF:  # N
            (aset if has_ne and has_nw else push)[i].append((cy - 1) * w + cx)
        if cx < w - 1 and cost[cy * w + (cx + 1)] < INF:  # E
            (aset if has_ne and has_se else push)[i].append(cy * w + (cx + 1))
        if cy < h - 1 and cost[(cy + 1) * w + cx] < INF:  # S
            (aset if has_se and has_sw else push)[i].append((cy + 1) * w + cx)
        if cx > 0 and cost[cy * w + (cx - 1)] < INF:  # W
            (aset if has_sw and has_nw else push)[i].append(cy * w + (cx - 1))
    return push, aset


def build_pnbc_navdijkstra(
    w: int, h: int, cost: list[int]
) -> tuple[list[list[tuple[int, int]]], list[list[tuple[int, int]]]]:
    """Weighted push/set with costs: (nb, cost[nb]) tuples."""
    push, aset = build_pnb_navdijkstra(w, h, cost)
    push_c = [[(nb, cost[nb]) for nb in push[i]] for i in range(len(push))]
    set_c = [[(nb, cost[nb]) for nb in aset[i]] for i in range(len(aset))]
    return push_c, set_c


def build_pnb_navdijkstra(
    w: int, h: int, cost: list[int]
) -> tuple[list[list[int]], list[list[int]]]:
    """Weighted variant: skip cardinal N only when cost[N] >= max(cost[D1], cost[D2])."""
    n = w * h
    push: list[list[int]] = [[] for _ in range(n)]
    aset: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        if cost[i] >= INF:
            continue
        cx, cy = i % w, i // w
        ne = (cy - 1) * w + (cx + 1) if cy > 0 and cx < w - 1 else -1
        se = (cy + 1) * w + (cx + 1) if cy < h - 1 and cx < w - 1 else -1
        sw = (cy + 1) * w + (cx - 1) if cy < h - 1 and cx > 0 else -1
        nw = (cy - 1) * w + (cx - 1) if cy > 0 and cx > 0 else -1
        has_ne = ne != -1 and cost[ne] < INF
        has_se = se != -1 and cost[se] < INF
        has_sw = sw != -1 and cost[sw] < INF
        has_nw = nw != -1 and cost[nw] < INF
        if has_ne:
            push[i].append(ne)
        if has_se:
            push[i].append(se)
        if has_sw:
            push[i].append(sw)
        if has_nw:
            push[i].append(nw)
        if cy > 0 and cost[(cy - 1) * w + cx] < INF:  # N
            ni = (cy - 1) * w + cx
            skip = has_ne and has_nw and cost[ni] >= max(cost[ne], cost[nw])
            (aset if skip else push)[i].append(ni)
        if cx < w - 1 and cost[cy * w + (cx + 1)] < INF:  # E
            ni = cy * w + (cx + 1)
            skip = has_ne and has_se and cost[ni] >= max(cost[ne], cost[se])
            (aset if skip else push)[i].append(ni)
        if cy < h - 1 and cost[(cy + 1) * w + cx] < INF:  # S
            ni = (cy + 1) * w + cx
            skip = has_se and has_sw and cost[ni] >= max(cost[se], cost[sw])
            (aset if skip else push)[i].append(ni)
        if cx > 0 and cost[cy * w + (cx - 1)] < INF:  # W
            ni = cy * w + (cx - 1)
            skip = has_sw and has_nw and cost[ni] >= max(cost[sw], cost[nw])
            (aset if skip else push)[i].append(ni)
    return push, aset


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


def place_roads(
    tiles: list[int],
    cost: list[int],
    nb: list[list[int]],
    passable: list[int],
) -> int:
    n = len(tiles)
    ores: list[int] = [i for i in range(n) if tiles[i] in (2, 3)]
    ore_adj: set[int] = set()
    for oi in ores:
        for ni in nb[oi]:
            if cost[ni] < INF:
                ore_adj.add(ni)
    targets = list(ore_adj)[:5]
    core_i = passable[0] if passable else 0
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
    return len(roads)


def build_pnb_by_offset(w: int, h: int, cost: list[int]) -> list[list[list[int]]]:
    """pnb_by_offset[nb][offset] = push list when arriving at nb from given offset.

    Uses Python negative indexing; list size w+3 accommodates all 8 offsets uniquely.
    Slot 0 reserved for entry_dir=8 (start): neither a valid positive nor negative offset.
    """
    pnb_dir = build_pnb_dir(w, h, cost)
    size = w + 3
    n = w * h
    out: list[list[list[int]]] = [[[] for _ in range(size)] for _ in range(n)]
    offset_to_dir = {
        -w - 1: 7,
        -w: 0,
        -w + 1: 1,
        -1: 6,
        1: 2,
        w - 1: 5,
        w: 4,
        w + 1: 3,
    }
    for nb in range(n):
        for off, d in offset_to_dir.items():
            out[nb][off] = pnb_dir[nb][d]
        out[nb][0] = pnb_dir[nb][8]  # slot 0 unused by offsets; use for start
    return out


def build_dir_of_offset(w: int) -> list[int]:
    """Negative-indexed: dir_of_offset[nb - node] = DIR8 index.

    Table size w+3; Python's negative indexing accommodates the 4 negative offsets.
    """
    size = w + 3
    table = [0] * size
    offset_to_dir = {
        -w - 1: 7,
        -w: 0,
        -w + 1: 1,
        -1: 6,
        1: 2,
        w - 1: 5,
        w: 4,
        w + 1: 3,
    }
    for off, d in offset_to_dir.items():
        table[off] = d
    return table


def build_pnb_dir(w: int, h: int, cost: list[int]) -> list[list[list[int]]]:
    """Classic JPS pruning for Chebyshev 8-connected uniform cost.

    pnb_dir[node][entry_dir]: list of neighbors to push.
    - Cardinal arrival: push continuation + forced diagonals.
    - Diagonal arrival: push continuation diagonal + 2 component cardinals + forced diagonals.
    - entry_dir == 8 (start): push all passable neighbors.
    """
    n = w * h
    pnb_dir: list[list[list[int]]] = [[[] for _ in range(9)] for _ in range(n)]

    for i in range(n):
        if cost[i] >= INF:
            continue
        cx, cy = i % w, i // w

        nbrs: list[int] = []
        for dx, dy in DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and cost[ny * w + nx] < INF:
                nbrs.append(ny * w + nx)
            else:
                nbrs.append(-1)

        for k in range(8):
            if nbrs[k] != -1:
                pnb_dir[i][8].append(nbrs[k])

        for ed in range(8):
            pushes = pnb_dir[i][ed]
            if ed % 2 == 0:
                # Cardinal arrival.
                if nbrs[ed] != -1:
                    pushes.append(nbrs[ed])
                # Forced diagonal ed-1: blocked if perpendicular cardinal ed-2 is wall.
                if nbrs[(ed - 2) % 8] == -1 and nbrs[(ed - 1) % 8] != -1:
                    pushes.append(nbrs[(ed - 1) % 8])
                if nbrs[(ed + 2) % 8] == -1 and nbrs[(ed + 1) % 8] != -1:
                    pushes.append(nbrs[(ed + 1) % 8])
            else:
                # Diagonal arrival.
                for k in ((ed - 1) % 8, ed, (ed + 1) % 8):
                    if nbrs[k] != -1:
                        pushes.append(nbrs[k])
                # Forced diagonals: ed-2 if cardinal ed-3 wall; ed+2 if cardinal ed+3 wall.
                if nbrs[(ed - 3) % 8] == -1 and nbrs[(ed - 2) % 8] != -1:
                    pushes.append(nbrs[(ed - 2) % 8])
                if nbrs[(ed + 3) % 8] == -1 and nbrs[(ed + 2) % 8] != -1:
                    pushes.append(nbrs[(ed + 2) % 8])

    return pnb_dir
