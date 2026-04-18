"""Generate per-junction conveyor PNG assets for the visualiser.

Emits 128 PNGs into pkg/visualiser/viewer/assets/:
    {conveyor,armoured_conveyor}_{gold,silver}_{n,e,s,w}_{x,<sorted inputs>}.png

The input suffix encodes the set of sides from which another friendly
resource-producing entity feeds this tile. "x" means no inputs detected
(dead-end: rendered as a straight pass-through). Otherwise it is the
concatenation of cardinal letters in NESW order, excluding the output side.

Run with: uv run conveyor-assets
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

from PIL import Image, ImageDraw

Dir = tuple[int, int]
Colour = tuple[int, int, int]
Rect = tuple[float, float, float, float]

TILE = 512
TILE_BG: Colour = (0x2A, 0x20, 0x18)
CARDINALS: tuple[Dir, ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))
DIR_NAMES: dict[Dir, str] = {(0, -1): "n", (1, 0): "e", (0, 1): "s", (-1, 0): "w"}

PIPE_OUTER_FRAC = 0.56
WALL_FRAC = 0.08
ARROW_BACK_FRAC = 0.28
ARROW_TIP_FRAC = 0.40
ARROW_HALF_FRAC = 0.08


def palette(team: str, *, armoured: bool) -> tuple[Colour, Colour, Colour]:
    if team == "gold":
        bg: Colour = (87, 36, 24)
        rail: Colour = (174, 129, 74)
        cap: Colour = (192, 149, 86) if armoured else (162, 113, 41)
    else:
        bg = (41, 57, 81)
        rail = (127, 136, 148)
        cap = (140, 150, 166) if armoured else (180, 187, 198)
    return bg, rail, cap


def subtract_gaps(
    full: tuple[float, float], gaps: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    segs: list[tuple[float, float]] = [full]
    for g0, g1 in gaps:
        new_segs: list[tuple[float, float]] = []
        for s0, s1 in segs:
            if g1 <= s0 or g0 >= s1:
                new_segs.append((s0, s1))
                continue
            if g0 > s0:
                new_segs.append((s0, g0))
            if g1 < s1:
                new_segs.append((g1, s1))
        segs = new_segs
    return segs


def render_tile(
    out_dir: Dir, inputs: frozenset[Dir], team: str, *, armoured: bool
) -> Image.Image:
    bg, rail, cap = palette(team, armoured=armoured)
    img = Image.new("RGBA", (TILE, TILE), TILE_BG)
    d = ImageDraw.Draw(img)
    size = float(TILE)
    half = size / 2
    cx = cy = size / 2

    pipe_outer = size * PIPE_OUTER_FRAC
    wall_thickness = size * WALL_FRAC
    pipe_outer_half = pipe_outer / 2
    pipe_inner_half = pipe_outer_half - wall_thickness

    odx, ody = out_dir
    back: Dir = (-odx, -ody)
    side_inputs = [i for i in inputs if i not in (back, out_dir)]
    back_extends = (back in inputs) or not side_inputs

    back_end = -half if back_extends else 0.0
    if ody == 0:
        x0 = cx + back_end if odx > 0 else cx - back_end
        x1 = cx + half if odx > 0 else cx - half
        lo, hi = (x0, x1) if x0 < x1 else (x1, x0)
        d.rectangle((lo, cy - pipe_inner_half, hi, cy + pipe_inner_half), fill=bg)
    else:
        y0 = cy + back_end if ody > 0 else cy - back_end
        y1 = cy + half if ody > 0 else cy - half
        lo, hi = (y0, y1) if y0 < y1 else (y1, y0)
        d.rectangle((cx - pipe_inner_half, lo, cx + pipe_inner_half, hi), fill=bg)

    for dx, dy in side_inputs:
        if ody == 0:
            if dy < 0:
                sy0, sy1 = cy - half, cy + pipe_inner_half
            else:
                sy0, sy1 = cy - pipe_inner_half, cy + half
            d.rectangle((cx - pipe_inner_half, sy0, cx + pipe_inner_half, sy1), fill=bg)
        elif dx < 0:
            sx0, sx1 = cx - half, cx + pipe_inner_half
            d.rectangle((sx0, cy - pipe_inner_half, sx1, cy + pipe_inner_half), fill=bg)
        else:
            sx0, sx1 = cx - pipe_inner_half, cx + half
            d.rectangle((sx0, cy - pipe_inner_half, sx1, cy + pipe_inner_half), fill=bg)

    if ody == 0:
        if back_extends:
            back_x = (cx - half) if (odx > 0) else (cx + half)
        else:
            back_x = (cx - pipe_outer_half) if (odx > 0) else (cx + pipe_outer_half)
        out_x = cx + odx * half
        x_lo, x_hi = (back_x, out_x) if back_x < out_x else (out_x, back_x)
        top_wall: Rect = (
            x_lo,
            cy - pipe_outer_half,
            x_hi,
            cy - pipe_outer_half + wall_thickness,
        )
        bot_wall: Rect = (
            x_lo,
            cy + pipe_outer_half - wall_thickness,
            x_hi,
            cy + pipe_outer_half,
        )
    else:
        if back_extends:
            back_y = (cy - half) if (ody > 0) else (cy + half)
        else:
            back_y = (cy - pipe_outer_half) if (ody > 0) else (cy + pipe_outer_half)
        out_y = cy + ody * half
        y_lo, y_hi = (back_y, out_y) if back_y < out_y else (out_y, back_y)
        top_wall = (
            cx - pipe_outer_half,
            y_lo,
            cx - pipe_outer_half + wall_thickness,
            y_hi,
        )
        bot_wall = (
            cx + pipe_outer_half - wall_thickness,
            y_lo,
            cx + pipe_outer_half,
            y_hi,
        )

    top_gaps: list[tuple[float, float]] = []
    bot_gaps: list[tuple[float, float]] = []
    if ody == 0:
        for _dx, dy in side_inputs:
            g = (cx - pipe_inner_half, cx + pipe_inner_half)
            (top_gaps if dy < 0 else bot_gaps).append(g)
        axis_full_top = (top_wall[0], top_wall[2])
        axis_full_bot = (bot_wall[0], bot_wall[2])
        for s0, s1 in subtract_gaps(axis_full_top, top_gaps):
            d.rectangle((s0, top_wall[1], s1, top_wall[3]), fill=rail)
        for s0, s1 in subtract_gaps(axis_full_bot, bot_gaps):
            d.rectangle((s0, bot_wall[1], s1, bot_wall[3]), fill=rail)
    else:
        for dx, _dy in side_inputs:
            g = (cy - pipe_inner_half, cy + pipe_inner_half)
            (top_gaps if dx < 0 else bot_gaps).append(g)
        axis_full_top = (top_wall[1], top_wall[3])
        axis_full_bot = (bot_wall[1], bot_wall[3])
        for s0, s1 in subtract_gaps(axis_full_top, top_gaps):
            d.rectangle((top_wall[0], s0, top_wall[2], s1), fill=rail)
        for s0, s1 in subtract_gaps(axis_full_bot, bot_gaps):
            d.rectangle((bot_wall[0], s0, bot_wall[2], s1), fill=rail)

    if not back_extends:
        if ody == 0:
            cap_x = (
                (cx - pipe_outer_half)
                if odx > 0
                else (cx + pipe_outer_half - wall_thickness)
            )
            d.rectangle(
                (
                    cap_x,
                    cy - pipe_outer_half,
                    cap_x + wall_thickness,
                    cy + pipe_outer_half,
                ),
                fill=rail,
            )
        else:
            cap_y = (
                (cy - pipe_outer_half)
                if ody > 0
                else (cy + pipe_outer_half - wall_thickness)
            )
            d.rectangle(
                (
                    cx - pipe_outer_half,
                    cap_y,
                    cx + pipe_outer_half,
                    cap_y + wall_thickness,
                ),
                fill=rail,
            )

    for dx, dy in side_inputs:
        if ody == 0:
            if dy < 0:
                sy0, sy1 = cy - half, cy - pipe_outer_half + wall_thickness
            else:
                sy0, sy1 = cy + pipe_outer_half - wall_thickness, cy + half
            d.rectangle(
                (
                    cx - pipe_outer_half,
                    sy0,
                    cx - pipe_outer_half + wall_thickness,
                    sy1,
                ),
                fill=rail,
            )
            d.rectangle(
                (
                    cx + pipe_outer_half - wall_thickness,
                    sy0,
                    cx + pipe_outer_half,
                    sy1,
                ),
                fill=rail,
            )
        else:
            if dx < 0:
                sx0, sx1 = cx - half, cx - pipe_outer_half + wall_thickness
            else:
                sx0, sx1 = cx + pipe_outer_half - wall_thickness, cx + half
            d.rectangle(
                (
                    sx0,
                    cy - pipe_outer_half,
                    sx1,
                    cy - pipe_outer_half + wall_thickness,
                ),
                fill=rail,
            )
            d.rectangle(
                (
                    sx0,
                    cy + pipe_outer_half - wall_thickness,
                    sx1,
                    cy + pipe_outer_half,
                ),
                fill=rail,
            )

    arrow_back_d = size * ARROW_BACK_FRAC
    arrow_tip_d = size * ARROW_TIP_FRAC
    arrow_half = size * ARROW_HALF_FRAC
    pdx, pdy = -ody, odx
    tip = (cx + odx * arrow_tip_d, cy + ody * arrow_tip_d)
    bc = (cx + odx * arrow_back_d, cy + ody * arrow_back_d)
    bl = (bc[0] + pdx * arrow_half, bc[1] + pdy * arrow_half)
    br = (bc[0] - pdx * arrow_half, bc[1] - pdy * arrow_half)
    d.polygon([tip, bl, br], fill=cap)

    return img


def input_suffix(inputs: frozenset[Dir]) -> str:
    if not inputs:
        return "x"
    return "".join(DIR_NAMES[d] for d in CARDINALS if d in inputs)


def enumerate_input_sets(out_dir: Dir) -> list[frozenset[Dir]]:
    others = [d for d in CARDINALS if d != out_dir]
    result: list[frozenset[Dir]] = []
    for k in range(len(others) + 1):
        result.extend(frozenset(combo) for combo in combinations(others, k))
    return result


def main() -> None:
    assets_dir = (
        Path(__file__).resolve().parents[3] / "viewer" / "assets" / "conveyors"
    )
    assets_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for team in ("gold", "silver"):
        for armoured in (False, True):
            base = "armoured_conveyor" if armoured else "conveyor"
            for out_dir in CARDINALS:
                out_s = DIR_NAMES[out_dir]
                for inputs in enumerate_input_sets(out_dir):
                    in_s = input_suffix(inputs)
                    fname = f"{base}_{team}_{out_s}_{in_s}.png"
                    img = render_tile(out_dir, inputs, team, armoured=armoured)
                    img.save(assets_dir / fname)
                    count += 1
    print(f"wrote {count} assets to {assets_dir}")


if __name__ == "__main__":
    main()
