"""Generate per-junction conveyor PNG assets for the visualiser.

Emits 128 PNGs into pkg/visualiser/viewer/assets/:
    {conveyor,armoured_conveyor}_{gold,silver}_{n,e,s,w}_{x,<sorted inputs>}.png

The input suffix encodes the set of sides from which another friendly
resource-producing entity feeds this tile. "x" means no inputs detected
(dead-end: rendered as a straight pass-through). Otherwise it is the
concatenation of cardinal letters in NESW order, excluding the output side.

Run with: uv run connected-textures
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
        rail: Colour = (255, 255, 255) if armoured else (174, 129, 74)
        arrow: Colour = (192, 149, 86) if armoured else (162, 113, 41)
    else:
        bg = (41, 57, 81)
        rail = (255, 255, 255) if armoured else (127, 136, 148)
        arrow = (140, 150, 166) if armoured else (180, 187, 198)
    return bg, rail, arrow


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
    bg, rail, arrow = palette(team, armoured=armoured)
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
    d.polygon([tip, bl, br], fill=arrow)

    return img


def input_suffix(inputs: frozenset[Dir]) -> str:
    if not inputs:
        return "x"
    return "".join(DIR_NAMES[d] for d in CARDINALS if d in inputs)


def bridge_body_colour(team: str) -> Colour:
    return (112, 64, 18) if team == "gold" else (63, 75, 85)


def render_bridge_base_tile(openings: frozenset[Dir], team: str) -> Image.Image:
    conveyor_bg, rail, _ = palette(team, armoured=False)
    body = bridge_body_colour(team)
    img = Image.new("RGBA", (TILE, TILE), TILE_BG)
    d = ImageDraw.Draw(img)

    size = float(TILE)
    half = size / 2
    cx = cy = half
    pipe_outer_half = size * PIPE_OUTER_FRAC / 2
    wall_thickness = size * WALL_FRAC
    pipe_inner_half = pipe_outer_half - wall_thickness

    # Conveyor-pipe protrusions on each opening side: inner body colour fills
    # the padding strip, with two rails flanking it so they line up 1:1 with
    # a conveyor rendered on the adjacent tile.
    for dx, dy in openings:
        if dy == 0:
            body_lo = cx + pipe_outer_half if dx > 0 else 0.0
            body_hi = size if dx > 0 else cx - pipe_outer_half
            d.rectangle(
                (body_lo, cy - pipe_inner_half, body_hi, cy + pipe_inner_half),
                fill=conveyor_bg,
            )
            top_y0, top_y1 = cy - pipe_outer_half, cy - pipe_outer_half + wall_thickness
            bot_y0, bot_y1 = cy + pipe_outer_half - wall_thickness, cy + pipe_outer_half
            seg_lo, seg_hi = (cx + pipe_outer_half, size) if dx > 0 else (0.0, cx - pipe_outer_half)
            d.rectangle((seg_lo, top_y0, seg_hi, top_y1), fill=rail)
            d.rectangle((seg_lo, bot_y0, seg_hi, bot_y1), fill=rail)
        else:
            body_lo = cy + pipe_outer_half if dy > 0 else 0.0
            body_hi = size if dy > 0 else cy - pipe_outer_half
            d.rectangle(
                (cx - pipe_inner_half, body_lo, cx + pipe_inner_half, body_hi),
                fill=conveyor_bg,
            )
            lft_x0, lft_x1 = cx - pipe_outer_half, cx - pipe_outer_half + wall_thickness
            rgt_x0, rgt_x1 = cx + pipe_outer_half - wall_thickness, cx + pipe_outer_half
            seg_lo, seg_hi = (cy + pipe_outer_half, size) if dy > 0 else (0.0, cy - pipe_outer_half)
            d.rectangle((lft_x0, seg_lo, lft_x1, seg_hi), fill=rail)
            d.rectangle((rgt_x0, seg_lo, rgt_x1, seg_hi), fill=rail)

    # Body square.
    d.rectangle(
        (cx - pipe_outer_half, cy - pipe_outer_half, cx + pipe_outer_half, cy + pipe_outer_half),
        fill=body,
    )

    # Border rail on every side that is NOT open.
    for dir_ in CARDINALS:
        if dir_ in openings:
            continue
        dx, dy = dir_
        if dy < 0:
            d.rectangle(
                (cx - pipe_outer_half, cy - pipe_outer_half,
                 cx + pipe_outer_half, cy - pipe_outer_half + wall_thickness),
                fill=rail,
            )
        elif dy > 0:
            d.rectangle(
                (cx - pipe_outer_half, cy + pipe_outer_half - wall_thickness,
                 cx + pipe_outer_half, cy + pipe_outer_half),
                fill=rail,
            )
        elif dx < 0:
            d.rectangle(
                (cx - pipe_outer_half, cy - pipe_outer_half,
                 cx - pipe_outer_half + wall_thickness, cy + pipe_outer_half),
                fill=rail,
            )
        else:
            d.rectangle(
                (cx + pipe_outer_half - wall_thickness, cy - pipe_outer_half,
                 cx + pipe_outer_half, cy + pipe_outer_half),
                fill=rail,
            )

    return img


def bridge_base_suffix(openings: frozenset[Dir]) -> str:
    if not openings:
        return "x"
    return "".join(DIR_NAMES[d] for d in CARDINALS if d in openings)


def enumerate_openings() -> list[frozenset[Dir]]:
    result: list[frozenset[Dir]] = []
    for k in range(len(CARDINALS) + 1):
        result.extend(frozenset(c) for c in combinations(CARDINALS, k))
    return result


def render_bridge_beam(team: str) -> Image.Image:
    """A 3:1 strip beam. Central x-strip is rails (opaque) + body (~50% alpha)
    with three chevrons (opaque) along the length. Outside the central strip
    is fully transparent so the beam reads as a clean ribbon when drawn."""
    width = TILE * 3
    height = TILE
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    conveyor_bg, rail, arrow = palette(team, armoured=False)
    body_rgb = bridge_body_colour(team)
    body = (*body_rgb, 128)
    rail_opaque = (*rail, 255)
    arrow_opaque = (*arrow, 255)
    _ = conveyor_bg

    half_h = height / 2
    pipe_outer_half = height * PIPE_OUTER_FRAC / 2
    wall_thickness = height * WALL_FRAC
    pipe_inner_half = pipe_outer_half - wall_thickness

    # Inner body strip (semi-transparent).
    d.rectangle(
        (0, half_h - pipe_inner_half, width, half_h + pipe_inner_half),
        fill=body,
    )

    # Rails along the long edges (opaque).
    d.rectangle(
        (0, half_h - pipe_outer_half, width, half_h - pipe_inner_half),
        fill=rail_opaque,
    )
    d.rectangle(
        (0, half_h + pipe_inner_half, width, half_h + pipe_outer_half),
        fill=rail_opaque,
    )

    # Three arrows evenly spaced along the length. Same geometry as the
    # conveyor arrow (ARROW_BACK_FRAC/ARROW_TIP_FRAC/ARROW_HALF_FRAC), with
    # each arrow centred between back and tip at one-third increments.
    arrow_back_d = height * ARROW_BACK_FRAC
    arrow_tip_d = height * ARROW_TIP_FRAC
    arrow_half = height * ARROW_HALF_FRAC
    arrow_centre_offset = (arrow_tip_d - arrow_back_d) / 2 + arrow_back_d
    for i in range(3):
        centre_x = (i + 0.5) * (width / 3)
        cy = half_h
        tip = (centre_x - arrow_centre_offset + arrow_tip_d, cy)
        bc = (centre_x - arrow_centre_offset + arrow_back_d, cy)
        bl = (bc[0], bc[1] + arrow_half)
        br_ = (bc[0], bc[1] - arrow_half)
        d.polygon([tip, bl, br_], fill=arrow_opaque)

    return img


def enumerate_input_sets(out_dir: Dir) -> list[frozenset[Dir]]:
    others = [d for d in CARDINALS if d != out_dir]
    result: list[frozenset[Dir]] = []
    for k in range(len(others) + 1):
        result.extend(frozenset(combo) for combo in combinations(others, k))
    return result


def main() -> None:
    base_dir = Path(__file__).resolve().parents[3] / "viewer" / "assets" / "custom"
    conveyor_dir = base_dir / "conveyor"
    armoured_dir = base_dir / "armoured_conveyor"
    bridge_dir = base_dir / "bridge"
    for d in (conveyor_dir, armoured_dir, bridge_dir):
        d.mkdir(parents=True, exist_ok=True)

    count = 0
    for team in ("gold", "silver"):
        for armoured in (False, True):
            base = "armoured_conveyor" if armoured else "conveyor"
            out_subdir = armoured_dir if armoured else conveyor_dir
            for out_dir in CARDINALS:
                out_s = DIR_NAMES[out_dir]
                for inputs in enumerate_input_sets(out_dir):
                    in_s = input_suffix(inputs)
                    fname = f"{base}_{team}_{out_s}_{in_s}.png"
                    img = render_tile(out_dir, inputs, team, armoured=armoured)
                    img.save(out_subdir / fname)
                    count += 1
        for openings in enumerate_openings():
            suffix = bridge_base_suffix(openings)
            fname = f"bridge_base_{team}_{suffix}.png"
            img = render_bridge_base_tile(openings, team)
            img.save(bridge_dir / fname)
            count += 1
        beam = render_bridge_beam(team)
        beam.save(bridge_dir / f"bridge_beam_{team}.png")
        count += 1
    print(f"wrote {count} assets to {base_dir}")


if __name__ == "__main__":
    main()
