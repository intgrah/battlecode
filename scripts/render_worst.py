"""Render worst-case Bug1 queries: butterfly (plan spike) and labyrinth (step spike)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "pkg" / "bench_nav" / "src")
)

from bench_nav.common import INF, MAPS_DIR
from bench_nav.precomputation import (
    build_cost,
    build_nb,
    load_map,
    place_roads,
)
from bench_nav.stepped.bug._planner import bug1_plan_debug
from bench_nav.stepped.dp_step import dp_step
from PIL import Image, ImageDraw

CELL = 12
PAD = 0


def _load(mapname: str, *, roads: bool) -> tuple:
    mf = MAPS_DIR / f"{mapname}.map26"
    m = load_map(mf)
    tiles = [t for row in m.rows for t in row.tiles]
    n = m.width * m.height
    cost = build_cost(tiles, n)
    if roads:
        nb = build_nb(m.width, m.height)
        passable = [i for i in range(n) if cost[i] < INF]
        place_roads(tiles, cost, nb, passable)
    return m.width, m.height, cost


def _img(w: int, h: int, cost: list[int]) -> Image.Image:
    img = Image.new("RGB", (w * CELL, h * CELL), (30, 30, 30))
    d = ImageDraw.Draw(img)
    for i in range(w * h):
        x, y = i % w, i // w
        r = (x * CELL + PAD, y * CELL + PAD, (x + 1) * CELL - PAD, (y + 1) * CELL - PAD)
        if cost[i] >= INF:
            d.rectangle(r, fill=(80, 80, 80))
        else:
            d.rectangle(r, fill=(200, 200, 200))
    return img


def _draw_path(
    img: Image.Image, w: int, path: list[int], colour: tuple, width: int = 2
) -> None:
    d = ImageDraw.Draw(img)
    for i in range(len(path) - 1):
        ax, ay = path[i] % w, path[i] // w
        bx, by = path[i + 1] % w, path[i + 1] // w
        d.line(
            (
                ax * CELL + CELL // 2,
                ay * CELL + CELL // 2,
                bx * CELL + CELL // 2,
                by * CELL + CELL // 2,
            ),
            fill=colour,
            width=width,
        )


def _draw_cell(
    img: Image.Image, w: int, cell: int, colour: tuple, size: int = 4
) -> None:
    d = ImageDraw.Draw(img)
    x, y = cell % w, cell // w
    cx, cy = x * CELL + CELL // 2, y * CELL + CELL // 2
    d.ellipse((cx - size, cy - size, cx + size, cy + size), fill=colour)


def _walked_path(
    w: int, h: int, cost: list[int], path: list[int], si: int, gi: int
) -> list[int]:
    if not path:
        return [si]
    n = len(cost)
    pmap = {c: i for i, c in enumerate(path)}
    pos = si
    walked = [si]
    for _ in range(8 * n):
        if pos == gi:
            break
        nxt = dp_step(w, cost, h, pos, pmap)
        if nxt == pos:
            break
        pos = nxt
        walked.append(pos)
    return walked


def render(mapname: str, si: int, gi: int, *, roads: bool, outpath: Path) -> None:
    w, h, cost = _load(mapname, roads=roads)
    path, perims = bug1_plan_debug(cost, w, h, si, gi)

    panel_w = w * CELL
    panel_h = h * CELL
    gap = 8
    img = Image.new("RGB", (panel_w * 3 + gap * 2, panel_h + 20), (15, 15, 15))

    perim_img = _img(w, h, cost)
    raw_img = _img(w, h, cost)
    walk_img = _img(w, h, cost)

    perim_cols = [(255, 100, 50), (50, 150, 255), (200, 50, 200), (50, 200, 100)]
    for pi, perim in enumerate(perims):
        _draw_path(perim_img, w, perim, perim_cols[pi % len(perim_cols)], width=1)
    if path:
        _draw_path(perim_img, w, path, (255, 255, 100), width=1)

    if path:
        _draw_path(raw_img, w, path, (255, 220, 50), width=2)

    walked = _walked_path(w, h, cost, path or [], si, gi)
    _draw_path(walk_img, w, walked, (80, 220, 80), width=2)

    for panel in (perim_img, raw_img, walk_img):
        _draw_cell(panel, w, si, (255, 0, 0))
        _draw_cell(panel, w, gi, (0, 255, 0))
        if path is None and perims:
            hit = perims[-2][0] if len(perims) >= 2 else perims[-1][0]
            _draw_cell(panel, w, hit, (255, 255, 0), size=5)

    img.paste(perim_img, (0, 0))
    img.paste(raw_img, (panel_w + gap, 0))
    img.paste(walk_img, (panel_w * 2 + gap * 2, 0))

    d = ImageDraw.Draw(img)
    sc = "with_roads" if roads else "no_roads"
    label = f"{mapname} {sc}  {si}->{gi}  plan={'OK' if path else 'FAIL'}  walked={len(walked)}"
    d.text((4, panel_h + 4), label, fill=(200, 200, 200))

    img.save(outpath)
    print(f"wrote {outpath}")


import csv

out = Path("bench_nav_renders")
out.mkdir(exist_ok=True)

_csv = (
    Path(__file__).resolve().parents[1] / "pkg" / "bench_nav" / "bench_nav_stepped.csv"
)
with _csv.open() as _f:
    _rows = [
        r
        for r in csv.DictReader(_f)
        if r["algo"] == "bug-bug1" and r["ref_reachable"] == "1" and r["reached"] == "1"
    ]

_by_peak = sorted(_rows, key=lambda r: -float(r["peak_step_us"]))[:3]
_by_opt = sorted(_rows, key=lambda r: -float(r["opt_ratio"]))[:3]

for _tag, _list in (("peak", _by_peak), ("opt", _by_opt)):
    for _r in _list:
        _mapname = _r["map"]
        _si = int(_r["start"])
        _gi = int(_r["goal"])
        _roads = _r["scenario"] == "with_roads"
        _sc = "roads" if _roads else "noroads"
        _val = float(_r["peak_step_us"]) if _tag == "peak" else float(_r["opt_ratio"])
        render(
            _mapname,
            _si,
            _gi,
            roads=_roads,
            outpath=out / f"{_tag}_{_val:.0f}_{_mapname}_{_si}_{_gi}_{_sc}.png",
        )
