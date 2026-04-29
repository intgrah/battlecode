"""Render per-algorithm worst-case planning paths from bench_nav_stepped.csv.

For each algorithm, finds the row with the largest peak per-step time, replays
the planner on that map, and renders a PNG with:
  - left: perimeter walks (Bug1 only)
  - middle: raw planned path (before prune)
  - right: pruned path (the actual walked path)
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "pkg" / "bench_nav" / "src")
)

from bench_nav.common import INF, MAPS_DIR
from bench_nav.precomputation import build_cost, build_nb, load_map, place_roads
from bench_nav.stepped.bug._planner import (
    bug1_plan_debug,
    bug2_plan,
    distbug_plan,
)
from bench_nav.stepped.bug.bfsbug import _bfs_plan
from bench_nav.stepped.bug.bug0 import _bug0_plan
from bench_nav.stepped.bug.lookahead_bug import _lookahead_plan
from bench_nav.stepped.bug.mem_astar import _astar_plan
from bench_nav.stepped.bug.tangentbug import _shortcut

OUT_DIR = Path("bench_nav_viz")
CELL = 12
GAP = 16
PAD = 24
HEADER_H = 36
LEGEND_H = 28


@dataclass(frozen=True)
class Row:
    algo: str
    scenario: str
    map: str
    start: int
    goal: int
    peak_us: float
    reached: bool


def load_rows(csv_path: Path) -> list[Row]:
    out: list[Row] = []
    with csv_path.open(newline="") as f:
        for r in csv.DictReader(f):
            out.append(
                Row(
                    algo=r["algo"],
                    scenario=r["scenario"],
                    map=r["map"],
                    start=int(r["start"]),
                    goal=int(r["goal"]),
                    peak_us=float(r.get("peak_step_us", "0") or "0"),
                    reached=r["reached"] == "1",
                )
            )
    return out


def worst_per_algo(rows: list[Row]) -> dict[str, Row]:
    best: dict[str, Row] = {}
    for r in rows:
        if not r.reached:
            continue
        cur = best.get(r.algo)
        if cur is None or r.peak_us > cur.peak_us:
            best[r.algo] = r
    return best


def load_scenario_cost(map_name: str, scenario: str) -> tuple[list[int], int, int]:
    mf = MAPS_DIR / f"{map_name}.map26"
    m = load_map(mf)
    tiles: list[int] = [int(t) for row in m.rows for t in row.tiles]
    n = m.width * m.height
    cost = build_cost(tiles, n)
    if scenario == "with_roads":
        nb = build_nb(m.width, m.height)
        passable = [i for i in range(n) if cost[i] < INF]
        place_roads(tiles, cost, nb, passable)
    return cost, m.width, m.height


def plan_for(
    algo: str, cost: list[int], w: int, h: int, si: int, gi: int
) -> tuple[list[int] | None, list[list[int]]]:
    """Return (raw_path, perimeters). perimeters non-empty for bug1 family."""
    match algo:
        case "bug-bug0":
            return _bug0_plan(cost, w, h, si, gi), []
        case "bug-bug1" | "bug-fast-bug" | "bug-step-bug":
            return bug1_plan_debug(cost, w, h, si, gi)
        case "bug-bug2":
            return bug2_plan(cost, w, h, si, gi), []
        case "bug-distbug":
            return distbug_plan(cost, w, h, si, gi), []
        case "bug-tangentbug" | "bug-visbug21":
            raw = bug2_plan(cost, w, h, si, gi)
            if raw is None:
                return None, []
            return _shortcut(cost, w, h, raw), []
        case "bug-visbug22":
            raw = distbug_plan(cost, w, h, si, gi)
            if raw is None:
                return None, []
            return _shortcut(cost, w, h, raw), []
        case "bug-bfsbug" | "bug-mem-bfs":
            return _bfs_plan(cost, w, h, si, gi), []
        case "bug-mem-astar":
            return _astar_plan(cost, w, h, si, gi), []
        case "bug-lookahead":
            return _lookahead_plan(cost, w, h, si, gi), []
        case _:
            return None, []


def base_grid_image(cost: list[int], w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w * CELL, h * CELL), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if cost[i] >= INF:
                draw.rectangle(
                    (x * CELL, y * CELL, (x + 1) * CELL - 1, (y + 1) * CELL - 1),
                    fill=(40, 40, 40),
                )
    return img


def overlay_path(
    img: Image.Image, path: list[int], w: int, color: tuple[int, int, int]
) -> None:
    if not path or len(path) < 2:
        return
    draw = ImageDraw.Draw(img)
    pts = [((c % w) * CELL + CELL // 2, (c // w) * CELL + CELL // 2) for c in path]
    draw.line(pts, fill=color, width=2)


def overlay_cells(
    img: Image.Image,
    cells: list[int],
    w: int,
    color: tuple[int, int, int, int],
) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for c in cells:
        x = (c % w) * CELL
        y = (c // w) * CELL
        d.rectangle((x, y, x + CELL - 1, y + CELL - 1), fill=color)
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def mark_endpoints(img: Image.Image, w: int, si: int, gi: int) -> None:
    draw = ImageDraw.Draw(img)
    for c, color in ((si, (0, 180, 0)), (gi, (200, 0, 0))):
        x = (c % w) * CELL
        y = (c // w) * CELL
        draw.ellipse(
            (x + 2, y + 2, x + CELL - 3, y + CELL - 3),
            fill=color,
            outline=(0, 0, 0),
        )


def panel(
    cost: list[int],
    w: int,
    h: int,
    si: int,
    gi: int,
    cells_overlay: list[int],
    path: list[int],
    overlay_color: tuple[int, int, int, int],
    path_color: tuple[int, int, int],
    title: str,
) -> Image.Image:
    img = base_grid_image(cost, w, h)
    if cells_overlay:
        overlay_cells(img, cells_overlay, w, overlay_color)
    overlay_path(img, path, w, path_color)
    mark_endpoints(img, w, si, gi)
    # Title strip.
    strip = Image.new("RGB", (img.width, HEADER_H), (255, 255, 255))
    sd = ImageDraw.Draw(strip)
    try:
        font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    sd.text((6, 8), title, fill=(0, 0, 0), font=font)
    out = Image.new("RGB", (img.width, img.height + HEADER_H), (255, 255, 255))
    out.paste(strip, (0, 0))
    out.paste(img, (0, HEADER_H))
    return out


def render(row: Row) -> Path | None:
    cost, w, h = load_scenario_cost(row.map, row.scenario)
    raw, perims = plan_for(row.algo, cost, w, h, row.start, row.goal)
    if raw is None:
        print(f"  {row.algo}: planner returned None", file=sys.stderr)
        return None
    perim_cells: list[int] = []
    seen: set[int] = set()
    for p in perims:
        for c in p:
            if c not in seen:
                seen.add(c)
                perim_cells.append(c)

    p1 = panel(
        cost,
        w,
        h,
        row.start,
        row.goal,
        perim_cells,
        [],
        (255, 200, 0, 130),
        (0, 0, 0),
        f"{row.algo}  perimeters ({sum(len(p) for p in perims)} cells, {len(perims)} walks)",
    )
    p2 = panel(
        cost,
        w,
        h,
        row.start,
        row.goal,
        [],
        raw,
        (0, 0, 0, 0),
        (30, 80, 220),
        f"raw plan  len={len(raw)}",
    )

    panel_w = p1.width
    total_w = panel_w * 3 + GAP * 2 + PAD * 2
    total_h = p1.height + LEGEND_H + PAD * 2
    big = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    bd = ImageDraw.Draw(big)
    try:
        font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    bd.text(
        (PAD, 6),
        f"{row.algo}  {row.map}/{row.scenario}  start={row.start} goal={row.goal}  peak={row.peak_us:.0f}us",
        fill=(0, 0, 0),
        font=font,
    )
    big.paste(p1, (PAD, LEGEND_H + PAD - 8))
    big.paste(p2, (PAD + panel_w + GAP, LEGEND_H + PAD - 8))

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{row.algo}.png"
    big.save(out_path)
    return out_path


def main() -> None:
    csv_path = Path("bench_nav_stepped.csv")
    if not csv_path.exists():
        print(
            f"missing {csv_path}; run `uv run python -m bench_nav stepped -n N` first",
            file=sys.stderr,
        )
        sys.exit(1)
    rows = load_rows(csv_path)
    worst = worst_per_algo(rows)
    for algo in sorted(worst):
        r = worst[algo]
        print(
            f"{algo:30s} peak={r.peak_us:>8.0f}us  {r.map}/{r.scenario}  {r.start}->{r.goal}"
        )
        out = render(r)
        if out is not None:
            print(f"  -> {out}")


if __name__ == "__main__":
    main()
