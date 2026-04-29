"""Step-by-step sheet for circumnav on a failing case."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "pkg" / "bench_nav" / "src")
)

from bench_nav.common import INF, MAPS_DIR
from bench_nav.precomputation import build_cost, load_map
from bench_nav.stepped.bug._planner import _IS_CARDINAL, DX, DY, dir_to
from PIL import Image, ImageDraw

MAPNAME = "battlebot"
SI = 12
GI = 490

mf = MAPS_DIR / f"{MAPNAME}.map26"
m = load_map(mf)
tiles = [t for row in m.rows for t in row.tiles]
n = m.width * m.height
cost = build_cost(tiles, n)
w, h = m.width, m.height
gx, gy = GI % w, GI // w

# Walk to the hit point manually.
pos = SI
while True:
    px, py = pos % w, pos // w
    d = dir_to(px, py, gx, gy)
    nx, ny = px + DX[d], py + DY[d]
    if 0 <= nx < w and 0 <= ny < h and cost[ny * w + nx] < INF:
        pos = ny * w + nx
        continue
    break

hit_pos = pos
blocked_dir = d
hx, hy = hit_pos % w, hit_pos // w
print(f"hit at ({hx},{hy}) blocked_dir={blocked_dir}")

# Crop to area around hit point.
cx0 = max(0, hx - 12)
cy0 = max(0, hy - 12)
cx1 = min(w, hx + 13)
cy1 = min(h, hy + 13)

CELL = 24
PW = (cx1 - cx0) * CELL
PH = (cy1 - cy0) * CELL
LABEL = 16


def cell_centre(x: int, y: int) -> tuple[int, int]:
    return (x - cx0) * CELL + CELL // 2, (y - cy0) * CELL + CELL // 2


def in_crop(x: int, y: int) -> bool:
    return cx0 <= x < cx1 and cy0 <= y < cy1


def base_img() -> Image.Image:
    img = Image.new("RGB", (PW, PH), (20, 20, 20))
    d_ = ImageDraw.Draw(img)
    for y in range(cy0, cy1):
        for x in range(cx0, cx1):
            c = y * w + x
            lx = (x - cx0) * CELL
            ly = (y - cy0) * CELL
            fill = (70, 70, 70) if cost[c] >= INF else (180, 180, 180)
            d_.rectangle((lx, ly, lx + CELL - 1, ly + CELL - 1), fill=fill)
    if in_crop(gx, gy):
        cx, cy = cell_centre(gx, gy)
        d_.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(0, 220, 0))
    if in_crop(hx, hy):
        cx, cy = cell_centre(hx, hy)
        d_.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(255, 50, 50))
    return img


def draw_face(
    d_: ImageDraw.ImageDraw, wx: int, wy: int, face: int, colour: tuple, width: int = 3
) -> None:
    if not in_crop(wx, wy):
        return
    lx = (wx - cx0) * CELL
    ly = (wy - cy0) * CELL
    rx = lx + CELL
    by = ly + CELL
    m2 = 4
    if face == 0:
        d_.line((rx - 1, ly + m2, rx - 1, by - m2), fill=colour, width=width)
    elif face == 1:
        d_.line((lx + 1, ly + m2, lx + 1, by - m2), fill=colour, width=width)
    elif face == 2:
        d_.line((lx + m2, ly + 1, rx - m2, ly + 1), fill=colour, width=width)
    elif face == 3:
        d_.line((lx + m2, by - 1, rx - m2, by - 1), fill=colour, width=width)


def step_sim(
    px: int,
    py: int,
    wox: int,
    woy: int,
    cw: int,
    own_f: set,
    other_f: set,
    wall_dir: int,
) -> tuple[int, int, int, int, int, bool, bool, bool, list, str]:
    """Mirror of circumnav inner loop. Returns
    (px, py, wox, woy, wall_dir, moved, met, loop, painted, note)."""
    delta = -1 if cw == 1 else 1
    painted: list = []
    for _ in range(8):
        wall_dir = (wall_dir + delta) % 8
        ndx = DX[wall_dir]
        ndy = DY[wall_dir]
        nx = px + ndx
        ny = py + ndy
        if not (0 <= nx < w and 0 <= ny < h):
            return px, py, wox, woy, wall_dir, False, False, False, painted, "off-map"
        if cost[ny * w + nx] < INF:
            wdx = wox - nx
            wdy = woy - ny
            met = False
            loop = False
            if wdx == 0 or wdy == 0:
                face = 0 if wdx == -1 else 1 if wdx == 1 else 2 if wdy == 1 else 3
                key = (wox, woy, face)
                painted.append(key)
                if key in other_f:
                    met = True
                elif key in own_f:
                    loop = True
                own_f.add(key)
            return nx, ny, wox, woy, wall_dir, True, met, loop, painted, "moved"
        wox, woy = nx, ny
        if _IS_CARDINAL[wall_dir]:
            pdx = px - nx
            pdy = py - ny
            face = 0 if pdx == 1 else 1 if pdx == -1 else 2 if pdy == -1 else 3
            key = (nx, ny, face)
            painted.append(key)
            met_p = key in other_f
            loop_p = key in own_f and not met_p
            own_f.add(key)
            if met_p:
                return (
                    px,
                    py,
                    wox,
                    woy,
                    wall_dir,
                    False,
                    True,
                    False,
                    painted,
                    "met-no-move",
                )
            if loop_p:
                return (
                    px,
                    py,
                    wox,
                    woy,
                    wall_dir,
                    False,
                    False,
                    True,
                    painted,
                    "loop-no-move",
                )
    return px, py, wox, woy, wall_dir, False, False, False, painted, "no-move"


cw_f: set = set()
ccw_f: set = set()
cw_px, cw_py = hx, hy
cw_wox, cw_woy = hx + DX[blocked_dir], hy + DY[blocked_dir]
cw_wall_dir = blocked_dir
ccw_px, ccw_py = hx, hy
ccw_wox, ccw_woy = hx + DX[blocked_dir], hy + DY[blocked_dir]
ccw_wall_dir = blocked_dir

cw_steps: list = []
ccw_steps: list = []
cw_done = False
ccw_done = False

for _ in range(80):
    if not cw_done:
        cw_px, cw_py, cw_wox, cw_woy, cw_wall_dir, moved, met, loop, painted, note = (
            step_sim(cw_px, cw_py, cw_wox, cw_woy, 1, cw_f, ccw_f, cw_wall_dir)
        )
        cw_steps.append(
            {
                "pos": (cw_px, cw_py),
                "wo": (cw_wox, cw_woy),
                "painted": list(painted),
                "note": note,
                "moved": moved,
                "met": met,
                "loop": loop,
            }
        )
        if not moved or met or loop:
            cw_done = True
            if met:
                ccw_done = True
    if not ccw_done:
        (
            ccw_px,
            ccw_py,
            ccw_wox,
            ccw_woy,
            ccw_wall_dir,
            moved,
            met,
            loop,
            painted,
            note,
        ) = step_sim(ccw_px, ccw_py, ccw_wox, ccw_woy, -1, ccw_f, cw_f, ccw_wall_dir)
        ccw_steps.append(
            {
                "pos": (ccw_px, ccw_py),
                "wo": (ccw_wox, ccw_woy),
                "painted": list(painted),
                "note": note,
                "moved": moved,
                "met": met,
                "loop": loop,
            }
        )
        if not moved or met or loop:
            ccw_done = True
            if met:
                cw_done = True
    if cw_done and ccw_done:
        break

nframes = max(len(cw_steps), len(ccw_steps)) + 1
print(f"cw steps: {len(cw_steps)}, ccw steps: {len(ccw_steps)}")

cw_f_hist: list = []
ccw_f_hist: list = []
cw_acc: set = set()
ccw_acc: set = set()
for frame in range(nframes):
    if frame > 0:
        fi = frame - 1
        if fi < len(cw_steps):
            for key in cw_steps[fi]["painted"]:
                cw_acc.add(key)
        if fi < len(ccw_steps):
            for key in ccw_steps[fi]["painted"]:
                ccw_acc.add(key)
    cw_f_hist.append(set(cw_acc))
    ccw_f_hist.append(set(ccw_acc))

CW = (255, 160, 40)
CCW = (60, 200, 255)
COLS = 5
ROWS = (nframes + COLS - 1) // COLS
GAP = 3
PANEL_W = PW * 2 + GAP
PANEL_H = PH + LABEL
sheet = Image.new("RGB", (COLS * (PANEL_W + GAP), ROWS * (PANEL_H + GAP)), (5, 5, 5))

for frame in range(nframes):
    col_i = frame % COLS
    row_i = frame // COLS
    ox = col_i * (PANEL_W + GAP)
    oy = row_i * (PANEL_H + GAP)
    panel = Image.new("RGB", (PANEL_W, PANEL_H), (10, 10, 10))
    for pi, (walker_steps, own_f, other_f, col, ocol) in enumerate(
        [
            (cw_steps, cw_f_hist[frame], ccw_f_hist[frame], CW, CCW),
            (ccw_steps, ccw_f_hist[frame], cw_f_hist[frame], CCW, CW),
        ]
    ):
        sub = base_img()
        d_ = ImageDraw.Draw(sub)
        for wx, wy, face in other_f:
            draw_face(
                d_, wx, wy, face, (ocol[0] // 6, ocol[1] // 6, ocol[2] // 6), width=1
            )
        for wx, wy, face in own_f:
            draw_face(d_, wx, wy, face, col, width=3)
        path = [(hx, hy)] + [s["pos"] for s in walker_steps[:frame] if s["moved"]]
        for i in range(len(path) - 1):
            ax, ay = path[i]
            bx, by = path[i + 1]
            if in_crop(ax, ay) and in_crop(bx, by):
                d_.line((cell_centre(ax, ay), cell_centre(bx, by)), fill=col, width=2)
        if frame > 0 and frame - 1 < len(walker_steps):
            wx, wy = walker_steps[frame - 1]["pos"]
            if in_crop(wx, wy):
                cx, cy = cell_centre(wx, wy)
                d_.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=col)
            wox_, woy_ = walker_steps[frame - 1]["wo"]
            if in_crop(wox_, woy_):
                cx, cy = cell_centre(wox_, woy_)
                d_.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), outline=col, width=2)
        panel.paste(sub, (pi * (PW + GAP), 0))
    label = f"f={frame}"
    if frame > 0:
        fi = frame - 1
        if fi < len(cw_steps):
            label += f"  CW:{cw_steps[fi]['note']}"
            if cw_steps[fi]["met"]:
                label += "(MET)"
            if cw_steps[fi]["loop"]:
                label += "(LOOP)"
        if fi < len(ccw_steps):
            label += f"  CCW:{ccw_steps[fi]['note']}"
            if ccw_steps[fi]["met"]:
                label += "(MET)"
            if ccw_steps[fi]["loop"]:
                label += "(LOOP)"
    ImageDraw.Draw(panel).text((2, PH + 2), label, fill=(180, 180, 180))
    sheet.paste(panel, (ox, oy))

out = Path("bench_nav_renders") / f"circumnav_{MAPNAME}_{SI}_{GI}.png"
out.parent.mkdir(exist_ok=True)
sheet.save(out)
print(f"wrote {out}")
