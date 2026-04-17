from bench_nav.common import DIR8, INF


def build_dir_of_offset(w: int) -> list[int]:
    """Flat table: dir_of_offset[nb - node + w + 1] = DIR8 index."""
    kp = w + 1
    table = [0] * (2 * w + 3)
    offsets = (-w, -w + 1, 1, w + 1, w, w - 1, -1, -w - 1)
    for d, off in enumerate(offsets):
        table[off + kp] = d
    return table


def build_pnb_dir(w: int, h: int, cost: list[int]) -> list[list[list[int]]]:
    """JPS dominance only (no bracket skip). push all non-dominated neighbors.

    pnb_dir[node][entry_dir] = neighbor indices to enqueue.
    """
    n = w * h
    pnb_dir: list[list[list[int]]] = [[[] for _ in range(9)] for _ in range(n)]
    dir_set = {DIR8[j] for j in range(8)} | {(0, 0)}

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

        for entry_dir in range(9):
            if entry_dir == 8:
                for nb in nbrs:
                    if nb != -1:
                        pnb_dir[i][entry_dir].append(nb)
                continue

            edx, edy = DIR8[entry_dir]
            for k in range(8):
                if nbrs[k] == -1:
                    continue
                kdx, kdy = DIR8[k]
                if (edx + kdx, edy + kdy) in dir_set:
                    continue
                pnb_dir[i][entry_dir].append(nbrs[k])

    return pnb_dir


def build_pnb_push_set_dir(
    w: int, h: int, cost: list[int]
) -> tuple[list[list[list[int]]], list[list[list[int]]]]:
    """JPS dominance + bracket skip.

    pnb_push_dir[node][entry_dir] = enqueue
    pnb_set_dir[node][entry_dir]  = fill dist but don't enqueue
    """
    n = w * h
    pnb_push_dir: list[list[list[int]]] = [[[] for _ in range(9)] for _ in range(n)]
    pnb_set_dir: list[list[list[int]]] = [[[] for _ in range(9)] for _ in range(n)]
    dir_set = {DIR8[j] for j in range(8)} | {(0, 0)}

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

        bracketed = [False] * 8
        for k in (0, 2, 4, 6):
            d1 = (k - 1) % 8
            d2 = (k + 1) % 8
            bracketed[k] = nbrs[d1] != -1 and nbrs[d2] != -1

        for entry_dir in range(9):
            if entry_dir == 8:
                for k in range(8):
                    if nbrs[k] == -1:
                        continue
                    if k % 2 == 0 and bracketed[k]:
                        pnb_set_dir[i][entry_dir].append(nbrs[k])
                    else:
                        pnb_push_dir[i][entry_dir].append(nbrs[k])
                continue

            edx, edy = DIR8[entry_dir]
            for k in range(8):
                if nbrs[k] == -1:
                    continue
                kdx, kdy = DIR8[k]
                if (edx + kdx, edy + kdy) in dir_set:
                    continue
                if k % 2 == 0 and bracketed[k]:
                    pnb_set_dir[i][entry_dir].append(nbrs[k])
                else:
                    pnb_push_dir[i][entry_dir].append(nbrs[k])

    return pnb_push_dir, pnb_set_dir
