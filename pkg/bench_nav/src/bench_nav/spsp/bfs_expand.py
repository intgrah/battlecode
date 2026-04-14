from bench_nav.common import CR, Path_


def bfs_expand(
    n: int, cost: list[int], pnb: list[list[int]], start: int, goal: int
) -> Path_:
    n2 = n + n
    parent = [-1] * (n + n2)
    parent[start] = start
    q = [start]
    append = q.append
    found = False
    for node in q:
        if node < n:
            for nb in pnb[node]:
                c = cost[nb]
                if c == CR:
                    if parent[nb] != -1:
                        continue
                    parent[nb] = node
                    if nb == goal:
                        found = True
                        break
                    append(nb)
                else:
                    vi = nb + n2
                    if parent[vi] != -1:
                        continue
                    parent[vi] = node
                    append(vi)
        elif node >= n2:
            nb = node - n
            if parent[nb] != -1:
                continue
            parent[nb] = node
            append(nb)
        else:
            nb = node - n
            if parent[nb] != -1:
                continue
            parent[nb] = node
            if nb < n and nb == goal:
                found = True
                break
            append(nb)
        if found:
            break
    if not found:
        return None
    path: list[int] = []
    cur = goal
    while cur != start:
        path.append(cur % n)
        cur = parent[cur]
    path.append(start)
    path.reverse()
    i = 1
    while i < len(path):
        if path[i] == path[i - 1]:
            path.pop(i)
        else:
            i += 1
    return path
