"""Render failing bug2 cases: plan + DP-optimised walk."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "pkg" / "bench_nav" / "src")
)

from bench_nav.common import INF, MAPS_DIR
from bench_nav.precomputation import build_cost, build_nb, load_map, place_roads
from bench_nav.stepped.bug._planner import _build_mline, bug2_plan_parallel_debug
from bench_nav.stepped.dp_step import dp_step
from PIL import Image, ImageDraw

CELL = 18
RULER_STEP = 5


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
        r = (x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL)
        if cost[i] >= INF:
            d.rectangle(r, fill=(80, 80, 80))
        else:
            d.rectangle(r, fill=(200, 200, 200))
    for x in range(0, w, RULER_STEP):
        d.text((x * CELL + 1, 1), str(x), fill=(60, 60, 200))
    for y in range(0, h, RULER_STEP):
        d.text((1, y * CELL + 1), str(y), fill=(60, 60, 200))
    return img


def _draw_path(img, w, path, colour, width=2) -> None:
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


def _draw_cell(img, w, cell, colour, size=4) -> None:
    d = ImageDraw.Draw(img)
    x, y = cell % w, cell // w
    cx, cy = x * CELL + CELL // 2, y * CELL + CELL // 2
    d.ellipse((cx - size, cy - size, cx + size, cy + size), fill=colour)


def _walked(w, h, cost, path, si, gi):
    if not path:
        return [si]
    pmap = {c: i for i, c in enumerate(path)}
    pos = si
    walked = [si]
    n = len(cost)
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
    committed, walker_traces, reason = bug2_plan_parallel_debug(cost, w, h, si, gi)
    sx, sy = si % w, si // w
    gx, gy = gi % w, gi // w
    mline = _build_mline(w, sx, sy, gx, gy)

    panel_w = w * CELL
    panel_h = h * CELL
    img = Image.new("RGB", (panel_w, panel_h + 20), (15, 15, 15))

    plan_img = _img(w, h, cost)
    d = ImageDraw.Draw(plan_img)
    for c in mline:
        if cost[c] >= INF:
            continue
        x, y = c % w, c // w
        d.rectangle(
            (x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL), fill=(180, 230, 255)
        )

    # Draw committed path (yellow).
    for c in committed:
        _draw_cell(plan_img, w, c, (255, 220, 50), size=2)
    # Draw final hit's walker traces (orange CW, blue CCW) — last entry is
    # the failed hit point.
    if walker_traces:
        cw_partial, ccw_partial = walker_traces[-1]
        for c in cw_partial:
            _draw_cell(plan_img, w, c, (255, 100, 50), size=2)
        for c in ccw_partial:
            _draw_cell(plan_img, w, c, (50, 150, 255), size=2)

    _draw_cell(plan_img, w, si, (255, 0, 0))
    _draw_cell(plan_img, w, gi, (0, 255, 0))

    img.paste(plan_img, (0, 0))

    d = ImageDraw.Draw(img)
    sc = "with_roads" if roads else "no_roads"
    cw_n = len(walker_traces[-1][0]) if walker_traces else 0
    ccw_n = len(walker_traces[-1][1]) if walker_traces else 0
    label = (
        f"{mapname} {sc}  {si}->{gi}  reason={reason} committed={len(committed)} "
        f"last-hit cw={cw_n} ccw={ccw_n}"
    )
    d.text((4, panel_h + 4), label, fill=(200, 200, 200))
    img.save(outpath)
    print(f"wrote {outpath}")


out = Path("bench_nav_renders")
out.mkdir(exist_ok=True)

_csv = Path(__file__).resolve().parents[1] / "bench_nav_stepped.csv"
with _csv.open() as _f:
    _rows = [
        r
        for r in csv.DictReader(_f)
        if r["algo"] == "bug-bug2" and r["ref_reachable"] == "1" and r["reached"] != "1"
    ]

_seen: set[tuple[str, str]] = set()
_cases: list[tuple[str, int, int, bool]] = []
for _r in _rows:
    _k = (_r["map"], _r["scenario"])
    if _k not in _seen:
        _seen.add(_k)
        _cases.append(
            (
                _r["map"],
                int(_r["start"]),
                int(_r["goal"]),
                _r["scenario"] == "with_roads",
            )
        )
    if len(_cases) >= 6:
        break

for _mapname, _si, _gi, _roads in _cases:
    _sc = "roads" if _roads else "noroads"
    render(
        _mapname,
        _si,
        _gi,
        roads=_roads,
        outpath=out / f"bug2fail_{_mapname}_{_si}_{_gi}_{_sc}.png",
    )
