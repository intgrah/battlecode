"""Render a .map26 file to a PNG image.

Usage: python scripts/render_map.py maps/<name>.map26 [output.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from proto.cambc_pb2 import Map

# Environment enum values
ENV_EMPTY = 0
ENV_WALL = 1
ENV_ORE_TITANIUM = 2
ENV_ORE_AXIONITE = 3

# Colors
COL_EMPTY = (45, 45, 45)
COL_WALL = (70, 50, 50)
COL_TI = (50, 90, 160)
COL_AX = (160, 100, 40)
COL_CORE_A = (70, 70, 180)
COL_CORE_B = (180, 60, 60)
COL_GRID = (30, 30, 30)

CELL = 48  # pixels per tile


def render_map(map_path: str, output_path: str | None = None) -> str:
    m = Map()
    m.ParseFromString(Path(map_path).read_bytes())
    w, h = m.width, m.height

    # Parse tiles
    tiles: list[list[int]] = [list(row.tiles) for row in m.rows]

    # Core positions
    cores: dict[int, tuple[int, int]] = {}
    for core in m.cores:
        cores[core.team] = (core.position.x, core.position.y)

    core_tiles_a: set[tuple[int, int]] = set()
    core_tiles_b: set[tuple[int, int]] = set()
    if 0 in cores:
        cx, cy = cores[0]
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                core_tiles_a.add((cx + dx, cy + dy))
    if 1 in cores:
        cx, cy = cores[1]
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                core_tiles_b.add((cx + dx, cy + dy))

    # Create image with margin for coords
    margin = 36
    img_w = w * CELL + margin
    img_h = h * CELL + margin
    img = Image.new("RGB", (img_w, img_h), (20, 20, 20))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16
        )
        font_sm = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12
        )
    except Exception:
        font = ImageFont.load_default()
        font_sm = font

    # Draw coordinate labels
    for x in range(w):
        if x % 5 == 0:
            draw.text(
                (margin + x * CELL + 4, 8), str(x), fill=(120, 120, 120), font=font_sm
            )
    for y in range(h):
        if y % 5 == 0:
            draw.text(
                (2, margin + y * CELL + 14), str(y), fill=(120, 120, 120), font=font_sm
            )

    # Draw tiles
    for y in range(h):
        for x in range(w):
            px = margin + x * CELL
            py = margin + y * CELL
            tile = tiles[y][x]

            if (x, y) in core_tiles_a:
                bg = COL_CORE_A
            elif (x, y) in core_tiles_b:
                bg = COL_CORE_B
            elif tile == ENV_WALL:
                bg = COL_WALL
            elif tile == ENV_ORE_TITANIUM:
                bg = COL_TI
            elif tile == ENV_ORE_AXIONITE:
                bg = COL_AX
            else:
                bg = COL_EMPTY

            draw.rectangle(
                [px, py, px + CELL - 1, py + CELL - 1], fill=bg, outline=COL_GRID
            )

            # Label ore tiles
            if (
                tile == ENV_ORE_TITANIUM
                and (x, y) not in core_tiles_a
                and (x, y) not in core_tiles_b
            ):
                draw.text((px + 16, py + 14), "T", fill=(150, 180, 230), font=font)
            elif (
                tile == ENV_ORE_AXIONITE
                and (x, y) not in core_tiles_a
                and (x, y) not in core_tiles_b
            ):
                draw.text((px + 16, py + 14), "A", fill=(230, 170, 90), font=font)

    # Label cores
    if 0 in cores:
        cx, cy = cores[0]
        px = margin + cx * CELL
        py = margin + cy * CELL
        draw.text((px + 6, py + 14), "C:A", fill=(200, 200, 255), font=font)
    if 1 in cores:
        cx, cy = cores[1]
        px = margin + cx * CELL
        py = margin + cy * CELL
        draw.text((px + 6, py + 14), "C:B", fill=(255, 200, 200), font=font)

    # Legend
    map_name = Path(map_path).stem.replace(".map26", "")
    title = f"{map_name}  ({w}x{h})"
    if 0 in cores:
        title += f"  A@{cores[0]}"
    if 1 in cores:
        title += f"  B@{cores[1]}"

    # Add legend bar at bottom
    legend_h = 50
    new_img = Image.new("RGB", (img_w, img_h + legend_h), (20, 20, 20))
    new_img.paste(img, (0, 0))
    draw2 = ImageDraw.Draw(new_img)
    draw2.text((8, img_h + 5), title, fill=(200, 200, 200), font=font)
    draw2.text(
        (8, img_h + 26),
        "T=Titanium  A=Axionite  Blue=CoreA  Red=CoreB  Brown=Wall",
        fill=(140, 140, 140),
        font=font_sm,
    )

    if output_path is None:
        output_path = f"/tmp/{map_name}.png"
    new_img.save(output_path)
    print(f"Saved to {output_path}")
    return output_path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/render_map.py maps/<name>.map26 [output.png]")
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else None
    render_map(sys.argv[1], out)


if __name__ == "__main__":
    main()
