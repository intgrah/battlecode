from bench_nav.common import DIR8, INF


def build_pnb_by_offset(
    w: int, h: int, cost: list[int]
) -> list[list[list[int]]]:
    """pnb_by_offset[nb][offset] = push list when arriving at nb from given offset.

    Uses Python negative indexing; list size w+3 accommodates all 8 offsets uniquely.
    Slot 0 reserved for entry_dir=8 (start): neither a valid positive nor negative offset.
    """
    pnb_dir = build_pnb_dir(w, h, cost)
    size = w + 3
    n = w * h
    out: list[list[list[int]]] = [[[] for _ in range(size)] for _ in range(n)]
    offset_to_dir = {
        -w - 1: 7, -w: 0, -w + 1: 1, -1: 6, 1: 2, w - 1: 5, w: 4, w + 1: 3,
    }
    for nb in range(n):
        for off, d in offset_to_dir.items():
            out[nb][off] = pnb_dir[nb][d]
        out[nb][0] = pnb_dir[nb][8]  # slot 0 unused by offsets; use for start
    return out


def build_dir_of_offset(w: int) -> list[int]:
    """Flat table: dir_of_offset[nb - node + w + 1] = DIR8 index."""
    kp = w + 1
    table = [0] * (2 * w + 3)
    offsets = (-w, -w + 1, 1, w + 1, w, w - 1, -1, -w - 1)
    for d, off in enumerate(offsets):
        table[off + kp] = d
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


