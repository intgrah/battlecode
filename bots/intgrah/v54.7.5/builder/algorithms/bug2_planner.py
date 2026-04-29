"""Bug2 plan generator that mutates a path_idx list in place.

Drains under a budget per turn — yields after each walker step, after
each m-line cell, and after each chosen-path cell. Caller drives the
generator and resumes next turn from where it left off.

Outcome signalling: the generator's `return` statement carries the
result. Caller catches `StopIteration as e` and reads `e.value`:
  - `True`  -> path reached the goal
  - `False` -> goal proven unreachable

(Sandbox forbids custom exception types, so we can't raise.)

Cost model:
- `cost[i] is INF`        : impassable (wall, enemy building, harvester, ore)
- `cost[i] is not INF`    : passable (treat as 1 for walkable, 3 for buildable
                            in the user's choice of cost grid; the planner
                            itself only checks `is INF`).
- `path_idx[i]`           : -1 if not on plan, else the index along the path
                            (monotone non-decreasing along the planned route).
                            Caller must initialize with -1s and write
                            `path_idx[start] = 0`.

`stride` is the row stride for cell indices: `cell = y * stride + x`.
For the bot we pass `MAX_WIDTH`. `n_pad` is `stride * stride` (the size
of the flat arrays). `w`, `h` are the actual map dimensions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from util.constants import INF, MAX_WIDTH

if TYPE_CHECKING:
    from collections.abc import Iterator

DX: tuple[int, ...] = (0, 1, 1, 1, 0, -1, -1, -1)
DY: tuple[int, ...] = (-1, -1, 0, 1, 1, 1, 0, -1)
_IS_CARDINAL: tuple[bool, ...] = tuple(DX[d] == 0 or DY[d] == 0 for d in range(8))


def _build_mline_seq(sx: int, sy: int, gx: int, gy: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    dx = abs(gx - sx)
    dy = abs(gy - sy)
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


def bug2_plan_iter(
    cost: list[int],
    w: int,
    h: int,
    si: int,
    gi: int,
    path_idx: list[int],
) -> Iterator[int]:
    """Generator. Mutates `path_idx` in place. Yields the flat cell
    index `y * MAX_WIDTH + x` each time it lays down a path tile so the
    caller can collect cells as they're committed (for visualisation,
    etc.). Yields between walker steps before any tile is laid still
    yield -1 as a heartbeat. Returns True on success (path reached the
    goal) and False on unreachable. The return value surfaces as
    `StopIteration.value` to the caller.
    """
    if cost[gi] is INF:
        return False
    stride = MAX_WIDTH
    n_pad = stride * stride
    sx = si % stride
    sy = si // stride
    gx = gi % stride
    gy = gi // stride
    mdx = gx - sx
    mdy = gy - sy
    goal_dot = mdx * mdx + mdy * mdy
    mline_seq = _build_mline_seq(sx, sy, gx, gy)
    is_cardinal = _IS_CARDINAL
    pos = si
    path_len = 1
    m_i = 0
    while pos != gi:
        if m_i + 1 >= len(mline_seq):
            return False
        px = pos % stride
        py = pos // stride
        nx, ny = mline_seq[m_i + 1]
        nb = ny * stride + nx
        if cost[nb] is not INF:
            pos = nb
            path_idx[nb] = path_len
            path_len += 1
            m_i += 1
            yield nb
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
        cw_faces = bytearray(n_pad * 4)
        ccw_faces = bytearray(n_pad * 4)
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
                    cell = ny2 * stride + nx2
                    if cost[cell] is not INF:
                        if 0 <= cw_wox < w and 0 <= cw_woy < h:
                            wdx = cw_wox - nx2
                            wdy = cw_woy - ny2
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
                                k = (cw_woy * stride + cw_wox) * 4 + face
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
                    if is_cardinal[cw_dir]:
                        pdx = cw_px - nx2
                        pdy = cw_py - ny2
                        face = (
                            0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        )
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
                yield -1
            if ccw_alive:
                moved = False
                for _ in range(8):
                    ccw_dir = (ccw_dir + 1) % 8
                    nx2 = ccw_px + DX[ccw_dir]
                    ny2 = ccw_py + DY[ccw_dir]
                    if not (0 <= nx2 < w and 0 <= ny2 < h):
                        continue
                    cell = ny2 * stride + nx2
                    if cost[cell] is not INF:
                        if 0 <= ccw_wox < w and 0 <= ccw_woy < h:
                            wdx = ccw_wox - nx2
                            wdy = ccw_woy - ny2
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
                                k = (ccw_woy * stride + ccw_wox) * 4 + face
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
                        face = (
                            0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
                        )
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
                yield -1
        if winner < 0:
            return False
        chosen_path = cw_path if winner == 0 else ccw_path
        for c in chosen_path:
            path_idx[c] = path_len
            path_len += 1
            yield c
        pos = win_y * stride + win_x
        path_idx[pos] = path_len
        path_len += 1
        yield pos
        walker_dot = (win_x - sx) * mdx + (win_y - sy) * mdy
        while m_i + 1 < len(mline_seq):
            mx, my = mline_seq[m_i + 1]
            if (mx - sx) * mdx + (my - sy) * mdy <= walker_dot:
                m_i += 1
            else:
                break
    return True
