"""Voronoi diagram of wall-boundary sites + chokepoint detection.

Algorithm (matches the structure hinted at by `voronoi_core/` + `chokepoint.py`):
1. Sites = centres of wall tiles that have at least one passable 8-neighbour
   (i.e. wall boundary pixels). Plus a wall-padded virtual map boundary.
2. Compute continuous Voronoi diagram of those sites (scipy.spatial.Voronoi
   uses Qhull). Output is vertices + ridges (edges between adjacent cells).
3. A Voronoi vertex is equidistant from ≥3 sites — its "clearance" is that
   shared distance, i.e. the radius of the largest empty disk centred there.
   Vertices in the passable region with low clearance = narrow passages.
4. Voronoi edges (ridges) traced through passable space form the medial axis
   skeleton. Chokepoints = low-clearance vertices at the narrowest spots.

The bot would run an INCREMENTAL Fortune's-style version distributed via
markers (each wall observation = one new site event, end-of-turn budget
processes events). This script is the offline analysis equivalent — same
output (Voronoi vertices + ridges, chokepoint scoring), no incremental
machinery.

Usage: uv run python scripts/voronoi_chokes.py [map_name] [out_path]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import Voronoi

from scripts.replay import load_map

if TYPE_CHECKING:
    from proto.cambc_pb2 import Environment

ENV_EMPTY = 0
ENV_WALL = 1
ENV_TI = 2
ENV_AX = 3

CELL = 24
SS = 3  # supersample factor for anti-aliasing


def load(
    map_path: str,
) -> tuple[
    int,
    int,
    list[list[Environment]],
    list[tuple[int, int]],
    list[tuple[int, int]],
    list[tuple[int, int]],
]:
    m = load_map(map_path)
    w, h = m.width, m.height
    tiles = [list(row.tiles) for row in m.rows]
    cores = [(c.position.x, c.position.y) for c in m.cores]
    ti_ores: list[tuple[int, int]] = []
    ax_ores: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            t = tiles[y][x]
            if t == ENV_TI:
                ti_ores.append((x, y))
            elif t == ENV_AX:
                ax_ores.append((x, y))
    return w, h, tiles, cores, ti_ores, ax_ores


def collect_sites(w: int, h: int, tiles: list[list[int]]) -> list[tuple[float, float]]:
    """Sites = midpoints of wall outline edges (where wall meets passable
    or map boundary). Each wall tile contributes up to 4 sites — one per
    cardinal edge whose other side is passable / OOB.

    This places sites ON the wall surface (the boundary curve between wall
    and passable), so Voronoi vertices in 1-wide gaps land at clearance 0.5
    (half-tile units to the nearest wall outline).

    Plus virtual sites along the map boundary at edge midpoints.
    """

    def is_wall(x: int, y: int) -> bool:
        if not (0 <= x < w and 0 <= y < h):
            return True
        return tiles[y][x] == ENV_WALL

    seen: set[tuple[float, float]] = set()
    for y in range(h):
        for x in range(w):
            if tiles[y][x] != ENV_WALL:
                continue
            if not is_wall(x, y - 1):
                seen.add((x + 0.5, float(y)))
            if not is_wall(x, y + 1):
                seen.add((x + 0.5, float(y + 1)))
            if not is_wall(x - 1, y):
                seen.add((float(x), y + 0.5))
            if not is_wall(x + 1, y):
                seen.add((float(x + 1), y + 0.5))

    for x in range(w):
        seen.add((x + 0.5, 0.0))
        seen.add((x + 0.5, float(h)))
    for y in range(h):
        seen.add((0.0, y + 0.5))
        seen.add((float(w), y + 0.5))
    return sorted(seen)


def segment_crosses_wall(
    p0x: float,
    p0y: float,
    p1x: float,
    p1y: float,
    tiles: list[list[int]],
    w: int,
    h: int,
    samples: int = 0,
) -> bool:
    dx, dy = p1x - p0x, p1y - p0y
    length = math.hypot(dx, dy)
    n = max(int(length * 4) + 1, 4) if samples == 0 else samples
    for i in range(1, n):
        t = i / n
        x = p0x + t * dx
        y = p0y + t * dy
        ix, iy = math.floor(x), math.floor(y)
        if not (0 <= ix < w and 0 <= iy < h):
            continue
        if tiles[iy][ix] == ENV_WALL:
            return True
    return False


def passable_cont(tiles: list[list[int]], w: int, h: int, x: float, y: float) -> bool:
    ix, iy = math.floor(x), math.floor(y)
    if not (0 <= ix < w and 0 <= iy < h):
        return False
    return tiles[iy][ix] != ENV_WALL


def vertex_clearance(vx: float, vy: float, sites: list[tuple[float, float]]) -> float:
    best = float("inf")
    for sx, sy in sites:
        d2 = (sx - vx) * (sx - vx) + (sy - vy) * (sy - vy)
        best = min(best, d2)
    return math.sqrt(best)


def render(
    w: int,
    h: int,
    tiles: list[list[int]],
    sites: list[tuple[float, float]],
    vor: Voronoi,
    passable_vertices: list[int],
    vertex_clearances: dict[int, float],
    chokes_05: list[tuple[int, int, float]],
    chokes_15: list[tuple[int, int, float]],
    cores: list[tuple[int, int]],
    ti_ores: list[tuple[int, int]],
    ax_ores: list[tuple[int, int]],
    out_path: str,
) -> None:
    big = Image.new("RGB", (w * CELL * SS, h * CELL * SS), (255, 255, 255))
    d = ImageDraw.Draw(big)
    cs = CELL * SS

    # Pass 1: solid fills (no per-tile outline — grid drawn separately).
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
                continue  # leave white background
            x0, y0 = x * cs, y * cs
            d.rectangle([x0, y0, x0 + cs - 1, y0 + cs - 1], fill=col)

    # Pass 2: thin grid lines (one px in supersampled space → ~1/3 px after).
    grid_col = (210, 210, 210)
    for x in range(w + 1):
        d.line([(x * cs, 0), (x * cs, h * cs - 1)], fill=grid_col, width=1)
    for y in range(h + 1):
        d.line([(0, y * cs), (w * cs - 1, y * cs)], fill=grid_col, width=1)

    # Cores: 3x3 outlined squares
    for i, (x, y) in enumerate(cores):
        col = (130, 200, 255) if i == 0 else (255, 140, 130)
        x0 = (x - 1) * cs
        y0 = (y - 1) * cs
        x1 = (x + 2) * cs - 1
        y1 = (y + 2) * cs - 1
        d.rectangle([x0, y0, x1, y1], outline=col, width=3 * SS)

    # First pass: render WALL-side Voronoi edges faintly (light lavender).
    # These are the "spikes" from the medial-axis skeleton out to the walls
    # (Voronoi cell boundaries that cross through walls).
    pv_set = set(passable_vertices)
    drew_at: dict[int, bool] = dict.fromkeys(passable_vertices, False)
    medial: list[tuple[int, int]] = []
    LAVENDER = (215, 200, 235)
    for v0, v1 in vor.ridge_vertices:
        if v0 < 0 or v1 < 0:
            continue
        p0 = vor.vertices[v0]
        p1 = vor.vertices[v1]
        if not (
            -2 <= p0[0] <= w + 2
            and -2 <= p0[1] <= h + 2
            and -2 <= p1[0] <= w + 2
            and -2 <= p1[1] <= h + 2
        ):
            continue
        passable_edge = (
            v0 in pv_set
            and v1 in pv_set
            and not segment_crosses_wall(p0[0], p0[1], p1[0], p1[1], tiles, w, h)
        )
        if passable_edge:
            medial.append((v0, v1))
            continue
        x0 = int(p0[0] * cs)
        y0 = int(p0[1] * cs)
        x1 = int(p1[0] * cs)
        y1 = int(p1[1] * cs)
        d.line([(x0, y0), (x1, y1)], fill=LAVENDER, width=max(1, SS // 2))

    # Second pass: render MEDIAL AXIS edges (passable side) bold, coloured
    # by min-clearance.
    max_clear = max(vertex_clearances.values()) if vertex_clearances else 1.0
    for v0, v1 in medial:
        p0 = vor.vertices[v0]
        p1 = vor.vertices[v1]
        drew_at[v0] = True
        drew_at[v1] = True
        c0 = vertex_clearances[v0]
        c1 = vertex_clearances[v1]
        cmin = min(c0, c1)
        t = max(0.0, min(1.0, cmin / max_clear))
        # Wide → blue, narrow → red
        r = int(220 * (1 - t) + 80 * t)
        g = int(60 * (1 - t) + 160 * t)
        b = int(60 * (1 - t) + 240 * t)
        x0 = int(p0[0] * cs)
        y0 = int(p0[1] * cs)
        x1 = int(p1[0] * cs)
        y1 = int(p1[1] * cs)
        d.line([(x0, y0), (x1, y1)], fill=(r, g, b), width=SS)

    # Junction dots only: vertices with medial-axis-degree ≥ 3 (real graph
    # nodes). Skip degree-2 transit vertices along straight skeleton runs.
    medial_degree: dict[int, int] = {}
    for v0, v1 in medial:
        medial_degree[v0] = medial_degree.get(v0, 0) + 1
        medial_degree[v1] = medial_degree.get(v1, 0) + 1
    for vi, deg in medial_degree.items():
        if deg < 3:
            continue
        p = vor.vertices[vi]
        cx, cy = int(p[0] * cs), int(p[1] * cs)
        r = 2 * SS
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(240, 180, 60))

    # 0.5 chokepoints: filled red 1-tile square (label drawn post-resize).
    for x, y, _c in chokes_05:
        x0, y0 = x * cs, y * cs
        d.rectangle([x0, y0, x0 + cs - 1, y0 + cs - 1], fill=(220, 30, 30))

    # 1.5 chokepoints: 3x3 outlined region (label drawn post-resize).
    for x, y, _c in chokes_15:
        x0 = (x - 1) * cs
        y0 = (y - 1) * cs
        x1 = (x + 2) * cs - 1
        y1 = (y + 2) * cs - 1
        d.rectangle([x0, y0, x1, y1], outline=(50, 100, 220), width=2 * SS)

    img = big.resize((w * CELL, h * CELL), Image.LANCZOS)

    # Draw labels on the final-resolution image — PIL's text rendering is
    # antialiased natively at the target resolution, so we get crisp glyphs
    # rather than blurry post-resize text.
    fd = ImageDraw.Draw(img)
    try:
        font_05 = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            max(8, int(CELL * 0.6)),
        )
        font_15 = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            max(10, int(CELL * 0.9)),
        )
    except OSError:
        font_05 = ImageFont.load_default()
        font_15 = font_05

    def draw_centered(
        cx: int, cy: int, text: str, fill: tuple[int, int, int], font
    ) -> None:
        bbox = fd.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        fd.text(
            (cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]),
            text,
            fill=fill,
            font=font,
        )

    for x, y, _c in chokes_05:
        cx = x * CELL + CELL // 2
        cy = y * CELL + CELL // 2
        draw_centered(cx, cy, "0.5", (255, 255, 255), font_05)

    for x, y, _c in chokes_15:
        cx = x * CELL + CELL // 2
        cy = y * CELL + CELL // 2
        draw_centered(cx, cy, "1.5", (50, 100, 220), font_15)

    img.save(out_path)


def main() -> None:
    map_name = sys.argv[1] if len(sys.argv) > 1 else "cubes"
    map_path = f"maps/{map_name}.map26" if not map_name.endswith(".map26") else map_name
    out_path = (
        sys.argv[2] if len(sys.argv) > 2 else f"/tmp/voronoi_{Path(map_path).stem}.png"
    )

    w, h, tiles, cores, ti_ores, ax_ores = load(map_path)
    print(f"map: {map_path}  size: {w}x{h}  Ti: {len(ti_ores)}  Ax: {len(ax_ores)}")

    sites = collect_sites(w, h, tiles)
    print(f"sites: {len(sites)} (wall-boundary + virtual map-boundary)")

    vor = Voronoi(sites)
    n_v = len(vor.vertices)
    print(f"voronoi vertices: {n_v}")

    # Filter vertices to passable region
    passable_vertices: list[int] = []
    vertex_clearances: dict[int, float] = {}
    for vi in range(n_v):
        v = vor.vertices[vi]
        vx, vy = float(v[0]), float(v[1])
        if not passable_cont(tiles, w, h, vx, vy):
            continue
        c = vertex_clearance(vx, vy, sites)
        passable_vertices.append(vi)
        vertex_clearances[vi] = c
    print(f"passable-side vertices: {len(passable_vertices)}")

    # Tile-snap chokepoint scoring.
    pv_set = set(passable_vertices)
    tile_min_clr: dict[tuple[int, int], float] = {}
    for v0, v1 in vor.ridge_vertices:
        if v0 < 0 or v1 < 0:
            continue
        if v0 not in pv_set or v1 not in pv_set:
            continue
        p0 = vor.vertices[v0]
        p1 = vor.vertices[v1]
        p0x, p0y = float(p0[0]), float(p0[1])
        p1x, p1y = float(p1[0]), float(p1[1])
        if segment_crosses_wall(p0x, p0y, p1x, p1y, tiles, w, h):
            continue
        dx, dy = p1x - p0x, p1y - p0y
        length = math.hypot(dx, dy)
        n = max(int(length * 4), 1)
        for i in range(n + 1):
            t = i / max(1, n)
            x = p0x + t * dx
            y = p0y + t * dy
            ix, iy = math.floor(x), math.floor(y)
            if not (0 <= ix < w and 0 <= iy < h):
                continue
            if tiles[iy][ix] == ENV_WALL:
                continue
            clr = vertex_clearance(x, y, sites)
            key = (ix, iy)
            cur = tile_min_clr.get(key, 1e9)
            if clr < cur:
                tile_min_clr[key] = clr

    # Chokepoint = passable tile T such that:
    #   1. The medial axis passes through T (tile_min_clr[T] is set), AND
    #   2. T has walls on at least one pair of OPPOSITE cardinals (real
    #      1-wide gap perpendicular to that axis — not a concave corner
    #      where only adjacent cardinals are walls).
    # Plus suppress runs (a long 1-wide corridor: keep one per cardinal-
    # connected run, picking the cardinal-degree-2 tiles).
    def is_wall(ix: int, iy: int) -> bool:
        if not (0 <= ix < w and 0 <= iy < h):
            return True  # treat OOB as wall
        return tiles[iy][ix] == ENV_WALL

    def has_opposite_walls(x: int, y: int) -> bool:
        return (is_wall(x - 1, y) and is_wall(x + 1, y)) or (
            is_wall(x, y - 1) and is_wall(x, y + 1)
        )

    chokes_05: list[tuple[int, int, float]] = []
    seen_run: set[tuple[int, int]] = set()
    for (x, y), c in sorted(tile_min_clr.items(), key=lambda kv: kv[1]):
        if c > 0.6:
            break
        if not has_opposite_walls(x, y):
            continue
        skip = False
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            if (x + dx, y + dy) in seen_run:
                skip = True
                break
        if skip:
            continue
        chokes_05.append((x, y, c))
        seen_run.add((x, y))

    # 1.5 chokepoint = passable tile T with:
    #   - All 8 cardinal+diagonal neighbours passable (3x3 passable region
    #     centred on T) — this is the "alcove" footprint.
    #   - Walls on at least one pair of opposite sides at distance exactly 2
    #     in one direction (row T-2 wall AND row T+2 wall, OR col T-2 wall
    #     AND col T+2 wall) — pinches the alcove on that axis.
    def passable(ix: int, iy: int) -> bool:
        if not (0 <= ix < w and 0 <= iy < h):
            return False
        return tiles[iy][ix] != ENV_WALL

    chokes_15_raw: list[tuple[int, int, float]] = []
    for y in range(h):
        for x in range(w):
            if not passable(x, y):
                continue
            ok_3x3 = all(
                passable(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            )
            if not ok_3x3:
                continue
            pinch_v = is_wall(x, y - 2) and is_wall(x, y + 2)
            pinch_h = is_wall(x - 2, y) and is_wall(x + 2, y)
            if not (pinch_v or pinch_h):
                continue
            chokes_15_raw.append((x, y, 1.5))

    # Cluster aggressively: 3x3 alcoves are by nature wide; a single one
    # shouldn't be marked twice. Use cluster radius 4.
    chokes_15: list[tuple[int, int, float]] = []
    for x, y, c in chokes_15_raw:
        if all(max(abs(x - kx), abs(y - ky)) > 4 for kx, ky, _ in chokes_15):
            chokes_15.append((x, y, c))

    print(
        f"chokepoints: {len(chokes_05)} @ 0.5 (1-wide), {len(chokes_15)} @ 1.5 (3-wide)"
    )

    render(
        w,
        h,
        tiles,
        sites,
        vor,
        passable_vertices,
        vertex_clearances,
        chokes_05,
        chokes_15,
        cores,
        ti_ores,
        ax_ores,
        out_path,
    )
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
