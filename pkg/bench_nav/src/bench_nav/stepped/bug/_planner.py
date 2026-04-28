"""Shared once-per-query planner primitives.

These functions are called exactly once per query (during plan()) — never
inside a step() hot loop. Per-step code stays inlined in each algorithm.

Coordinates are flat int indices: pos = y * w + x. cost is list[int],
INF marks impassable.
"""

from __future__ import annotations

from bench_nav.common import INF

DX: tuple[int, ...] = (0, 1, 1, 1, 0, -1, -1, -1)
DY: tuple[int, ...] = (-1, -1, 0, 1, 1, 1, 0, -1)


def dir_to(sx: int, sy: int, gx: int, gy: int) -> int:
    """8-direction discretisation of (gx-sx, gy-sy). 0 if same cell."""
    rx = (gx > sx) - (gx < sx)
    ry = (gy > sy) - (gy < sy)
    if rx == 0:
        return 0 if ry < 0 else (4 if ry > 0 else 0)
    if rx > 0:
        return 1 if ry < 0 else (2 if ry == 0 else 3)
    return 7 if ry < 0 else (6 if ry == 0 else 5)


_IS_CARDINAL: tuple[bool, ...] = tuple(DX[d] == 0 or DY[d] == 0 for d in range(8))


def circumnav(
    cost: list[int],
    w: int,
    h: int,
    hit_pos: int,
    blocked_dir: int,
    gx: int,
    gy: int,
) -> tuple[list[int], list[int], int, int, int, int]:
    """Walk CW and CCW in parallel, one step each per iteration. Returns
    (cw_perim, ccw_perim, cw_best_idx, cw_best_d, ccw_best_idx, ccw_best_d).

    Face encoding on wall cell (wx, wy):
      face 0 = walker E of wall, face 1 = walker W,
      face 2 = walker N,         face 3 = walker S.

    Painting rules:
      - Cardinal direction tried, wall cell: paint face toward walker.
      - Diagonal direction tried, wall cell: no face painted.
      - Move taken (any direction): paint face of wall-ref from new position,
        but only when wall-ref is cardinally adjacent to new position.
    """
    n = w * h
    cw_faces = bytearray(n * 4)
    ccw_faces = bytearray(n * 4)

    cw_perim: list[int] = [hit_pos]
    ccw_perim: list[int] = [hit_pos]
    cw_len = 1
    ccw_len = 1

    px = hit_pos % w
    py = hit_pos // w
    bdx = DX[blocked_dir]
    bdy = DY[blocked_dir]

    cw_px, cw_py = px, py
    cw_wox, cw_woy = px + bdx, py + bdy
    cw_wall_dir = blocked_dir
    ccw_px, ccw_py = px, py
    ccw_wox, ccw_woy = px + bdx, py + bdy
    ccw_wall_dir = blocked_dir

    hd = (px - gx) * (px - gx) + (py - gy) * (py - gy)
    cw_best_d = hd
    cw_best_idx = 0
    ccw_best_d = hd
    ccw_best_idx = 0

    cw_done = False
    ccw_done = False

    is_cardinal = _IS_CARDINAL
    dx = DX
    dy = DY

    while True:
        # --- CW step ---
        if not cw_done:
            moved = False
            met = False
            loop = False
            for _ in range(8):
                cw_wall_dir = (cw_wall_dir - 1) % 8
                ndx = dx[cw_wall_dir]
                ndy = dy[cw_wall_dir]
                nx = cw_px + ndx
                ny = cw_py + ndy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                cell = ny * w + nx
                if cost[cell] < INF:
                    if 0 <= cw_wox < w and 0 <= cw_woy < h:
                        wdx = cw_wox - nx
                        wdy = cw_woy - ny
                        if wdx == 0 or wdy == 0:
                            face = (
                                0
                                if wdx == -1
                                else 1
                                if wdx == 1
                                else 2
                                if wdy == 1
                                else 3
                            )
                            k = (cw_woy * w + cw_wox) * 4 + face
                            if ccw_faces[k]:
                                met = True
                            elif cw_faces[k]:
                                loop = True
                            cw_faces[k] = 1
                    cw_px, cw_py = nx, ny
                    if is_cardinal[cw_wall_dir]:
                        cw_wall_dir = (cw_wall_dir + 2) % 8
                    else:
                        cw_wall_dir = (cw_wall_dir + 3) % 8
                    cw_wox = cw_px + dx[cw_wall_dir]
                    cw_woy = cw_py + dy[cw_wall_dir]
                    moved = True
                    if not (0 <= cw_wox < w and 0 <= cw_woy < h):
                        cw_done = True
                    break
                cw_wox, cw_woy = nx, ny
                if is_cardinal[cw_wall_dir]:
                    pdx = cw_px - nx
                    pdy = cw_py - ny
                    face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                    k = cell * 4 + face
                    if ccw_faces[k]:
                        met = True
                    elif cw_faces[k]:
                        loop = True
                    cw_faces[k] = 1
            if not moved:
                cw_done = True
            else:
                new_pos = cw_py * w + cw_px
                cw_perim.append(new_pos)
                cw_len += 1
                d2 = (cw_px - gx) * (cw_px - gx) + (cw_py - gy) * (cw_py - gy)
                if d2 <= cw_best_d:
                    cw_best_d = d2
                    cw_best_idx = cw_len - 1
                if met:
                    cw_done = True
                    ccw_done = True
                elif loop:
                    cw_done = True
        # --- CCW step ---
        if not ccw_done:
            moved = False
            met = False
            loop = False
            for _ in range(8):
                ccw_wall_dir = (ccw_wall_dir + 1) % 8
                ndx = dx[ccw_wall_dir]
                ndy = dy[ccw_wall_dir]
                nx = ccw_px + ndx
                ny = ccw_py + ndy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                cell = ny * w + nx
                if cost[cell] < INF:
                    if 0 <= ccw_wox < w and 0 <= ccw_woy < h:
                        wdx = ccw_wox - nx
                        wdy = ccw_woy - ny
                        if wdx == 0 or wdy == 0:
                            face = (
                                0
                                if wdx == -1
                                else 1
                                if wdx == 1
                                else 2
                                if wdy == 1
                                else 3
                            )
                            k = (ccw_woy * w + ccw_wox) * 4 + face
                            if cw_faces[k]:
                                met = True
                            elif ccw_faces[k]:
                                loop = True
                            ccw_faces[k] = 1
                    ccw_px, ccw_py = nx, ny
                    if is_cardinal[ccw_wall_dir]:
                        ccw_wall_dir = (ccw_wall_dir - 2) % 8
                    else:
                        ccw_wall_dir = (ccw_wall_dir - 3) % 8
                    ccw_wox = ccw_px + dx[ccw_wall_dir]
                    ccw_woy = ccw_py + dy[ccw_wall_dir]
                    moved = True
                    if not (0 <= ccw_wox < w and 0 <= ccw_woy < h):
                        ccw_done = True
                    break
                ccw_wox, ccw_woy = nx, ny
                if is_cardinal[ccw_wall_dir]:
                    pdx = ccw_px - nx
                    pdy = ccw_py - ny
                    face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                    k = cell * 4 + face
                    if cw_faces[k]:
                        met = True
                    elif ccw_faces[k]:
                        loop = True
                    ccw_faces[k] = 1
            if not moved:
                ccw_done = True
            else:
                new_pos = ccw_py * w + ccw_px
                ccw_perim.append(new_pos)
                ccw_len += 1
                d2 = (ccw_px - gx) * (ccw_px - gx) + (ccw_py - gy) * (ccw_py - gy)
                if d2 <= ccw_best_d:
                    ccw_best_d = d2
                    ccw_best_idx = ccw_len - 1
                if met:
                    cw_done = True
                    ccw_done = True
                elif loop:
                    ccw_done = True
        if cw_done and ccw_done:
            return (
                cw_perim,
                ccw_perim,
                cw_best_idx,
                cw_best_d,
                ccw_best_idx,
                ccw_best_d,
            )


def bug1_plan(cost: list[int], w: int, h: int, si: int, gi: int) -> list[int] | None:
    """Plan a Bug1 path from si to gi. Returns list of cells [si, ..., gi] or
    None if start and goal are impassable or in disjoint components.
    """
    if cost[si] >= INF or cost[gi] >= INF:
        return None
    path: list[int] = [si]
    pos = si
    gx = gi % w
    gy = gi // w
    iters = 0
    while pos != gi:
        iters += 1
        if iters > w * h + 16:
            return None
        px = pos % w
        py = pos // w
        d = dir_to(px, py, gx, gy)
        ndx = DX[d]
        ndy = DY[d]
        nx = px + ndx
        ny = py + ndy
        if 0 <= nx < w and 0 <= ny < h and cost[ny * w + nx] < INF:
            pos = ny * w + nx
            path.append(pos)
            continue
        cw_perim, ccw_perim, cw_idx, cw_d, ccw_idx, ccw_d = circumnav(
            cost, w, h, pos, d, gx, gy
        )
        perim, idx = (cw_perim, cw_idx) if cw_d <= ccw_d else (ccw_perim, ccw_idx)
        arc = perim[1 : idx + 1] if idx > 0 else []
        if not arc:
            return None
        path.extend(arc)
        pos = arc[-1]
    return path


def bug1_plan_debug(
    cost: list[int], w: int, h: int, si: int, gi: int
) -> tuple[list[int] | None, list[list[int]]]:
    """Same as bug1_plan, but also returns the list of perimeters explored
    at each obstacle hit. Each perimeter is a list of cell indices."""
    perims: list[list[int]] = []
    if cost[si] >= INF or cost[gi] >= INF:
        return None, perims
    path: list[int] = [si]
    pos = si
    gx = gi % w
    gy = gi // w
    iters = 0
    while pos != gi:
        iters += 1
        if iters > w * h + 16:
            return None, perims
        px = pos % w
        py = pos // w
        d = dir_to(px, py, gx, gy)
        ndx = DX[d]
        ndy = DY[d]
        nx = px + ndx
        ny = py + ndy
        if 0 <= nx < w and 0 <= ny < h and cost[ny * w + nx] < INF:
            pos = ny * w + nx
            path.append(pos)
            continue
        cw_perim, ccw_perim, cw_idx, cw_d, ccw_idx, ccw_d = circumnav(
            cost, w, h, pos, d, gx, gy
        )
        perims.append(list(cw_perim))
        perims.append(list(ccw_perim))
        perim, idx = (cw_perim, cw_idx) if cw_d <= ccw_d else (ccw_perim, ccw_idx)
        arc = perim[1 : idx + 1] if idx > 0 else []
        if not arc:
            return None, perims
        path.extend(arc)
        pos = arc[-1]
    return path, perims


def bug2_plan(cost: list[int], w: int, h: int, si: int, gi: int) -> list[int] | None:
    """Bug2 — at each hit point, fork CW + CCW walkers; first to cross the
    m-line at a closer point wins. Walkers paint obstacle faces; meeting
    on a face means obstacle fully circumnavigated → unreachable."""
    if cost[si] >= INF or cost[gi] >= INF:
        return None
    n = w * h
    sx = si % w
    sy = si // w
    gx = gi % w
    gy = gi // w
    mdx = gx - sx
    mdy = gy - sy
    goal_dot = mdx * mdx + mdy * mdy
    mline_seq = _build_mline_seq(sx, sy, gx, gy)
    is_cardinal = _IS_CARDINAL
    path: list[int] = [si]
    pos = si
    m_i = 0
    while pos != gi:
        if m_i + 1 >= len(mline_seq):
            return None
        px = pos % w
        py = pos // w
        nx, ny = mline_seq[m_i + 1]
        nb = ny * w + nx
        if cost[nb] < INF:
            pos = nb
            path.append(pos)
            m_i += 1
            continue
        ddx = px - gx
        ddy = py - gy
        hit_d = ddx * ddx + ddy * ddy
        bdx = nx - px
        bdy = ny - py
        if bdx == 0:
            init_dir = 0 if bdy < 0 else 4
        elif bdx > 0:
            init_dir = 1 if bdy < 0 else (2 if bdy == 0 else 3)
        else:
            init_dir = 7 if bdy < 0 else (6 if bdy == 0 else 5)
        # Fork CW + CCW walkers, each with its own face-painting bytearray.
        cw_faces = bytearray(n * 4)
        ccw_faces = bytearray(n * 4)
        cw_px, cw_py = px, py
        cw_dir = init_dir
        cw_path: list[int] = []
        cw_alive = True
        cw_cross = (py - sy) * mdx - (px - sx) * mdy
        cw_wox = px + DX[init_dir]
        cw_woy = py + DY[init_dir]
        ccw_px, ccw_py = px, py
        ccw_dir = init_dir
        ccw_path: list[int] = []
        ccw_alive = True
        ccw_cross = cw_cross
        ccw_wox = cw_wox
        ccw_woy = cw_woy
        winner: int = -1  # 0=cw, 1=ccw
        win_x = win_y = -1
        met = False
        while cw_alive or ccw_alive:
            if cw_alive:
                moved = False
                for _ in range(8):
                    cw_dir = (cw_dir - 1) % 8
                    nx2 = cw_px + DX[cw_dir]
                    ny2 = cw_py + DY[cw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        # Paint face on wall-ref toward walker (cardinal only).
                        if 0 <= cw_wox < w and 0 <= cw_woy < h:
                            wdx = cw_wox - nx2
                            wdy = cw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (cw_woy * w + cw_wox) * 4 + face
                                if ccw_faces[k]:
                                    met = True
                                cw_faces[k] = 1
                        nxt_cross = (ny2 - sy) * mdx - (nx2 - sx) * mdy
                        if (
                            (cw_cross > 0 and nxt_cross < 0)
                            or (cw_cross < 0 and nxt_cross > 0)
                            or nxt_cross == 0
                        ):
                            cell_dot = (nx2 - sx) * mdx + (ny2 - sy) * mdy
                            ddx = nx2 - gx
                            ddy = ny2 - gy
                            if (
                                0 < cell_dot <= goal_dot
                                and ddx * ddx + ddy * ddy < hit_d
                            ):
                                winner = 0
                                win_x, win_y = nx2, ny2
                                break
                        cw_px, cw_py = nx2, ny2
                        cw_cross = nxt_cross
                        cw_path.append(cell)
                        if is_cardinal[cw_dir]:
                            cw_dir = (cw_dir + 2) % 8
                        else:
                            cw_dir = (cw_dir + 3) % 8
                        cw_wox = cw_px + DX[cw_dir]
                        cw_woy = cw_py + DY[cw_dir]
                        moved = True
                        if not (0 <= cw_wox < w and 0 <= cw_woy < h):
                            cw_alive = False
                        break
                    # Diagonal try, wall cell — no face paint per bug1 rule;
                    # this branch only runs for cardinal `wall_dir` (when the
                    # rotation lands on a wall cell as candidate).
                    if is_cardinal[cw_dir]:
                        pdx = cw_px - nx2
                        pdy = cw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if ccw_faces[k]:
                            met = True
                        cw_faces[k] = 1
                    cw_wox = nx2
                    cw_woy = ny2
                if not moved:
                    cw_alive = False
                if winner >= 0 or met:
                    break
            if ccw_alive:
                moved = False
                for _ in range(8):
                    ccw_dir = (ccw_dir + 1) % 8
                    nx2 = ccw_px + DX[ccw_dir]
                    ny2 = ccw_py + DY[ccw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        if 0 <= ccw_wox < w and 0 <= ccw_woy < h:
                            wdx = ccw_wox - nx2
                            wdy = ccw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (ccw_woy * w + ccw_wox) * 4 + face
                                if cw_faces[k]:
                                    met = True
                                ccw_faces[k] = 1
                        nxt_cross = (ny2 - sy) * mdx - (nx2 - sx) * mdy
                        if (
                            (ccw_cross > 0 and nxt_cross < 0)
                            or (ccw_cross < 0 and nxt_cross > 0)
                            or nxt_cross == 0
                        ):
                            cell_dot = (nx2 - sx) * mdx + (ny2 - sy) * mdy
                            ddx = nx2 - gx
                            ddy = ny2 - gy
                            if (
                                0 < cell_dot <= goal_dot
                                and ddx * ddx + ddy * ddy < hit_d
                            ):
                                winner = 1
                                win_x, win_y = nx2, ny2
                                break
                        ccw_px, ccw_py = nx2, ny2
                        ccw_cross = nxt_cross
                        ccw_path.append(cell)
                        if is_cardinal[ccw_dir]:
                            ccw_dir = (ccw_dir - 2) % 8
                        else:
                            ccw_dir = (ccw_dir - 3) % 8
                        ccw_wox = ccw_px + DX[ccw_dir]
                        ccw_woy = ccw_py + DY[ccw_dir]
                        moved = True
                        if not (0 <= ccw_wox < w and 0 <= ccw_woy < h):
                            ccw_alive = False
                        break
                    if is_cardinal[ccw_dir]:
                        pdx = ccw_px - nx2
                        pdy = ccw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if cw_faces[k]:
                            met = True
                        ccw_faces[k] = 1
                    ccw_wox = nx2
                    ccw_woy = ny2
                if not moved:
                    ccw_alive = False
                if winner >= 0 or met:
                    break
        if winner < 0:
            return None
        chosen_path = cw_path if winner == 0 else ccw_path
        path.extend(chosen_path)
        pos = win_y * w + win_x
        path.append(pos)
        walker_dot = (win_x - sx) * mdx + (win_y - sy) * mdy
        while m_i + 1 < len(mline_seq):
            mx, my = mline_seq[m_i + 1]
            if (mx - sx) * mdx + (my - sy) * mdy <= walker_dot:
                m_i += 1
            else:
                break
    return path


def bug2_plan_iter(
    cost: list[int], w: int, h: int, si: int, gi: int, path_idx: list[int]
):
    """Generator version of bug2_plan. Mutates `path_idx` in place: writes
    the path index at each cell it adds (cell -> position-along-path). Yields
    after each iteration to allow budget pause."""
    if cost[si] >= INF or cost[gi] >= INF:
        return
    n = w * h
    sx = si % w
    sy = si // w
    gx = gi % w
    gy = gi // w
    mdx = gx - sx
    mdy = gy - sy
    goal_dot = mdx * mdx + mdy * mdy
    mline_seq = _build_mline_seq(sx, sy, gx, gy)
    is_cardinal = _IS_CARDINAL
    pos = si
    path_len = 1  # path_idx[si] = 0 set by caller
    m_i = 0
    while pos != gi:
        if m_i + 1 >= len(mline_seq):
            return
        px = pos % w
        py = pos // w
        nx, ny = mline_seq[m_i + 1]
        nb = ny * w + nx
        if cost[nb] < INF:
            pos = nb
            path_idx[nb] = path_len
            path_len += 1
            m_i += 1
            yield
            continue
        ddx = px - gx
        ddy = py - gy
        hit_d = ddx * ddx + ddy * ddy
        bdx = nx - px
        bdy = ny - py
        if bdx == 0:
            init_dir = 0 if bdy < 0 else 4
        elif bdx > 0:
            init_dir = 1 if bdy < 0 else (2 if bdy == 0 else 3)
        else:
            init_dir = 7 if bdy < 0 else (6 if bdy == 0 else 5)
        cw_faces = bytearray(n * 4)
        ccw_faces = bytearray(n * 4)
        cw_px, cw_py = px, py
        cw_dir = init_dir
        cw_path: list[int] = []
        cw_alive = True
        cw_cross = (py - sy) * mdx - (px - sx) * mdy
        cw_wox = px + DX[init_dir]
        cw_woy = py + DY[init_dir]
        ccw_px, ccw_py = px, py
        ccw_dir = init_dir
        ccw_path: list[int] = []
        ccw_alive = True
        ccw_cross = cw_cross
        ccw_wox = cw_wox
        ccw_woy = cw_woy
        winner: int = -1
        win_x = win_y = -1
        met = False
        while cw_alive or ccw_alive:
            if cw_alive:
                moved = False
                for _ in range(8):
                    cw_dir = (cw_dir - 1) % 8
                    nx2 = cw_px + DX[cw_dir]
                    ny2 = cw_py + DY[cw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        if 0 <= cw_wox < w and 0 <= cw_woy < h:
                            wdx = cw_wox - nx2
                            wdy = cw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (cw_woy * w + cw_wox) * 4 + face
                                if ccw_faces[k]:
                                    met = True
                                cw_faces[k] = 1
                        nxt_cross = (ny2 - sy) * mdx - (nx2 - sx) * mdy
                        if (cw_cross > 0 and nxt_cross < 0) or (cw_cross < 0 and nxt_cross > 0) or nxt_cross == 0:
                            cell_dot = (nx2 - sx) * mdx + (ny2 - sy) * mdy
                            ddx = nx2 - gx
                            ddy = ny2 - gy
                            if 0 < cell_dot <= goal_dot and ddx * ddx + ddy * ddy < hit_d:
                                winner = 0
                                win_x, win_y = nx2, ny2
                                break
                        cw_px, cw_py = nx2, ny2
                        cw_cross = nxt_cross
                        cw_path.append(cell)
                        if is_cardinal[cw_dir]:
                            cw_dir = (cw_dir + 2) % 8
                        else:
                            cw_dir = (cw_dir + 3) % 8
                        cw_wox = cw_px + DX[cw_dir]
                        cw_woy = cw_py + DY[cw_dir]
                        moved = True
                        if not (0 <= cw_wox < w and 0 <= cw_woy < h):
                            cw_alive = False
                        break
                    if is_cardinal[cw_dir]:
                        pdx = cw_px - nx2
                        pdy = cw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if ccw_faces[k]:
                            met = True
                        cw_faces[k] = 1
                    cw_wox = nx2
                    cw_woy = ny2
                if not moved:
                    cw_alive = False
                if winner >= 0 or met:
                    break
                yield
            if ccw_alive:
                moved = False
                for _ in range(8):
                    ccw_dir = (ccw_dir + 1) % 8
                    nx2 = ccw_px + DX[ccw_dir]
                    ny2 = ccw_py + DY[ccw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        if 0 <= ccw_wox < w and 0 <= ccw_woy < h:
                            wdx = ccw_wox - nx2
                            wdy = ccw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (ccw_woy * w + ccw_wox) * 4 + face
                                if cw_faces[k]:
                                    met = True
                                ccw_faces[k] = 1
                        nxt_cross = (ny2 - sy) * mdx - (nx2 - sx) * mdy
                        if (ccw_cross > 0 and nxt_cross < 0) or (ccw_cross < 0 and nxt_cross > 0) or nxt_cross == 0:
                            cell_dot = (nx2 - sx) * mdx + (ny2 - sy) * mdy
                            ddx = nx2 - gx
                            ddy = ny2 - gy
                            if 0 < cell_dot <= goal_dot and ddx * ddx + ddy * ddy < hit_d:
                                winner = 1
                                win_x, win_y = nx2, ny2
                                break
                        ccw_px, ccw_py = nx2, ny2
                        ccw_cross = nxt_cross
                        ccw_path.append(cell)
                        if is_cardinal[ccw_dir]:
                            ccw_dir = (ccw_dir - 2) % 8
                        else:
                            ccw_dir = (ccw_dir - 3) % 8
                        ccw_wox = ccw_px + DX[ccw_dir]
                        ccw_woy = ccw_py + DY[ccw_dir]
                        moved = True
                        if not (0 <= ccw_wox < w and 0 <= ccw_woy < h):
                            ccw_alive = False
                        break
                    if is_cardinal[ccw_dir]:
                        pdx = ccw_px - nx2
                        pdy = ccw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if cw_faces[k]:
                            met = True
                        ccw_faces[k] = 1
                    ccw_wox = nx2
                    ccw_woy = ny2
                if not moved:
                    ccw_alive = False
                if winner >= 0 or met:
                    break
                yield
        if winner < 0:
            return
        chosen_path = cw_path if winner == 0 else ccw_path
        for c in chosen_path:
            path_idx[c] = path_len
            path_len += 1
            yield
        pos = win_y * w + win_x
        path_idx[pos] = path_len
        path_len += 1
        yield
        walker_dot = (win_x - sx) * mdx + (win_y - sy) * mdy
        while m_i + 1 < len(mline_seq):
            mx, my = mline_seq[m_i + 1]
            if (mx - sx) * mdx + (my - sy) * mdy <= walker_dot:
                m_i += 1
            else:
                break


def bug2_plan_parallel_debug(
    cost: list[int], w: int, h: int, si: int, gi: int
) -> tuple[list[int], list[tuple[list[int], list[int]]], str]:
    """Debug variant of bug2_plan returning (committed_path, per-hit
    (cw_partial, ccw_partial) walker traces, fail_reason)."""
    if cost[si] >= INF or cost[gi] >= INF:
        return [si], [], "impassable"
    sx = si % w
    sy = si // w
    gx = gi % w
    gy = gi // w
    mdx = gx - sx
    mdy = gy - sy
    goal_dot = mdx * mdx + mdy * mdy
    mline_seq = _build_mline_seq(sx, sy, gx, gy)
    is_cardinal = _IS_CARDINAL
    safety_cap = w * h + 16
    path: list[int] = [si]
    walker_traces: list[tuple[list[int], list[int]]] = []
    pos = si
    m_i = 0
    outer_iter = 0
    outer_cap = 4 * w * h
    while pos != gi:
        outer_iter += 1
        if outer_iter > outer_cap:
            return path, walker_traces, "outer-cap"
        if len(path) > safety_cap:
            return path, walker_traces, "safety-cap"
        if m_i + 1 >= len(mline_seq):
            return path, walker_traces, "mline-end"
        px = pos % w
        py = pos // w
        nx, ny = mline_seq[m_i + 1]
        nb = ny * w + nx
        if cost[nb] < INF:
            pos = nb
            path.append(pos)
            m_i += 1
            continue
        ddx = px - gx
        ddy = py - gy
        hit_d = ddx * ddx + ddy * ddy
        bdx = nx - px
        bdy = ny - py
        if bdx == 0:
            init_dir = 0 if bdy < 0 else 4
        elif bdx > 0:
            init_dir = 1 if bdy < 0 else (2 if bdy == 0 else 3)
        else:
            init_dir = 7 if bdy < 0 else (6 if bdy == 0 else 5)
        cw_px, cw_py = px, py
        cw_dir = init_dir
        cw_path: list[int] = []
        cw_alive = True
        cw_cross = (py - sy) * mdx - (px - sx) * mdy
        ccw_px, ccw_py = px, py
        ccw_dir = init_dir
        ccw_path: list[int] = []
        ccw_alive = True
        ccw_cross = cw_cross
        winner: int = -1
        win_x = win_y = -1
        inner_iter = 0
        inner_cap = 8 * w * h
        while cw_alive or ccw_alive:
            inner_iter += 1
            if inner_iter > inner_cap:
                walker_traces.append((cw_path, ccw_path))
                return path, walker_traces, "inner-cap"
            if cw_alive:
                moved = False
                for _ in range(8):
                    cw_dir = (cw_dir - 1) % 8
                    nx2 = cw_px + DX[cw_dir]
                    ny2 = cw_py + DY[cw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    if cost[ny2 * w + nx2] < INF:
                        nxt_cross = (ny2 - sy) * mdx - (nx2 - sx) * mdy
                        if (
                            (cw_cross > 0 and nxt_cross < 0)
                            or (cw_cross < 0 and nxt_cross > 0)
                            or nxt_cross == 0
                        ):
                            cell_dot = (nx2 - sx) * mdx + (ny2 - sy) * mdy
                            ddx = nx2 - gx
                            ddy = ny2 - gy
                            if (
                                0 < cell_dot <= goal_dot
                                and ddx * ddx + ddy * ddy < hit_d
                            ):
                                winner = 0
                                win_x, win_y = nx2, ny2
                                break
                        cw_px, cw_py = nx2, ny2
                        cw_cross = nxt_cross
                        cw_path.append(ny2 * w + nx2)
                        if is_cardinal[cw_dir]:
                            cw_dir = (cw_dir + 2) % 8
                        else:
                            cw_dir = (cw_dir + 3) % 8
                        wox = cw_px + DX[cw_dir]
                        woy = cw_py + DY[cw_dir]
                        moved = True
                        if not (0 <= wox < w and 0 <= woy < h):
                            cw_alive = False
                        break
                if not moved:
                    cw_alive = False
                if winner >= 0:
                    break
            if ccw_alive:
                moved = False
                for _ in range(8):
                    ccw_dir = (ccw_dir + 1) % 8
                    nx2 = ccw_px + DX[ccw_dir]
                    ny2 = ccw_py + DY[ccw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    if cost[ny2 * w + nx2] < INF:
                        nxt_cross = (ny2 - sy) * mdx - (nx2 - sx) * mdy
                        if (
                            (ccw_cross > 0 and nxt_cross < 0)
                            or (ccw_cross < 0 and nxt_cross > 0)
                            or nxt_cross == 0
                        ):
                            cell_dot = (nx2 - sx) * mdx + (ny2 - sy) * mdy
                            ddx = nx2 - gx
                            ddy = ny2 - gy
                            if (
                                0 < cell_dot <= goal_dot
                                and ddx * ddx + ddy * ddy < hit_d
                            ):
                                winner = 1
                                win_x, win_y = nx2, ny2
                                break
                        ccw_px, ccw_py = nx2, ny2
                        ccw_cross = nxt_cross
                        ccw_path.append(ny2 * w + nx2)
                        if is_cardinal[ccw_dir]:
                            ccw_dir = (ccw_dir - 2) % 8
                        else:
                            ccw_dir = (ccw_dir - 3) % 8
                        wox = ccw_px + DX[ccw_dir]
                        woy = ccw_py + DY[ccw_dir]
                        moved = True
                        if not (0 <= wox < w and 0 <= woy < h):
                            ccw_alive = False
                        break
                if not moved:
                    ccw_alive = False
                if winner >= 0:
                    break
        walker_traces.append((cw_path, ccw_path))
        if winner < 0:
            return path, walker_traces, "both-died"
        chosen_path = cw_path if winner == 0 else ccw_path
        path.extend(chosen_path)
        pos = win_y * w + win_x
        path.append(pos)
        walker_dot = (win_x - sx) * mdx + (win_y - sy) * mdy
        while m_i + 1 < len(mline_seq):
            mx, my = mline_seq[m_i + 1]
            if (mx - sx) * mdx + (my - sy) * mdy <= walker_dot:
                m_i += 1
            else:
                break
    return path, walker_traces, "ok"


def _build_mline(w: int, sx: int, sy: int, gx: int, gy: int) -> set[int]:
    """Bresenham line from (sx,sy) to (gx,gy)."""
    cells: set[int] = set()
    dx = gx - sx
    if dx < 0:
        dx = -dx
    dy = gy - sy
    if dy < 0:
        dy = -dy
    sxi = 1 if sx < gx else -1
    syi = 1 if sy < gy else -1
    err = dx - dy
    cx, cy = sx, sy
    while True:
        cells.add(cy * w + cx)
        if cx == gx and cy == gy:
            return cells
        e2 = err << 1
        if e2 > -dy:
            err -= dy
            cx += sxi
        if e2 < dx:
            err += dx
            cy += syi


def _build_mline_seq(sx: int, sy: int, gx: int, gy: int) -> list[tuple[int, int]]:
    """Bresenham line cells in order from (sx,sy) to (gx,gy)."""
    out: list[tuple[int, int]] = []
    dx = gx - sx
    if dx < 0:
        dx = -dx
    dy = gy - sy
    if dy < 0:
        dy = -dy
    sxi = 1 if sx < gx else -1
    syi = 1 if sy < gy else -1
    err = dx - dy
    cx, cy = sx, sy
    while True:
        out.append((cx, cy))
        if cx == gx and cy == gy:
            return out
        e2 = err << 1
        if e2 > -dy:
            err -= dy
            cx += sxi
        if e2 < dx:
            err += dx
            cy += syi



def bug0_plan(cost: list[int], w: int, h: int, si: int, gi: int) -> list[int] | None:
    """Bug0 — greedy until hit, then fork CW + CCW walkers. A walker leaves
    when it can take any 8-step strictly closer to goal by Chebyshev. Walker
    dies on map edge (wall-ref off-map) or face-meet with the other walker.
    Both die without leaving → unreachable."""
    if cost[si] >= INF or cost[gi] >= INF:
        return None
    n = w * h
    is_cardinal = _IS_CARDINAL
    safety_cap = 4 * n + 16
    path: list[int] = [si]
    pos = si
    gx = gi % w
    gy = gi // w
    while pos != gi:
        if len(path) > safety_cap:
            return None
        px = pos % w
        py = pos // w
        # Greedy: best 8-neighbour by chebyshev to goal.
        cur_cheb = max(abs(px - gx), abs(py - gy))
        best_nb = -1
        best_cheb = cur_cheb
        for d in range(8):
            nx = px + DX[d]
            ny = py + DY[d]
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            nb = ny * w + nx
            if cost[nb] >= INF:
                continue
            cheb = max(abs(nx - gx), abs(ny - gy))
            if cheb < best_cheb:
                best_cheb = cheb
                best_nb = nb
        if best_nb >= 0:
            pos = best_nb
            path.append(pos)
            continue
        # Hit. Find blocked direction toward goal.
        d = dir_to(px, py, gx, gy)
        hit_cheb = max(abs(px - gx), abs(py - gy))
        # Fork CW + CCW from hit point.
        cw_faces = bytearray(n * 4)
        ccw_faces = bytearray(n * 4)
        cw_px, cw_py = px, py
        cw_dir = d
        cw_path: list[int] = []
        cw_alive = True
        cw_wox = px + DX[d]
        cw_woy = py + DY[d]
        ccw_px, ccw_py = px, py
        ccw_dir = d
        ccw_path: list[int] = []
        ccw_alive = True
        ccw_wox = cw_wox
        ccw_woy = cw_woy
        winner = -1
        win_x = win_y = -1
        met = False
        while cw_alive or ccw_alive:
            if cw_alive:
                # Leave check: walker is closer than at hit point.
                if max(abs(cw_px - gx), abs(cw_py - gy)) < hit_cheb:
                    winner = 0
                    win_x, win_y = cw_px, cw_py
                    break
                # Wall-step.
                moved = False
                for _ in range(8):
                    cw_dir = (cw_dir - 1) % 8
                    nx2 = cw_px + DX[cw_dir]
                    ny2 = cw_py + DY[cw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        if 0 <= cw_wox < w and 0 <= cw_woy < h:
                            wdx = cw_wox - nx2
                            wdy = cw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (cw_woy * w + cw_wox) * 4 + face
                                if ccw_faces[k]:
                                    met = True
                                cw_faces[k] = 1
                        cw_px, cw_py = nx2, ny2
                        cw_path.append(cell)
                        if is_cardinal[cw_dir]:
                            cw_dir = (cw_dir + 2) % 8
                        else:
                            cw_dir = (cw_dir + 3) % 8
                        cw_wox = cw_px + DX[cw_dir]
                        cw_woy = cw_py + DY[cw_dir]
                        moved = True
                        if not (0 <= cw_wox < w and 0 <= cw_woy < h):
                            cw_alive = False
                        break
                    if is_cardinal[cw_dir]:
                        pdx = cw_px - nx2
                        pdy = cw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if ccw_faces[k]:
                            met = True
                        cw_faces[k] = 1
                    cw_wox = nx2
                    cw_woy = ny2
                if not moved:
                    cw_alive = False
                if met:
                    break
            if ccw_alive:
                if max(abs(ccw_px - gx), abs(ccw_py - gy)) < hit_cheb:
                    winner = 1
                    win_x, win_y = ccw_px, ccw_py
                    break
                moved = False
                for _ in range(8):
                    ccw_dir = (ccw_dir + 1) % 8
                    nx2 = ccw_px + DX[ccw_dir]
                    ny2 = ccw_py + DY[ccw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        if 0 <= ccw_wox < w and 0 <= ccw_woy < h:
                            wdx = ccw_wox - nx2
                            wdy = ccw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (ccw_woy * w + ccw_wox) * 4 + face
                                if cw_faces[k]:
                                    met = True
                                ccw_faces[k] = 1
                        ccw_px, ccw_py = nx2, ny2
                        ccw_path.append(cell)
                        if is_cardinal[ccw_dir]:
                            ccw_dir = (ccw_dir - 2) % 8
                        else:
                            ccw_dir = (ccw_dir - 3) % 8
                        ccw_wox = ccw_px + DX[ccw_dir]
                        ccw_woy = ccw_py + DY[ccw_dir]
                        moved = True
                        if not (0 <= ccw_wox < w and 0 <= ccw_woy < h):
                            ccw_alive = False
                        break
                    if is_cardinal[ccw_dir]:
                        pdx = ccw_px - nx2
                        pdy = ccw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if cw_faces[k]:
                            met = True
                        ccw_faces[k] = 1
                    ccw_wox = nx2
                    ccw_woy = ny2
                if not moved:
                    ccw_alive = False
                if met:
                    break
        if winner < 0:
            return None
        chosen_path = cw_path if winner == 0 else ccw_path
        path.extend(chosen_path)
        pos = win_y * w + win_x
    return path


def bug0_plan_debug(
    cost: list[int], w: int, h: int, si: int, gi: int
) -> tuple[list[int], list[tuple[list[int], list[int]]], str]:
    """Debug variant of bug0_plan: returns (committed_path, per-hit
    (cw_partial, ccw_partial), fail_reason)."""
    if cost[si] >= INF or cost[gi] >= INF:
        return [si], [], "impassable"
    n = w * h
    is_cardinal = _IS_CARDINAL
    safety_cap = 4 * n + 16
    path: list[int] = [si]
    walker_traces: list[tuple[list[int], list[int]]] = []
    pos = si
    gx = gi % w
    gy = gi // w
    while pos != gi:
        if len(path) > safety_cap:
            return path, walker_traces, "safety-cap"
        px = pos % w
        py = pos // w
        cur_cheb = max(abs(px - gx), abs(py - gy))
        best_nb = -1
        best_cheb = cur_cheb
        for d in range(8):
            nx = px + DX[d]
            ny = py + DY[d]
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            nb = ny * w + nx
            if cost[nb] >= INF:
                continue
            cheb = max(abs(nx - gx), abs(ny - gy))
            if cheb < best_cheb:
                best_cheb = cheb
                best_nb = nb
        if best_nb >= 0:
            pos = best_nb
            path.append(pos)
            continue
        d = dir_to(px, py, gx, gy)
        hit_cheb = max(abs(px - gx), abs(py - gy))
        cw_faces = bytearray(n * 4)
        ccw_faces = bytearray(n * 4)
        cw_px, cw_py = px, py
        cw_dir = d
        cw_path: list[int] = []
        cw_alive = True
        cw_wox = px + DX[d]
        cw_woy = py + DY[d]
        ccw_px, ccw_py = px, py
        ccw_dir = d
        ccw_path: list[int] = []
        ccw_alive = True
        ccw_wox = cw_wox
        ccw_woy = cw_woy
        winner = -1
        win_x = win_y = -1
        met = False
        while cw_alive or ccw_alive:
            if cw_alive:
                cur_cheb = max(abs(cw_px - gx), abs(cw_py - gy))
                leave_nb = -1
                for di in range(8):
                    lx = cw_px + DX[di]
                    ly = cw_py + DY[di]
                    if not (0 <= lx < w and 0 <= ly < h):
                        continue
                    lc = ly * w + lx
                    if cost[lc] >= INF:
                        continue
                    if max(abs(lx - gx), abs(ly - gy)) < hit_cheb:
                        leave_nb = lc
                        win_x, win_y = lx, ly
                        break
                if leave_nb >= 0:
                    winner = 0
                    break
                moved = False
                for _ in range(8):
                    cw_dir = (cw_dir - 1) % 8
                    nx2 = cw_px + DX[cw_dir]
                    ny2 = cw_py + DY[cw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        if 0 <= cw_wox < w and 0 <= cw_woy < h:
                            wdx = cw_wox - nx2
                            wdy = cw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (cw_woy * w + cw_wox) * 4 + face
                                if ccw_faces[k]:
                                    met = True
                                cw_faces[k] = 1
                        cw_px, cw_py = nx2, ny2
                        cw_path.append(cell)
                        if is_cardinal[cw_dir]:
                            cw_dir = (cw_dir + 2) % 8
                        else:
                            cw_dir = (cw_dir + 3) % 8
                        cw_wox = cw_px + DX[cw_dir]
                        cw_woy = cw_py + DY[cw_dir]
                        moved = True
                        if not (0 <= cw_wox < w and 0 <= cw_woy < h):
                            cw_alive = False
                        break
                    if is_cardinal[cw_dir]:
                        pdx = cw_px - nx2
                        pdy = cw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if ccw_faces[k]:
                            met = True
                        cw_faces[k] = 1
                    cw_wox = nx2
                    cw_woy = ny2
                if not moved:
                    cw_alive = False
                if met:
                    break
            if ccw_alive:
                if max(abs(ccw_px - gx), abs(ccw_py - gy)) < hit_cheb:
                    winner = 1
                    win_x, win_y = ccw_px, ccw_py
                    break
                moved = False
                for _ in range(8):
                    ccw_dir = (ccw_dir + 1) % 8
                    nx2 = ccw_px + DX[ccw_dir]
                    ny2 = ccw_py + DY[ccw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * w + nx2
                    if cost[cell] < INF:
                        if 0 <= ccw_wox < w and 0 <= ccw_woy < h:
                            wdx = ccw_wox - nx2
                            wdy = ccw_woy - ny2
                            if wdx == 0 or wdy == 0:
                                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                                k = (ccw_woy * w + ccw_wox) * 4 + face
                                if cw_faces[k]:
                                    met = True
                                ccw_faces[k] = 1
                        ccw_px, ccw_py = nx2, ny2
                        ccw_path.append(cell)
                        if is_cardinal[ccw_dir]:
                            ccw_dir = (ccw_dir - 2) % 8
                        else:
                            ccw_dir = (ccw_dir - 3) % 8
                        ccw_wox = ccw_px + DX[ccw_dir]
                        ccw_woy = ccw_py + DY[ccw_dir]
                        moved = True
                        if not (0 <= ccw_wox < w and 0 <= ccw_woy < h):
                            ccw_alive = False
                        break
                    if is_cardinal[ccw_dir]:
                        pdx = ccw_px - nx2
                        pdy = ccw_py - ny2
                        face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        k = cell * 4 + face
                        if cw_faces[k]:
                            met = True
                        ccw_faces[k] = 1
                    ccw_wox = nx2
                    ccw_woy = ny2
                if not moved:
                    ccw_alive = False
                if met:
                    break
        walker_traces.append((cw_path, ccw_path))
        if winner < 0:
            return path, walker_traces, "both-died"
        chosen_path = cw_path if winner == 0 else ccw_path
        path.extend(chosen_path)
        pos = win_y * w + win_x
    return path, walker_traces, "ok"


def distbug_plan(cost: list[int], w: int, h: int, si: int, gi: int) -> list[int] | None:
    """DistBug — leave wall when free ray toward goal reaches a closer cell."""
    if cost[si] >= INF or cost[gi] >= INF:
        return None
    a = _distbug_one(cost, w, h, si, gi, 0)
    b = _distbug_one(cost, w, h, si, gi, 1)
    if a is None:
        return b
    if b is None:
        return a
    return a if len(a) <= len(b) else b


def _distbug_one(
    cost: list[int], w: int, h: int, si: int, gi: int, on_right: int
) -> list[int] | None:
    safety_cap = w * h + 16
    path: list[int] = [si]
    pos = si
    sx = si % w
    sy = si // w
    gx = gi % w
    gy = gi // w
    ddx = sx - gx
    ddy = sy - gy
    d_min = ddx * ddx + ddy * ddy
    while pos != gi:
        if len(path) > safety_cap:
            return None
        px = pos % w
        py = pos // w
        d = dir_to(px, py, gx, gy)
        ndx = DX[d]
        ndy = DY[d]
        nx = px + ndx
        ny = py + ndy
        if 0 <= nx < w and 0 <= ny < h and cost[ny * w + nx] < INF:
            pos = ny * w + nx
            path.append(pos)
            ddx = nx - gx
            ddy = ny - gy
            dd = ddx * ddx + ddy * ddy
            d_min = min(d_min, dd)
            continue
        wox = nx
        woy = ny
        seen: set[int] = set()
        side = on_right
        seen.add(pos * 16 + d * 2 + side)
        while True:
            # Try ray toward goal.
            rd = dir_to(px, py, gx, gy)
            rdx = DX[rd]
            rdy = DY[rd]
            rx = px
            ry = py
            ri = pos
            while True:
                tx = rx + rdx
                ty = ry + rdy
                if not (0 <= tx < w and 0 <= ty < h):
                    break
                ti = ty * w + tx
                if cost[ti] >= INF:
                    break
                rx = tx
                ry = ty
                ri = ti
                if ri == gi:
                    break
            ddx = rx - gx
            ddy = ry - gy
            d_after = ddx * ddx + ddy * ddy
            if ri != pos and d_after < d_min:
                p = pos
                while p != ri:
                    p += rdy * w + rdx
                    path.append(p)
                pos = ri
                px = rx
                py = ry
                d_min = d_after
                break
            # Wall-follow step.
            odx = wox - px
            ody = woy - py
            sox = (odx > 0) - (odx < 0)
            soy = (ody > 0) - (ody < 0)
            if sox == 0:
                direction = 0 if soy < 0 else 4
            elif sox > 0:
                direction = 1 if soy < 0 else (2 if soy == 0 else 3)
            else:
                direction = 7 if soy < 0 else (6 if soy == 0 else 5)
            moved = False
            for _ in range(8):
                direction = (direction - 1) % 8 if on_right else (direction + 1) & 7
                ndx2 = DX[direction]
                ndy2 = DY[direction]
                nx2 = px + ndx2
                ny2 = py + ndy2
                on_map = 0 <= nx2 < w and 0 <= ny2 < h
                if on_map and cost[ny2 * w + nx2] < INF:
                    px = nx2
                    py = ny2
                    moved = True
                    break
                if on_map:
                    wox = nx2
                    woy = ny2
                else:
                    return None
            if not moved:
                return None
            pos = py * w + px
            path.append(pos)
            ddx = px - gx
            ddy = py - gy
            dd = ddx * ddx + ddy * ddy
            d_min = min(d_min, dd)
            nox = wox - px
            noy = woy - py
            nsox = (nox > 0) - (nox < 0)
            nsoy = (noy > 0) - (noy < 0)
            if nsox == 0:
                ndir2 = 0 if nsoy < 0 else 4
            elif nsox > 0:
                ndir2 = 1 if nsoy < 0 else (2 if nsoy == 0 else 3)
            else:
                ndir2 = 7 if nsoy < 0 else (6 if nsoy == 0 else 5)
            sk = pos * 16 + ndir2 * 2 + side
            if sk in seen:
                return None
            seen.add(sk)
            if len(path) > safety_cap:
                return None
    return path
