"""Single-bot Voronoi-discovery simulation.

Each turn the bot:
  1. Sees the 69 tiles within r²≤20 of its current position.
  2. Identifies new wall-outline-edge sites in vision; queues them.
  3. Picks a random reachable waypoint (or keeps the existing one);
     BFS-pathfinds toward it (using ground truth — caveat: real bot
     would use only its observed map).
  4. Takes one 8-connected step along the path.
  5. Inserts up to N queued sites into the Voronoi via Bowyer-Watson
     incremental Delaunay (Voronoi is the dual: each Delaunay triangle's
     circumcentre is a Voronoi vertex; adjacent triangles' circumcentres
     are connected by Voronoi edges).

Output: PNG sequence under /tmp/voronoi_sim/.

Pure Python (no numpy/scipy). Bowyer-Watson is O(N) per insertion in the
naive form (linear scan of triangles for the bad set). Point-location
walking would speed it up but isn't implemented here.
"""

from __future__ import annotations

import heapq
import math
import random
import subprocess
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.replay import load_map

ENV_EMPTY = 0
ENV_WALL = 1
ENV_TI = 2
ENV_AX = 3

VISION_R2 = 20
CELL = 12
SS = 2
SITE_BUDGET_PER_TURN = 4


def load_world(
    map_path: str,
) -> tuple[int, int, list[list[int]], list[tuple[int, int]]]:
    m = load_map(map_path)
    w, h = m.width, m.height
    tiles: list[list[int]] = [[int(t) for t in row.tiles] for row in m.rows]
    cores = [(c.position.x, c.position.y) for c in m.cores]
    return w, h, tiles, cores


def vision_tiles(bx: int, by: int, w: int, h: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            if dx * dx + dy * dy > VISION_R2:
                continue
            x, y = bx + dx, by + dy
            if 0 <= x < w and 0 <= y < h:
                out.append((x, y))
    return out


def discover_sites(
    tiles: list[list[int]],
    vis: list[tuple[int, int]],
    known: set[tuple[float, float]],
    w: int,
    h: int,
) -> list[tuple[float, float]]:
    """Wall-outline sample points: edge midpoints AND grid corners that
    are adjacent to passable space.

    Edge midpoints alone leave 1-tile-wide doorways under-sampled — the
    point-Voronoi can't triangulate the gap because only 2 sites bracket
    it. Adding corner sites gives the third point needed for triangle
    circumcenters to land in narrow doorways."""
    new: list[tuple[float, float]] = []
    for x, y in vis:
        if tiles[y][x] != ENV_WALL:
            continue
        # Edge midpoints (whose other side is passable / OOB)
        for nx, ny, sx, sy in (
            (x - 1, y, float(x), y + 0.5),
            (x + 1, y, float(x + 1), y + 0.5),
            (x, y - 1, x + 0.5, float(y)),
            (x, y + 1, x + 0.5, float(y + 1)),
        ):
            if 0 <= nx < w and 0 <= ny < h and tiles[ny][nx] == ENV_WALL:
                continue
            site = (sx, sy)
            if site not in known:
                known.add(site)
                new.append(site)
        # Grid corners exposed to passable space (any of the 4 incident
        # tiles is passable / OOB)
        for cx, cy in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)):
            exposed = False
            for tx, ty in (
                (cx - 1, cy - 1),
                (cx, cy - 1),
                (cx - 1, cy),
                (cx, cy),
            ):
                if not (0 <= tx < w and 0 <= ty < h):
                    exposed = True
                    break
                if tiles[ty][tx] != ENV_WALL:
                    exposed = True
                    break
            if not exposed:
                continue
            site = (float(cx), float(cy))
            if site not in known:
                known.add(site)
                new.append(site)
    return new


def bfs_path(
    tiles: list[list[int]],
    w: int,
    h: int,
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    if start == goal:
        return [start]
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    q: deque[tuple[int, int]] = deque([start])
    found = False
    while q:
        cur = q.popleft()
        if cur == goal:
            found = True
            break
        cx, cy = cur
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                if tiles[ny][nx] == ENV_WALL:
                    continue
                if (nx, ny) in parent:
                    continue
                parent[(nx, ny)] = cur
                q.append((nx, ny))
    if not found:
        return None
    path: list[tuple[int, int]] = []
    cur2: tuple[int, int] | None = goal
    while cur2 is not None:
        path.append(cur2)
        cur2 = parent[cur2]
    return list(reversed(path))


# ---------- Bowyer-Watson incremental Delaunay ----------


class Triangle:
    __slots__ = ("a", "b", "c", "cx", "cy", "r2")

    def __init__(
        self, a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
    ) -> None:
        self.a = a
        self.b = b
        self.c = c
        ax, ay = a
        bx, by = b
        cx, cy = c
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if d == 0:
            self.cx = 0.0
            self.cy = 0.0
            self.r2 = float("inf")
            return
        asq = ax * ax + ay * ay
        bsq = bx * bx + by * by
        csq = cx * cx + cy * cy
        ux = (asq * (by - cy) + bsq * (cy - ay) + csq * (ay - by)) / d
        uy = (asq * (cx - bx) + bsq * (ax - cx) + csq * (bx - ax)) / d
        self.cx = ux
        self.cy = uy
        self.r2 = (ax - ux) ** 2 + (ay - uy) ** 2

    def in_circle(self, p: tuple[float, float]) -> bool:
        px, py = p
        return (px - self.cx) ** 2 + (py - self.cy) ** 2 < self.r2

    def edges(
        self,
    ) -> tuple[
        tuple[tuple[float, float], tuple[float, float]],
        tuple[tuple[float, float], tuple[float, float]],
        tuple[tuple[float, float], tuple[float, float]],
    ]:
        return ((self.a, self.b), (self.b, self.c), (self.c, self.a))

    def vertices(
        self,
    ) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
        return (self.a, self.b, self.c)


def super_triangle(w: int, h: int) -> Triangle:
    m = max(w, h) * 20
    return Triangle((-m, -m), (3 * m, -m), (0.0, 3 * m))


def insert_site(
    triangles: list[Triangle],
    site: tuple[float, float],
) -> tuple[list[Triangle], list[Triangle]]:
    """Returns (removed, added) for incremental medial-graph update."""
    bad: list[Triangle] = [t for t in triangles if t.in_circle(site)]
    if not bad:
        return [], []
    edge_count: dict[tuple[tuple[float, float], tuple[float, float]], int] = {}
    for t in bad:
        for e in t.edges():
            a, b = e
            ek = (a, b) if a < b else (b, a)
            edge_count[ek] = edge_count.get(ek, 0) + 1
    boundary = [e for e, c in edge_count.items() if c == 1]
    bad_ids = {id(t) for t in bad}
    triangles[:] = [t for t in triangles if id(t) not in bad_ids]
    added: list[Triangle] = []
    for p, q in boundary:
        nt = Triangle(p, q, site)
        triangles.append(nt)
        added.append(nt)
    return bad, added


def voronoi_edges(
    triangles: list[Triangle],
    super_verts: set[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    edge_tris: dict[
        tuple[tuple[float, float], tuple[float, float]], list[Triangle]
    ] = {}
    for t in triangles:
        if any(v in super_verts for v in t.vertices()):
            continue
        for e in t.edges():
            a, b = e
            ek = (a, b) if a < b else (b, a)
            edge_tris.setdefault(ek, []).append(t)
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for tris in edge_tris.values():
        if len(tris) != 2:
            continue
        out.append(((tris[0].cx, tris[0].cy), (tris[1].cx, tris[1].cy)))
    return out


# ---------- Hand-rolled axis-aligned wall geo (no shapely) ----------


def _seg_crosses_wall(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    tiles: list[list[int]],
    w: int,
    h: int,
) -> bool:
    # No-op: do not filter Voronoi edges by tile-rasterized passability.
    # Both the multi-sample and midpoint-only versions disconnected the
    # medial graph at narrow gaps. We instead rely on clearance values
    # (circumradius) and the prune/identify-regions phases to handle
    # spurious wall-side vertices.
    del x0, y0, x1, y1, tiles, w, h
    return False


# ---------- BWTA pipeline ----------


def build_obstacle_graph(
    discovered_walls: set[tuple[int, int]],
    w: int,
    h: int,
) -> list[tuple[float, float]]:
    """Phase 1: extract wall outline as edge midpoints.
    Each wall tile contributes a midpoint per cardinal edge whose other
    side is passable / OOB. (We use midpoint sites as a point-Voronoi
    proxy for the segment-Voronoi BWTA uses; same medial-axis structure
    where it matters, far cheaper to compute incrementally.)"""
    out: list[tuple[float, float]] = []
    for x, y in discovered_walls:
        for nx, ny, sx, sy in (
            (x - 1, y, float(x), y + 0.5),
            (x + 1, y, float(x + 1), y + 0.5),
            (x, y - 1, x + 0.5, float(y)),
            (x, y + 1, x + 0.5, float(y + 1)),
        ):
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) in discovered_walls:
                continue
            out.append((sx, sy))
    return out


def _is_passable_circumcenter(
    t: Triangle,
    super_verts: set[tuple[float, float]],
    w: int,
    h: int,
) -> bool:
    # Filtering wall-tile circumcenters disconnected the medial graph at
    # narrow gaps (a wall-side circumcenter is often the transit vertex
    # between two passable circumcenters in a doorway). Keep every
    # in-bounds non-super circumcenter; clearance already encodes how
    # close it is to the obstacle surface.
    if any(v in super_verts for v in t.vertices()):
        return False
    ix = int(t.cx) if t.cx >= 0 else int(t.cx) - 1
    iy = int(t.cy) if t.cy >= 0 else int(t.cy) - 1
    return 0 <= ix < w and 0 <= iy < h


MedialState = tuple[
    dict[int, tuple[float, float, float]],
    dict[tuple[tuple[float, float], tuple[float, float]], list[Triangle]],
    dict[int, list[int]],
]


def build_medial_graph(
    triangles: list[Triangle],
    super_verts: set[tuple[float, float]],
    tiles: list[list[int]],
    w: int,
    h: int,
) -> MedialState:
    """Voronoi dual → medial-axis graph (initial full build).
    Returns (valid, edge_to_tris, adj):
      valid[id(t)]      = (cx, cy, clearance) for passable circumcenters
      edge_to_tris[ek]  = triangles using Delaunay edge ek (canonical pair)
      adj[id(t)]        = neighbors via passable Voronoi edges
    edge_to_tris is kept around so update_medial_graph can patch the delta."""
    valid: dict[int, tuple[float, float, float]] = {}
    for t in triangles:
        if _is_passable_circumcenter(t, super_verts, w, h):
            valid[id(t)] = (t.cx, t.cy, math.sqrt(t.r2))

    edge_to_tris: dict[
        tuple[tuple[float, float], tuple[float, float]],
        list[Triangle],
    ] = {}
    for t in triangles:
        for e in t.edges():
            a, b = e
            ek = (a, b) if a < b else (b, a)
            edge_to_tris.setdefault(ek, []).append(t)

    adj: dict[int, list[int]] = {vid: [] for vid in valid}
    for tris in edge_to_tris.values():
        if len(tris) != 2:
            continue
        ta, tb = tris
        ida, idb = id(ta), id(tb)
        if ida not in valid or idb not in valid:
            continue
        ax, ay, _ = valid[ida]
        bx, by, _ = valid[idb]
        if _seg_crosses_wall(ax, ay, bx, by, tiles, w, h):
            continue
        adj[ida].append(idb)
        adj[idb].append(ida)
    return valid, edge_to_tris, adj


def update_medial_graph(
    state: MedialState,
    removed: list[Triangle],
    added: list[Triangle],
    super_verts: set[tuple[float, float]],
    tiles: list[list[int]],
    w: int,
    h: int,
) -> None:
    """Incremental medial-graph patch from one B-W insertion's delta.

    Cost is O(|removed| + |added|) plus wall-cross tests on the affected
    edge set (≤ 3 * (|removed| + |added|))."""
    valid, edge_to_tris, adj = state
    affected: set[tuple[tuple[float, float], tuple[float, float]]] = set()

    # Drop removed triangles from valid / edge_to_tris / adj.
    for t in removed:
        tid = id(t)
        if tid in valid:
            del valid[tid]
        for e in t.edges():
            a, b = e
            ek = (a, b) if a < b else (b, a)
            lst = edge_to_tris.get(ek)
            if lst is None:
                continue
            new_lst = [tt for tt in lst if id(tt) != tid]
            if new_lst:
                edge_to_tris[ek] = new_lst
            else:
                del edge_to_tris[ek]
            affected.add(ek)
        ns = adj.pop(tid, None)
        if ns is not None:
            for n in ns:
                nl = adj.get(n)
                if nl is not None and tid in nl:
                    nl.remove(tid)

    # Insert added triangles into valid / edge_to_tris.
    for t in added:
        tid = id(t)
        if _is_passable_circumcenter(t, super_verts, w, h):
            valid[tid] = (t.cx, t.cy, math.sqrt(t.r2))
            adj[tid] = []
        for e in t.edges():
            a, b = e
            ek = (a, b) if a < b else (b, a)
            edge_to_tris.setdefault(ek, []).append(t)
            affected.add(ek)

    # Re-evaluate adjacency on affected edges only.
    for ek in affected:
        tris = edge_to_tris.get(ek)
        if tris is None or len(tris) != 2:
            continue
        ta, tb = tris
        ida, idb = id(ta), id(tb)
        if ida not in valid or idb not in valid:
            continue
        if idb in adj[ida]:
            continue  # already wired
        ax, ay, _ = valid[ida]
        bx, by, _ = valid[idb]
        if _seg_crosses_wall(ax, ay, bx, by, tiles, w, h):
            continue
        adj[ida].append(idb)
        adj[idb].append(ida)


def prune_graph(
    valid: dict[int, tuple[float, float, float]],
    adj: dict[int, list[int]],
) -> tuple[
    dict[int, tuple[float, float, float]],
    dict[int, list[int]],
]:
    """BWTA leaf prune: a degree-1 node with clearance < its neighbor's
    is a spur whose disk is dominated by the parent's, so it's not part
    of the medial axis. Iterate to fixed point."""
    valid = dict(valid)
    adj = {k: list(v) for k, v in adj.items()}
    leaves = [v for v, ns in adj.items() if len(ns) == 1]
    while leaves:
        next_leaves: list[int] = []
        for leaf in leaves:
            ns = adj.get(leaf)
            if ns is None or len(ns) != 1:
                continue
            parent = ns[0]
            if parent not in valid:
                del adj[leaf]
                del valid[leaf]
                continue
            if valid[leaf][2] < valid[parent][2]:
                del adj[leaf]
                del valid[leaf]
                pn = adj[parent]
                if leaf in pn:
                    pn.remove(leaf)
                if len(pn) == 1:
                    next_leaves.append(parent)
        leaves = next_leaves
    return valid, adj


def identify_regions(
    valid: dict[int, tuple[float, float, float]],
    adj: dict[int, list[int]],
    tiles: list[list[int]],
    w: int,
    h: int,
    min_clearance: float = 1.0,
) -> list[int]:
    """Region nodes = local maxima of clearance, restricted to passable
    tiles AND clearance >= min_clearance. min_clearance keeps narrow
    corridor plateaus (1-tile = clearance 0.5) from being mistaken for
    regions; only 2-tile-wide+ open areas qualify. Tied plateaus inside
    a room are collapsed to one representative."""
    candidate: set[int] = set()
    for v, ns in adj.items():
        cx_, cy_, c = valid[v]
        if c < min_clearance:
            continue
        ix = int(cx_) if cx_ >= 0 else int(cx_) - 1
        iy = int(cy_) if cy_ >= 0 else int(cy_) - 1
        if not (0 <= ix < w and 0 <= iy < h):
            continue
        if tiles[iy][ix] == ENV_WALL:
            continue
        ok = True
        for n in ns:
            if valid[n][2] > c:
                ok = False
                break
        if ok:
            candidate.add(v)

    seen: set[int] = set()
    out: list[int] = []
    for v in candidate:
        if v in seen:
            continue
        seen.add(v)
        component = [v]
        stack = [v]
        while stack:
            cur = stack.pop()
            for n in adj.get(cur, ()):
                if n in candidate and n not in seen:
                    seen.add(n)
                    component.append(n)
                    stack.append(n)
        out.append(max(component))
    return out


def identify_chokes(
    valid: dict[int, tuple[float, float, float]],
    adj: dict[int, list[int]],
    regions: list[int],
) -> tuple[
    dict[int, int],
    dict[tuple[int, int], tuple[int, float]],
]:
    """BWTA paper, literal: 'on each path between two adjacent region
    nodes, find the local minimum of clearance.'

    Clearance-watershed: flood region labels through the medial graph
    in descending-clearance order via a priority queue. The first time
    a vertex would be claimed by a different region than already owns
    it, we've found the saddle (= max-bottleneck path's bottleneck =
    the local minimum of clearance the paper describes).

    Returns (region_of, pair_choke):
      region_of[v]            = which raw region's flood claimed v
      pair_choke[(rA, rB)]    = (saddle_vertex, saddle_clearance), rA < rB
    The region_of map is needed downstream to place the choke marker on
    the lowest-clearance *passable* boundary vertex (the watershed-meet
    vertex itself is often a wall-side transit vertex)."""
    if not regions:
        return {}, {}
    region_of: dict[int, int] = {r: r for r in regions}
    pq: list[tuple[float, int, int]] = []
    for r in regions:
        for n in adj.get(r, ()):
            if n not in region_of:
                heapq.heappush(pq, (-valid[n][2], n, r))

    pair_choke: dict[tuple[int, int], tuple[int, float]] = {}
    while pq:
        neg_clr, v, src = heapq.heappop(pq)
        owner = region_of.get(v)
        if owner is None:
            region_of[v] = src
            for n in adj.get(v, ()):
                if region_of.get(n) != src:
                    heapq.heappush(pq, (-valid[n][2], n, src))
        elif owner != src:
            pair = (min(src, owner), max(src, owner))
            if pair not in pair_choke:
                pair_choke[pair] = (v, -neg_clr)
    return region_of, pair_choke


def detect_passage_chokes_tile(
    discovered_walls: set[tuple[int, int]],
    discovered_passable: set[tuple[int, int]],
    w: int,
    h: int,
) -> list[tuple[int, int, float]]:
    """Tile-based 1-wide-corridor chokepoint detector.

    A passable tile is a chokepoint candidate if it has walls (or OOB)
    on at least one pair of opposite cardinal sides — that's the
    definition of a 1-tile-wide corridor. Long corridors are
    run-suppressed by 4-connected component, keeping one chokepoint per
    corridor at the component's median tile.

    Uses only OBSERVED tiles: an unknown side is treated as 'not wall'
    so the bot doesn't fabricate chokes from unexplored space."""

    def is_wall(x: int, y: int) -> bool:
        if not (0 <= x < w and 0 <= y < h):
            return True
        return (x, y) in discovered_walls

    candidates: list[tuple[int, int]] = []
    for x, y in discovered_passable:
        wn_s = is_wall(x, y - 1) and is_wall(x, y + 1)
        we_w = is_wall(x - 1, y) and is_wall(x + 1, y)
        if wn_s or we_w:
            candidates.append((x, y))

    cset = set(candidates)
    seen: set[tuple[int, int]] = set()
    out: list[tuple[int, int, float]] = []
    for c in candidates:
        if c in seen:
            continue
        component: list[tuple[int, int]] = [c]
        stack: list[tuple[int, int]] = [c]
        seen.add(c)
        while stack:
            cx, cy = stack.pop()
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nc = (cx + dx, cy + dy)
                if nc in cset and nc not in seen:
                    seen.add(nc)
                    component.append(nc)
                    stack.append(nc)
        component.sort()
        mx, my = component[len(component) // 2]
        out.append((mx, my, 0.5))
    return out


def place_chokes(
    valid: dict[int, tuple[float, float, float]],
    adj: dict[int, list[int]],
    region_of: dict[int, int],
    region_to_group: dict[int, int],
    tiles: list[list[int]],
    w: int,
    h: int,
) -> list[int]:
    """For each cross-group adjacency in the watershed tessellation,
    pick the lowest-clearance medial vertex on the boundary that snaps
    to a passable tile. The watershed's own saddle-meet vertex is
    correct in *clearance* but often sits inside a wall (it's a transit
    vertex on the dual graph); for display/decision use we want the
    actual narrow passable position."""
    best: dict[tuple[int, int], tuple[int, float]] = {}
    for u, ns in adj.items():
        ru = region_of.get(u)
        if ru is None:
            continue
        gu = region_to_group.get(ru)
        if gu is None:
            continue
        cu_x, cu_y, cu = valid[u]
        ux = int(cu_x) if cu_x >= 0 else int(cu_x) - 1
        uy = int(cu_y) if cu_y >= 0 else int(cu_y) - 1
        u_pass = 0 <= ux < w and 0 <= uy < h and tiles[uy][ux] != ENV_WALL
        for v in ns:
            if u >= v:
                continue
            rv = region_of.get(v)
            if rv is None:
                continue
            gv = region_to_group.get(rv)
            if gv is None or gv == gu:
                continue
            cv_x, cv_y, cv = valid[v]
            vx = int(cv_x) if cv_x >= 0 else int(cv_x) - 1
            vy = int(cv_y) if cv_y >= 0 else int(cv_y) - 1
            v_pass = 0 <= vx < w and 0 <= vy < h and tiles[vy][vx] != ENV_WALL
            if not u_pass and not v_pass:
                continue
            if u_pass and (not v_pass or cu <= cv):
                cand_v, cand_c = u, cu
            else:
                cand_v, cand_c = v, cv
            pair = (min(gu, gv), max(gu, gv))
            cur = best.get(pair)
            if cur is None or cand_c < cur[1]:
                best[pair] = (cand_v, cand_c)

    seen: set[int] = set()
    out: list[int] = []
    for cand_v, _ in best.values():
        if cand_v not in seen:
            seen.add(cand_v)
            out.append(cand_v)
    return out


def merge_regions(
    valid: dict[int, tuple[float, float, float]],
    regions: list[int],
    pair_chokes: dict[tuple[int, int], tuple[int, float]],
    ratio: float = 0.7,
) -> list[list[int]]:
    """DSU directly over regions: union (rA, rB) when their saddle's
    clearance is high enough relative to their own clearances.

    A pair merges iff `saddle_clr >= ratio * min(rA.clr, rB.clr)`. Cost
    is O(P * inverse-Ackermann(R)) where P = #region pairs reported."""
    if not regions:
        return []
    parent: dict[int, int] = {r: r for r in regions}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (ra, rb), (_, clr) in pair_chokes.items():
        thresh = ratio * min(valid[ra][2], valid[rb][2])
        if clr < thresh:
            continue
        pa, pb = find(ra), find(rb)
        if pa != pb:
            parent[pa] = pb

    groups: dict[int, list[int]] = {}
    for r in regions:
        groups.setdefault(find(r), []).append(r)
    return list(groups.values())


def simplify_for_game(
    valid: dict[int, tuple[float, float, float]],
    region_groups: list[list[int]],
    chokes: list[int],
    tiles: list[list[int]],
    w: int,
    h: int,
) -> tuple[
    list[tuple[int, int, int, float]],
    list[tuple[int, int, float]],
]:
    """Snap region centroids and chokes to integer tiles.
    Filters chokes whose snapped tile is a wall (those are wall-side
    transit vertices kept for medial-graph connectivity, not real
    passages) and dedupes by tile coord so output is stable across
    turns once the underlying geometry stops changing."""
    region_centers: list[tuple[int, int, int, float]] = []
    for rid, group in enumerate(region_groups):
        sx = sy = sw = 0.0
        cmax = 0.0
        for v in group:
            cx_, cy_, clr = valid[v]
            sx += cx_ * clr
            sy += cy_ * clr
            sw += clr
            cmax = max(cmax, clr)
        if sw <= 0:
            continue
        ix = max(0, min(w - 1, round(sx / sw)))
        iy = max(0, min(h - 1, round(sy / sw)))
        region_centers.append((rid, ix, iy, cmax))

    by_tile: dict[tuple[int, int], float] = {}
    for v in chokes:
        cx_, cy_, clr = valid[v]
        ix = max(0, min(w - 1, round(cx_)))
        iy = max(0, min(h - 1, round(cy_)))
        if tiles[iy][ix] == ENV_WALL:
            continue
        cur = by_tile.get((ix, iy))
        if cur is None or clr < cur:
            by_tile[(ix, iy)] = clr
    choke_tiles = [(ix, iy, clr) for (ix, iy), clr in by_tile.items()]
    return region_centers, choke_tiles


# ---------- Render ----------


def render_frame(
    w: int,
    h: int,
    tiles: list[list[int]],
    bx: int,
    by: int,
    vis: list[tuple[int, int]],
    known_sites: set[tuple[float, float]],
    edges: list[tuple[tuple[float, float], tuple[float, float]]],
    waypoint: tuple[int, int] | None,
    region_centers: list[tuple[int, int, int, float]],
    choke_tiles: list[tuple[int, int, float]],
    out_path: str | None,
    stats: str,
) -> Image.Image:
    cs = CELL * SS
    img = Image.new("RGB", (w * cs, h * cs), (255, 255, 255))
    d = ImageDraw.Draw(img)

    for y in range(h):
        for x in range(w):
            t = tiles[y][x]
            if t == ENV_WALL:
                col = (0, 0, 0)
            elif t == ENV_TI:
                col = (90, 160, 230)
            elif t == ENV_AX:
                col = (240, 160, 60)
            else:
                continue
            d.rectangle(
                [x * cs, y * cs, (x + 1) * cs - 1, (y + 1) * cs - 1],
                fill=col,
            )

    grid_col = (220, 220, 220)
    for x in range(w + 1):
        d.line([(x * cs, 0), (x * cs, h * cs - 1)], fill=grid_col, width=1)
    for y in range(h + 1):
        d.line([(0, y * cs), (w * cs - 1, y * cs)], fill=grid_col, width=1)

    # Vision: thin yellow rect outline
    vis_set = set(vis)
    for x, y in vis_set:
        d.rectangle(
            [x * cs, y * cs, (x + 1) * cs - 1, (y + 1) * cs - 1],
            outline=(220, 200, 80),
            width=1,
        )

    # Voronoi edges (clip to image bounds; skip edges that cross walls)
    def crosses_wall(x0: float, y0: float, x1: float, y1: float) -> bool:
        dx, dy = x1 - x0, y1 - y0
        n = max(int(math.hypot(dx, dy) * 4) + 1, 4)
        for i in range(1, n):
            t = i / n
            xx = x0 + t * dx
            yy = y0 + t * dy
            ix, iy = math.floor(xx), math.floor(yy)
            if 0 <= ix < w and 0 <= iy < h and tiles[iy][ix] == ENV_WALL:
                return True
        return False

    for (x0, y0), (x1, y1) in edges:
        # clip far-out edges
        if not (
            -2 <= x0 <= w + 2
            and -2 <= y0 <= h + 2
            and -2 <= x1 <= w + 2
            and -2 <= y1 <= h + 2
        ):
            continue
        if crosses_wall(x0, y0, x1, y1):
            continue
        d.line(
            [(int(x0 * cs), int(y0 * cs)), (int(x1 * cs), int(y1 * cs))],
            fill=(50, 100, 220),
            width=SS,
        )

    # Known sites
    for sx, sy in known_sites:
        cx_, cy_ = int(sx * cs), int(sy * cs)
        r = SS
        d.ellipse([cx_ - r, cy_ - r, cx_ + r, cy_ + r], fill=(160, 100, 200))

    # Waypoint
    if waypoint is not None:
        wx, wy = waypoint
        cxw, cyw = wx * cs + cs // 2, wy * cs + cs // 2
        rw = cs // 3
        d.ellipse(
            [cxw - rw, cyw - rw, cxw + rw, cyw + rw],
            outline=(40, 160, 60),
            width=2 * SS,
        )

    # Region centers: outlined orange square with rid label
    for rid, rx, ry, _ in region_centers:
        x0 = rx * cs + 2 * SS
        y0 = ry * cs + 2 * SS
        x1 = (rx + 1) * cs - 2 * SS
        y1 = (ry + 1) * cs - 2 * SS
        d.rectangle([x0, y0, x1, y1], outline=(240, 140, 40), width=2 * SS)
        d.text(
            (rx * cs + 3 * SS, ry * cs + 3 * SS),
            str(rid),
            fill=(240, 140, 40),
        )

    # Choke tiles: filled red dot
    for cx_, cy_, _ in choke_tiles:
        cxc = cx_ * cs + cs // 2
        cyc = cy_ * cs + cs // 2
        rc = cs // 4
        d.ellipse(
            [cxc - rc, cyc - rc, cxc + rc, cyc + rc],
            fill=(220, 30, 30),
        )

    # Bot position
    cxb, cyb = bx * cs + cs // 2, by * cs + cs // 2
    rb = cs // 3
    d.ellipse([cxb - rb, cyb - rb, cxb + rb, cyb + rb], fill=(220, 30, 30))

    # Stats overlay
    d.text((4, 4), stats, fill=(0, 0, 0))

    img2 = img.resize((w * CELL, h * CELL), Image.Resampling.LANCZOS)
    if out_path is not None:
        img2.save(out_path)
    return img2


# ---------- Simulation ----------


def simulate(
    map_path: str,
    n_turns: int = 250,
    out_gif: str | None = None,
    frame_ms: int = 80,
) -> None:
    if out_gif is None:
        out_gif = str(Path(tempfile.gettempdir()) / "voronoi_sim.gif")
    w, h, tiles, cores = load_world(map_path)

    rng = random.Random(7)
    bx, by = cores[0]

    known_sites: set[tuple[float, float]] = set()
    pending: list[tuple[float, float]] = []

    super_tri = super_triangle(w, h)
    super_verts = {super_tri.a, super_tri.b, super_tri.c}
    triangles: list[Triangle] = [super_tri]

    waypoint: tuple[int, int] | None = None
    path: list[tuple[int, int]] = []

    insert_total_us = 0
    frames: list[Image.Image] = []
    per_turn_us: list[float] = []
    parts_us: dict[str, list[float]] = {
        "waypoint+bfs": [],
        "vision": [],
        "discover": [],
        "insert": [],
        "medial_upd": [],
        "obstacle_graph": [],
        "prune": [],
        "regions": [],
        "chokes": [],
        "merge": [],
        "simplify": [],
        "pipeline_total": [],
    }
    discovered_walls: set[tuple[int, int]] = set()
    discovered_passable: set[tuple[int, int]] = set()
    medial_state: MedialState = build_medial_graph(
        triangles,
        super_verts,
        tiles,
        w,
        h,
    )
    for turn in range(n_turns):
        bfs_t0 = time.perf_counter_ns()
        if waypoint is None or (bx, by) == waypoint or not path:
            for _ in range(40):
                wx = rng.randint(0, w - 1)
                wy = rng.randint(0, h - 1)
                if tiles[wy][wx] == ENV_WALL:
                    continue
                p = bfs_path(tiles, w, h, (bx, by), (wx, wy))
                if p is not None:
                    waypoint = (wx, wy)
                    path = p[1:] if len(p) > 1 else []
                    break
        if path:
            bx, by = path[0]
            path = path[1:]
        bfs_t1 = time.perf_counter_ns()
        parts_us["waypoint+bfs"].append((bfs_t1 - bfs_t0) / 1000)

        # Bot-thinking timer starts AFTER bfs (bfs is the harness step,
        # not part of the per-turn pipeline budget).
        turn_t0 = time.perf_counter_ns()

        ta = time.perf_counter_ns()
        vis = vision_tiles(bx, by, w, h)
        tb = time.perf_counter_ns()
        parts_us["vision"].append((tb - ta) / 1000)

        ta = time.perf_counter_ns()
        new = discover_sites(tiles, vis, known_sites, w, h)
        pending.extend(new)
        for vx, vy in vis:
            if tiles[vy][vx] == ENV_WALL:
                discovered_walls.add((vx, vy))
            else:
                discovered_passable.add((vx, vy))
        tb = time.perf_counter_ns()
        parts_us["discover"].append((tb - ta) / 1000)

        budget = SITE_BUDGET_PER_TURN
        ins_us = 0.0
        upd_us = 0.0
        while pending and budget > 0:
            site = pending.pop(0)
            ts = time.perf_counter_ns()
            removed, added = insert_site(triangles, site)
            te = time.perf_counter_ns()
            ins_us += (te - ts) / 1000
            ts = time.perf_counter_ns()
            update_medial_graph(
                medial_state,
                removed,
                added,
                super_verts,
                tiles,
                w,
                h,
            )
            te = time.perf_counter_ns()
            upd_us += (te - ts) / 1000
            budget -= 1
        insert_total_us += ins_us
        parts_us["insert"].append(ins_us)
        parts_us["medial_upd"].append(upd_us)

        edges = voronoi_edges(triangles, super_verts)

        valid_g, _, adj_g = medial_state

        # --- BWTA pipeline (downstream phases still full-rebuild) ---
        pipe_t0 = time.perf_counter_ns()

        ta = time.perf_counter_ns()
        _ = build_obstacle_graph(discovered_walls, w, h)
        tb = time.perf_counter_ns()
        parts_us["obstacle_graph"].append((tb - ta) / 1000)

        ta = time.perf_counter_ns()
        valid_p, adj_p = prune_graph(valid_g, adj_g)
        tb = time.perf_counter_ns()
        parts_us["prune"].append((tb - ta) / 1000)

        ta = time.perf_counter_ns()
        regions = identify_regions(valid_p, adj_p, tiles, w, h)
        tb = time.perf_counter_ns()
        parts_us["regions"].append((tb - ta) / 1000)

        ta = time.perf_counter_ns()
        region_of, pair_chokes = identify_chokes(valid_p, adj_p, regions)
        tb = time.perf_counter_ns()
        parts_us["chokes"].append((tb - ta) / 1000)

        ta = time.perf_counter_ns()
        groups = merge_regions(valid_p, regions, pair_chokes)
        tb = time.perf_counter_ns()
        parts_us["merge"].append((tb - ta) / 1000)

        # Chokepoints: tile-based 1-tile-corridor detector on the
        # observed map. The Voronoi pipeline is used for region info
        # (regions / merging) but not for choke detection — the watershed
        # saddle approach over-counted because of plateau regions, and
        # cluster-thresholding caught corner spikes alongside corridors.
        del region_of, pair_chokes  # not used for chokes

        ta = time.perf_counter_ns()
        choke_tiles = detect_passage_chokes_tile(
            discovered_walls,
            discovered_passable,
            w,
            h,
        )
        region_centers, _ = simplify_for_game(
            valid_p,
            groups,
            [],
            tiles,
            w,
            h,
        )
        tb = time.perf_counter_ns()
        parts_us["simplify"].append((tb - ta) / 1000)

        pipe_t1 = time.perf_counter_ns()
        parts_us["pipeline_total"].append((pipe_t1 - pipe_t0) / 1000)
        per_turn_us.append((pipe_t1 - turn_t0) / 1000)

        stats = (
            f"turn={turn:4d}  bot=({bx},{by})  "
            f"sites_seen={len(known_sites)}  pending={len(pending)}  "
            f"tris={len(triangles)}  edges={len(edges)}  "
            f"regions={len(region_centers)}  chokes={len(choke_tiles)}"
        )
        frame = render_frame(
            w,
            h,
            tiles,
            bx,
            by,
            vis,
            known_sites,
            edges,
            waypoint,
            region_centers,
            choke_tiles,
            None,
            stats,
        )
        frames.append(frame)

        if turn % 25 == 0:
            print(stats)

    print(
        f"\nfinal: {len(known_sites)} sites discovered, {len(triangles)} tris, "
        f"avg insert per turn = {insert_total_us / n_turns:.0f}us"
    )

    def fmt_stats(name: str, xs: list[float]) -> str:
        s = sorted(xs)
        n = len(s)
        return (
            f"  {name:14s} median={s[n // 2]:7.1f}us  "
            f"p95={s[int(n * 0.95)]:7.1f}us  "
            f"max={s[-1]:8.1f}us  "
            f"sum={sum(xs):.0f}us"
        )

    print("\nper-turn bot thinking time:")
    print(fmt_stats("TOTAL", per_turn_us))
    for k, v in parts_us.items():
        if v:
            print(fmt_stats(k, v))

    # Save MP4 via ffmpeg (much better quality than GIF for thin lines/text)
    out_path = Path(out_gif)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".mp4":
        with tempfile.TemporaryDirectory() as td:
            for i, f in enumerate(frames):
                f.save(f"{td}/{i:05d}.png")
            fps = max(1, round(1000 / frame_ms))
            cmd = [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                str(fps),
                "-i",
                f"{td}/%05d.png",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "18",
                "-preset",
                "slow",
                "-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                str(out_path),
            ]
            subprocess.run(cmd, check=True)
        print(f"wrote {out_path} ({n_turns} frames @ {fps} fps)")
    else:
        pal_frames = [
            f.convert("P", palette=Image.Palette.ADAPTIVE, colors=256) for f in frames
        ]
        pal_frames[0].save(
            out_path,
            save_all=True,
            append_images=pal_frames[1:],
            duration=frame_ms,
            loop=0,
            optimize=True,
        )
        print(f"wrote {out_path} ({n_turns} frames @ {frame_ms}ms each)")


def main() -> None:
    map_name = sys.argv[1] if len(sys.argv) > 1 else "cubes"
    map_path = f"maps/{map_name}.map26"
    n_turns = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    out_path = (
        sys.argv[3]
        if len(sys.argv) > 3
        else str(Path(tempfile.gettempdir()) / f"voronoi_sim_{map_name}.mp4")
    )
    simulate(map_path, n_turns=n_turns, out_gif=out_path)


if __name__ == "__main__":
    main()
