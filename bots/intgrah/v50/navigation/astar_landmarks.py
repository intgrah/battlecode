import heapq

from util import COST_ROAD, DIR8_DELTA, INF

_NODE_BUDGET = 700


def find_path_raw(
    w: int,
    h: int,
    cost: list[int],
    sx: int,
    sy: int,
    gx: int,
    gy: int,
    landmarks: list[int],
    lm_data: bytes,
    n_tiles: int,
) -> list[int] | None:
    n = w * h
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    n_lm = len(landmarks)
    lm_gi = [lm_data[li * n_tiles + gi] for li in range(n_lm)]

    ht = [-1] * n

    def _h(i: int) -> int:
        v = ht[i]
        if v >= 0:
            return v
        v = max(abs(i % w - gx), abs(i // w - gy)) * COST_ROAD
        for li in range(n_lm):
            di = lm_data[li * n_tiles + i]
            dg = lm_gi[li]
            if di < 255 and dg < 255:
                diff = di - dg
                if diff < 0:
                    diff = -diff
                diff *= COST_ROAD
                v = max(v, diff)
        ht[i] = v
        return v

    g = [INF] * n
    parent = [-1] * n
    g[si] = 0
    touched = [si]
    h_si = _h(si)
    heap: list[tuple[int, int]] = [(h_si, si)]
    exp = 0
    best_h = INF
    best_node = si

    while heap:
        f, node = heapq.heappop(heap)
        if node == gi:
            return _extract(parent, si, gi)
        h_node = _h(node)
        if f > g[node] + h_node:
            continue
        exp += 1
        if h_node < best_h:
            best_h = h_node
            best_node = node
        if exp >= _NODE_BUDGET:
            return _extract(parent, si, best_node)
        gn = g[node]
        cx, cy = node % w, node // w
        for dx, dy in DIR8_DELTA:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or nx >= w or ny < 0 or ny >= h:
                continue
            ni = ny * w + nx
            c = cost[ni]
            if c >= INF:
                continue
            if dx != 0 and dy != 0:
                c += 1
            nd = gn + c
            if nd < g[ni]:
                if g[ni] == INF:
                    touched.append(ni)
                g[ni] = nd
                parent[ni] = node
                heapq.heappush(heap, (nd + _h(ni), ni))

    if best_h < INF:
        return _extract(parent, si, best_node)
    return None


def _extract(parent: list[int], si: int, node: int) -> list[int] | None:
    if parent[node] == -1 and node != si:
        return None
    path: list[int] = []
    cur = node
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path
