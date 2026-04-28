"""Inlined bug-style path planners.

Plan-once, walk-the-cache style. Three variants — Bug1, Bug2, DistBug —
each running CW + CCW internally and picking the shorter. A `best_of`
combinator runs all three and picks the shortest pruned result.

Implementation rules:
- All three planners and the cycle-pruner are flat top-level functions,
  no helper imports beyond `INF` and `MAX_WIDTH`. Wall-follow logic is
  inlined per-variant.
- Coordinates as flat int indices throughout (`i = y * MAX_WIDTH + x`).
  No tuples, no dataclasses, no closures inside hot loops.
- Caller passes `cost: list[int]` (len MAX_N). A tile is "passable" iff
  `cost[i] < INF`. Off-map tiles are walls.
- Return `list[int]` of flat indices `[start, ..., goal]`, or None on
  failure (cycle, surrounded, no_progress, safety_cap).
- Direction encoding: 0=N, 1=NE, 2=E, 3=SE, 4=S, 5=SW, 6=W, 7=NW.
  Stored as `int` (no Direction enum lookup).
- Cycle detection: bytearray `seen` keyed by
  `(pos_idx * 16 + obstacle_dir * 2 + side)`. Reset between
  wall-follow excursions by bumping a `version` byte and storing
  versions instead of bools.

The dirty-but-fast aesthetic is intentional. Clarity belongs in
`bench_nav/stepped/bug/_common.py`; this file exists to be small and
fast on CPython.
"""

from __future__ import annotations

from util.constants import INF, MAX_WIDTH

__all__ = [
    "plan_bug1",
    "plan_bug2",
    "plan_distbug",
    "prune_cycles",
]


# Per-direction (dx, dy) — kept as parallel lists for fast indexing.
_DX: tuple[int, ...] = (0, 1, 1, 1, 0, -1, -1, -1)
_DY: tuple[int, ...] = (-1, -1, 0, 1, 1, 1, 0, -1)
# Flat-index delta = dy*MAX_WIDTH + dx.
_DI: tuple[int, ...] = tuple(_DY[d] * MAX_WIDTH + _DX[d] for d in range(8))


def _dir_to_goal(sx: int, sy: int, gx: int, gy: int) -> int:
    """Discretise (gx-sx, gy-sy) to one of 8 dirs. Returns 0 for
    same-cell, which is a degenerate case the callers handle.
    """
    dx = gx - sx
    dy = gy - sy
    sx2 = (dx > 0) - (dx < 0)
    sy2 = (dy > 0) - (dy < 0)
    # Mapping table for (sx2, sy2) -> dir:
    #  ( 0, -1) -> 0   ( 1, -1) -> 1   ( 1, 0) -> 2
    #  ( 1,  1) -> 3   ( 0,  1) -> 4   (-1, 1) -> 5
    #  (-1,  0) -> 6   (-1, -1) -> 7
    if sx2 == 0:
        return 0 if sy2 < 0 else 4
    if sx2 > 0:
        if sy2 < 0:
            return 1
        if sy2 == 0:
            return 2
        return 3
    if sy2 < 0:
        return 7
    if sy2 == 0:
        return 6
    return 5


def prune_cycles(path: list[int]) -> list[int]:
    """Remove all subloops: walking i -> ... -> i collapses to just i.
    Mutates a fresh list; original untouched.
    """
    out: list[int] = []
    idx: dict[int, int] = {}
    for c in path:
        prev = idx.get(c, -1)
        if prev != -1:
            # Collapse: drop everything after prev.
            while len(out) > prev + 1:
                popped = out.pop()
                if idx.get(popped, -1) == len(out):
                    del idx[popped]
        else:
            idx[c] = len(out)
            out.append(c)
    return out


def _wall_follow_one(
    cost: list[int],
    pos: int,
    obstacle: int,
    on_right: int,
    w: int,
    h: int,
) -> tuple[int, int, int, int]:
    """Take one wall-follow step. Returns (new_pos, new_obstacle,
    new_on_right, status) where status is 0=moved, 1=surrounded.

    The returned `new_on_right` may differ from the input if the walker
    hit an off-map cell during this step and flipped sides — the caller
    must persist this updated side for subsequent steps.

    Inlined from `wall_follow_step`. on_right=0 (CW), on_right=1 (CCW).
    """
    # direction_to_cell(pos, obstacle):
    px = pos % MAX_WIDTH
    py = pos // MAX_WIDTH
    ox = obstacle % MAX_WIDTH
    oy = obstacle // MAX_WIDTH
    dx = ox - px
    dy = oy - py
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    # (sx, sy) -> dir
    if sx == 0 and sy < 0:
        direction = 0
    elif sx > 0 and sy < 0:
        direction = 1
    elif sx > 0 and sy == 0:
        direction = 2
    elif sx > 0 and sy > 0:
        direction = 3
    elif sx == 0 and sy > 0:
        direction = 4
    elif sx < 0 and sy > 0:
        direction = 5
    elif sx < 0 and sy == 0:
        direction = 6
    else:
        direction = 7

    new_obstacle = obstacle
    for _ in range(8):
        direction = direction + 7 & 7 if on_right else direction + 1 & 7
        ndi = _DI[direction]
        ni = pos + ndi
        ndx = _DX[direction]
        ndy = _DY[direction]
        nx = px + ndx
        ny = py + ndy
        on_map = 0 <= nx < w and 0 <= ny < h
        if on_map and cost[ni] < INF:
            return ni, new_obstacle, on_right, 0
        if on_map:
            new_obstacle = ni
    return pos, obstacle, on_right, 1


def _walk_perim(
    cost: list[int],
    hit_pos: int,
    hit_obstacle: int,
    side: int,
    hit_d: int,
    gx: int,
    gy: int,
    w: int,
    h: int,
    safety_cap: int,
) -> tuple[list[int], int, int, bool]:
    """Walk one wall-follow direction from hit_pos until closure or
    surrounded. Returns (perim, best_idx, best_d, closed).
    """
    perim: list[int] = [hit_pos]
    best_d = hit_d
    best_idx = 0
    wp = hit_pos
    wob = hit_obstacle
    wside = side
    while True:
        wp, wob, wside, status = _wall_follow_one(cost, wp, wob, wside, w, h)
        if status == 1:
            return perim, best_idx, best_d, False
        perim.append(wp)
        wpx = wp % MAX_WIDTH
        wpy = wp // MAX_WIDTH
        ddx = wpx - gx
        ddy = wpy - gy
        dd = ddx * ddx + ddy * ddy
        if dd < best_d:
            best_d = dd
            best_idx = len(perim) - 1
        if wp == hit_pos:
            return perim, best_idx, best_d, True
        if len(perim) > safety_cap:
            return perim, best_idx, best_d, False


def _bug1_path_one(
    cost: list[int],
    si: int,
    gi: int,
    on_right: int,
    w: int,
    h: int,
) -> list[int] | None:
    """Bug1 from start to goal, single wall-side. Walks the perimeter
    of each obstacle, records closest point, traverses the shorter arc
    back to it, leaves wall in the goal direction.

    Returns the trace path (start...goal) or None on no_progress /
    surrounded / safety_cap.
    """
    safety_cap = 2 * w * h + 16
    path: list[int] = [si]
    pos = si
    gx = gi % MAX_WIDTH
    gy = gi // MAX_WIDTH

    while True:
        if pos == gi:
            return path
        if len(path) > safety_cap:
            return None
        px = pos % MAX_WIDTH
        py = pos // MAX_WIDTH
        if px == gx:
            d = 0 if py > gy else 4
        elif px < gx:
            if py == gy:
                d = 2
            elif py > gy:
                d = 1
            else:
                d = 3
        elif py == gy:
            d = 6
        elif py > gy:
            d = 7
        else:
            d = 5
        ndi = _DI[d]
        ni = pos + ndi
        nx = px + _DX[d]
        ny = py + _DY[d]
        if 0 <= nx < w and 0 <= ny < h and cost[ni] < INF:
            pos = ni
            path.append(pos)
            continue
        hit_pos = pos
        hit_obstacle = ni
        if not (0 <= nx < w and 0 <= ny < h):
            hit_obstacle = pos
        hit_dx = px - gx
        hit_dy = py - gy
        hit_d = hit_dx * hit_dx + hit_dy * hit_dy

        perim, best_idx, best_d, closed = _walk_perim(
            cost,
            hit_pos,
            hit_obstacle,
            on_right,
            hit_d,
            gx,
            gy,
            w,
            h,
            safety_cap,
        )
        if not closed:
            perim2, best_idx2, best_d2, closed2 = _walk_perim(
                cost,
                hit_pos,
                hit_obstacle,
                1 - on_right,
                hit_d,
                gx,
                gy,
                w,
                h,
                safety_cap,
            )
            if closed2:
                perim, best_idx, best_d, closed = perim2, best_idx2, best_d2, True
            elif best_d2 < best_d:
                perim, best_idx, best_d = perim2, best_idx2, best_d2
        if best_d >= hit_d:
            return None
        if closed:
            forward_len = best_idx
            backward_len = len(perim) - 1 - best_idx
            if backward_len < forward_len:
                path.extend(perim[i] for i in range(len(perim) - 2, best_idx, -1))
                path.append(perim[best_idx])
            else:
                path.extend(perim[1 : best_idx + 1])
        else:
            # Incomplete perimeter — only forward arc is valid.
            path.extend(perim[1 : best_idx + 1])
        pos = perim[best_idx]


def plan_bug1(cost: list[int], si: int, gi: int, w: int, h: int) -> list[int] | None:
    """Bug1, both wall-sides; pick the shorter."""
    cw = _bug1_path_one(cost, si, gi, 0, w, h)
    ccw = _bug1_path_one(cost, si, gi, 1, w, h)
    if cw is None:
        return ccw
    if ccw is None:
        return cw
    return cw if len(cw) <= len(ccw) else ccw


def _bug2_path_one(
    cost: list[int],
    si: int,
    gi: int,
    on_right: int,
    w: int,
    h: int,
) -> list[int] | None:
    """Bug2 — leave wall when crossing the m-line at a closer point."""
    safety_cap = 2 * w * h + 16
    path: list[int] = [si]
    pos = si
    sx = si % MAX_WIDTH
    sy = si // MAX_WIDTH
    gx = gi % MAX_WIDTH
    gy = gi // MAX_WIDTH
    dx_t = gx - sx
    dy_t = gy - sy
    abs_dx = dx_t if dx_t >= 0 else -dx_t
    abs_dy = dy_t if dy_t >= 0 else -dy_t
    tol = (max(abs_dy, abs_dx)) // 2
    d_start_goal = dx_t * dx_t + dy_t * dy_t

    while True:
        if pos == gi:
            return path
        if len(path) > safety_cap:
            return None
        px = pos % MAX_WIDTH
        py = pos // MAX_WIDTH
        # Greedy step toward goal.
        if px == gx:
            d = 0 if py > gy else 4
        elif px < gx:
            if py == gy:
                d = 2
            elif py > gy:
                d = 1
            else:
                d = 3
        elif py == gy:
            d = 6
        elif py > gy:
            d = 7
        else:
            d = 5
        ndi = _DI[d]
        ni = pos + ndi
        nx = px + _DX[d]
        ny = py + _DY[d]
        if 0 <= nx < w and 0 <= ny < h and cost[ni] < INF:
            pos = ni
            path.append(pos)
            continue
        hit_pos = pos
        hit_d = (px - gx) * (px - gx) + (py - gy) * (py - gy)
        wp = hit_pos
        wob = ni
        wside = on_right
        seen: dict[int, int] = {}
        sk = (
            wp * 16
            + (
                _dir_to_goal(
                    wp % MAX_WIDTH, wp // MAX_WIDTH, wob % MAX_WIDTH, wob // MAX_WIDTH,
                )
            )
            * 2
            + wside
        )
        seen[sk] = 0
        steps_in_walk = 0
        while True:
            wp, wob, wside, status = _wall_follow_one(cost, wp, wob, wside, w, h)
            if status == 1:
                return None
            steps_in_walk += 1
            path.append(wp)
            wpx = wp % MAX_WIDTH
            wpy = wp // MAX_WIDTH
            # On m-line and closer than hit?
            cx2 = wpx - sx
            cy2 = wpy - sy
            cross = cy2 * dx_t - cx2 * dy_t
            abs_cross = cross if cross >= 0 else -cross
            on_mline = abs_cross <= tol
            forward = cx2 * dx_t + cy2 * dy_t > 0
            ddx = wpx - gx
            ddy = wpy - gy
            dist_now = ddx * ddx + ddy * ddy
            if on_mline and forward and dist_now < d_start_goal and dist_now < hit_d:
                pos = wp
                break
            wob_dir = _dir_to_goal(wpx, wpy, wob % MAX_WIDTH, wob // MAX_WIDTH)
            sk = wp * 16 + wob_dir * 2 + wside
            if sk in seen:
                return None
            seen[sk] = steps_in_walk
            if len(path) > safety_cap:
                return None


def plan_bug2(cost: list[int], si: int, gi: int, w: int, h: int) -> list[int] | None:
    cw = _bug2_path_one(cost, si, gi, 0, w, h)
    ccw = _bug2_path_one(cost, si, gi, 1, w, h)
    if cw is None:
        return ccw
    if ccw is None:
        return cw
    return cw if len(cw) <= len(ccw) else ccw


def _distbug_path_one(
    cost: list[int],
    si: int,
    gi: int,
    on_right: int,
    w: int,
    h: int,
) -> list[int] | None:
    """DistBug — leave wall when free-space ray toward goal reaches a
    point closer than the running minimum.
    """
    safety_cap = 2 * w * h + 16
    path: list[int] = [si]
    pos = si
    sx = si % MAX_WIDTH
    sy = si // MAX_WIDTH
    gx = gi % MAX_WIDTH
    gy = gi // MAX_WIDTH
    ddx = sx - gx
    ddy = sy - gy
    d_min = ddx * ddx + ddy * ddy

    while True:
        if pos == gi:
            return path
        if len(path) > safety_cap:
            return None
        px = pos % MAX_WIDTH
        py = pos // MAX_WIDTH
        if px == gx:
            d = 0 if py > gy else 4
        elif px < gx:
            if py == gy:
                d = 2
            elif py > gy:
                d = 1
            else:
                d = 3
        elif py == gy:
            d = 6
        elif py > gy:
            d = 7
        else:
            d = 5
        ndi = _DI[d]
        ni = pos + ndi
        nx = px + _DX[d]
        ny = py + _DY[d]
        if 0 <= nx < w and 0 <= ny < h and cost[ni] < INF:
            pos = ni
            path.append(pos)
            ddx = nx - gx
            ddy = ny - gy
            dd = ddx * ddx + ddy * ddy
            d_min = min(d_min, dd)
            continue
        # Wall.
        wp = pos
        wob = ni
        wside = on_right
        seen: dict[int, int] = {}
        sk = (
            wp * 16
            + (
                _dir_to_goal(
                    wp % MAX_WIDTH, wp // MAX_WIDTH, wob % MAX_WIDTH, wob // MAX_WIDTH,
                )
            )
            * 2
            + wside
        )
        seen[sk] = 0
        steps_in_walk = 0
        while True:
            wpx = wp % MAX_WIDTH
            wpy = wp // MAX_WIDTH
            rd = _dir_to_goal(wpx, wpy, gx, gy)
            rdx = _DX[rd]
            rdy = _DY[rd]
            rdi = _DI[rd]
            rx = wpx
            ry = wpy
            ri = wp
            while True:
                tx = rx + rdx
                ty = ry + rdy
                if tx < 0 or tx >= w or ty < 0 or ty >= h:
                    break
                ti = ri + rdi
                if cost[ti] >= INF:
                    break
                rx, ry, ri = tx, ty, ti
                if ri == gi:
                    break
            ddx = rx - gx
            ddy = ry - gy
            d_after = ddx * ddx + ddy * ddy
            if ri != wp and d_after < d_min:
                # Leave wall: walk the ray back to the leave-point.
                p = wp
                while p != ri:
                    p += rdi
                    path.append(p)
                pos = ri
                d_min = d_after
                break
            wp, wob, wside, status = _wall_follow_one(cost, wp, wob, wside, w, h)
            if status == 1:
                return None
            steps_in_walk += 1
            path.append(wp)
            wpx2 = wp % MAX_WIDTH
            wpy2 = wp // MAX_WIDTH
            ddx = wpx2 - gx
            ddy = wpy2 - gy
            dd = ddx * ddx + ddy * ddy
            d_min = min(d_min, dd)
            wob_dir = _dir_to_goal(wpx2, wpy2, wob % MAX_WIDTH, wob // MAX_WIDTH)
            sk = wp * 16 + wob_dir * 2 + wside
            if sk in seen:
                return None
            seen[sk] = steps_in_walk
            if len(path) > safety_cap:
                return None


def plan_distbug(cost: list[int], si: int, gi: int, w: int, h: int) -> list[int] | None:
    cw = _distbug_path_one(cost, si, gi, 0, w, h)
    ccw = _distbug_path_one(cost, si, gi, 1, w, h)
    if cw is None:
        return ccw
    if ccw is None:
        return cw
    return cw if len(cw) <= len(ccw) else ccw
