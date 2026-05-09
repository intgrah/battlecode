"""Render a build schedule onto its map, sprites tinted by build turn.

Usage: python scripts/render_schedule.py <schedule.txt> <blueprint.bp> <map.map26> [output.png]
"""

from __future__ import annotations

import colorsys
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from scripts.replay import load_map

CELL = 48
MARGIN = 36

CARDINALS: list[tuple[int, int]] = [(0, -1), (1, 0), (0, 1), (-1, 0)]
DIR_TO_UNIT: dict[str, tuple[int, int]] = {
    "NORTH": (0, -1),
    "EAST": (1, 0),
    "SOUTH": (0, 1),
    "WEST": (-1, 0),
}
DIR_SUFFIX: dict[tuple[int, int], str] = {
    (0, -1): "n",
    (1, 0): "e",
    (0, 1): "s",
    (-1, 0): "w",
}


@dataclass(frozen=True)
class Pos:
    x: int
    y: int


@dataclass
class Placement:
    pos: Pos
    kind: str
    direction: str | None = None
    bridge_target: Pos | None = None
    build_turn: int | None = None


def parse_bp(path: Path) -> list[Placement]:
    out: list[Placement] = []
    for raw in path.read_text().splitlines():
        s = raw.split("#", 1)[0].strip()
        if not s or s.startswith("map:"):
            continue
        toks = s.split()
        x, y = int(toks[0]), int(toks[1])
        kind = toks[2]
        direction: str | None = None
        bridge_target: Pos | None = None
        for t in toks[3:]:
            if t.startswith("dir="):
                direction = t[4:]
            elif t.startswith("bridge="):
                a, b = t[len("bridge=") :].split(",")
                bridge_target = Pos(int(a), int(b))
        out.append(Placement(Pos(x, y), kind, direction, bridge_target))
    return out


SCHEDULE_RE = re.compile(
    r"^T\s*(\d+)\s+([SB])\s+(\w+)\s+pos=\(\s*(\d+)\s*,\s*(\d+)\s*\)"
)


def parse_schedule(path: Path) -> dict[Pos, int]:
    out: dict[Pos, int] = {}
    for raw in path.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = SCHEDULE_RE.match(s)
        if not m or m.group(2) != "B":
            continue
        out[Pos(int(m.group(4)), int(m.group(5)))] = int(m.group(1))
    return out


def conveyor_feeds_into(neighbour: Placement, target: Pos) -> bool:
    k = neighbour.kind
    if k in ("CONVEYOR", "ARMOURED_CONVEYOR"):
        d = DIR_TO_UNIT.get(neighbour.direction or "")
        if d is None:
            return False
        return Pos(neighbour.pos.x + d[0], neighbour.pos.y + d[1]) == target
    if k == "SPLITTER":
        d = DIR_TO_UNIT.get(neighbour.direction or "")
        if d is None:
            return False
        back = (-d[0], -d[1])
        delta = (target.x - neighbour.pos.x, target.y - neighbour.pos.y)
        return delta in CARDINALS and delta != back
    if k == "BRIDGE":
        return neighbour.bridge_target == target
    return k in ("HARVESTER", "FOUNDRY")


def conveyor_sprite_name(
    p: Placement,
    by_pos: dict[Pos, list[Placement]],
    team: str = "gold",
) -> str | None:
    base = {"CONVEYOR": "conveyor", "ARMOURED_CONVEYOR": "armoured_conveyor"}.get(
        p.kind
    )
    if base is None:
        return None
    out = DIR_TO_UNIT.get(p.direction or "")
    if out is None:
        return None
    inputs: list[tuple[int, int]] = []
    for d in CARDINALS:
        if d == out:
            continue
        n = Pos(p.pos.x + d[0], p.pos.y + d[1])
        if any(conveyor_feeds_into(nb, p.pos) for nb in by_pos.get(n, [])):
            inputs.append(d)
    inputs.sort(key=CARDINALS.index)
    in_s = "x" if not inputs else "".join(DIR_SUFFIX[d] for d in inputs)
    return f"{base}_{team}_{DIR_SUFFIX[out]}_{in_s}"


def bridge_sprite_name(
    p: Placement,
    by_pos: dict[Pos, list[Placement]],
    team: str = "gold",
) -> str:
    openings: list[tuple[int, int]] = []
    for d in CARDINALS:
        n = Pos(p.pos.x + d[0], p.pos.y + d[1])
        if any(conveyor_feeds_into(nb, p.pos) for nb in by_pos.get(n, [])):
            openings.append(d)
    openings.sort(key=CARDINALS.index)
    suffix = "x" if not openings else "".join(DIR_SUFFIX[d] for d in openings)
    return f"bridge_base_{team}_{suffix}"


def sprite_name(p: Placement, by_pos: dict[Pos, list[Placement]]) -> str | None:
    k = p.kind
    if k in ("CONVEYOR", "ARMOURED_CONVEYOR"):
        return conveyor_sprite_name(p, by_pos)
    if k == "BRIDGE":
        return bridge_sprite_name(p, by_pos)
    if k == "SPLITTER":
        d = DIR_TO_UNIT.get(p.direction or "")
        return f"splitter_{DIR_SUFFIX[d]}_gold" if d else None
    if k == "HARVESTER":
        return "harvester_gold"
    if k == "FOUNDRY":
        return "foundry_gold"
    if k == "ROAD":
        return "road_gold"
    if k == "BARRIER":
        return "barrier_gold"
    return None


def turn_colour(t: int, t_max: int) -> tuple[int, int, int]:
    if t_max <= 0:
        return (0, 255, 0)
    f = max(0.0, min(1.0, t / t_max))
    h = (120 + 180 * f) / 360.0
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


@dataclass
class SpriteLoader:
    asset_dirs: list[Path]
    cache: dict[str, Image.Image | None] = field(default_factory=dict)

    def get(self, name: str) -> Image.Image | None:
        if name in self.cache:
            return self.cache[name]
        for d in self.asset_dirs:
            p = d / f"{name}.png"
            if p.exists():
                im = (
                    Image.open(p)
                    .convert("RGBA")
                    .resize((CELL, CELL), Image.Resampling.LANCZOS)
                )
                self.cache[name] = im
                return im
        self.cache[name] = None
        return None


def render(schedule_path: Path, bp_path: Path, map_path: Path, out_path: Path) -> None:
    placements = parse_bp(bp_path)
    build_turns = parse_schedule(schedule_path)
    for p in placements:
        p.build_turn = build_turns.get(p.pos)

    by_pos: dict[Pos, list[Placement]] = {}
    for p in placements:
        by_pos.setdefault(p.pos, []).append(p)

    m = load_map(map_path)
    w, h = m.width, m.height
    t_max = max(
        (p.build_turn for p in placements if p.build_turn is not None), default=0
    )

    repo_root = Path(__file__).resolve().parent.parent
    asset_root = repo_root / "crates" / "titan" / "assets"
    loader = SpriteLoader(
        [
            asset_root / "custom" / "conveyor",
            asset_root / "custom" / "armoured_conveyor",
            asset_root / "custom" / "bridge",
            asset_root / "custom" / "road",
            asset_root / "cambc",
        ]
    )

    img_w = w * CELL + MARGIN
    img_h = h * CELL + MARGIN
    img = Image.new("RGBA", (img_w, img_h), (20, 20, 20, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_sm = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12
        )
    except OSError:
        font_sm = ImageFont.load_default()

    for x in range(w):
        if x % 5 == 0:
            draw.text(
                (MARGIN + x * CELL + 4, 8),
                str(x),
                fill=(120, 120, 120),
                font=font_sm,
            )
    for y in range(h):
        if y % 5 == 0:
            draw.text(
                (2, MARGIN + y * CELL + 14),
                str(y),
                fill=(120, 120, 120),
                font=font_sm,
            )

    tiles = [list(row.tiles) for row in m.rows]
    for y in range(h):
        for x in range(w):
            px = MARGIN + x * CELL
            py = MARGIN + y * CELL
            t = tiles[y][x]
            colour = (45, 45, 45)
            if t == 1:
                colour = (70, 50, 50)
            elif t == 2:
                colour = (50, 90, 160)
            elif t == 3:
                colour = (160, 100, 40)
            draw.rectangle([px, py, px + CELL - 1, py + CELL - 1], fill=colour)

    for core in m.cores:
        cx, cy = core.position.x, core.position.y
        nm = "base_gold" if core.team == 0 else "base_silver"
        sp = loader.get(nm)
        px0 = MARGIN + (cx - 1) * CELL
        py0 = MARGIN + (cy - 1) * CELL
        if sp is not None:
            big = sp.resize((CELL * 3, CELL * 3), Image.Resampling.LANCZOS)
            img.alpha_composite(big, (px0, py0))
        else:
            col = (70, 70, 180) if core.team == 0 else (180, 60, 60)
            draw.rectangle([px0, py0, px0 + CELL * 3 - 1, py0 + CELL * 3 - 1], fill=col)

    rank = {
        "ROAD": 0,
        "BARRIER": 1,
        "CONVEYOR": 2,
        "ARMOURED_CONVEYOR": 2,
        "SPLITTER": 2,
        "BRIDGE": 3,
        "HARVESTER": 4,
        "FOUNDRY": 5,
    }
    placements_sorted = sorted(placements, key=lambda p: rank.get(p.kind, 0))

    for p in placements_sorted:
        nm = sprite_name(p, by_pos)
        if nm is None:
            continue
        sp = loader.get(nm)
        if sp is None:
            continue
        px = MARGIN + p.pos.x * CELL
        py = MARGIN + p.pos.y * CELL
        img.alpha_composite(sp, (px, py))
        if p.build_turn is not None:
            colour = turn_colour(p.build_turn, t_max)
            mask = sp.split()[3]
            tinted = Image.new("RGBA", (CELL, CELL), (*colour, 128))
            img.alpha_composite(
                Image.composite(
                    tinted, Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0)), mask
                ),
                (px, py),
            )

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for p in placements:
        if p.kind != "BRIDGE" or p.bridge_target is None:
            continue
        sx = MARGIN + p.pos.x * CELL + CELL // 2
        sy = MARGIN + p.pos.y * CELL + CELL // 2
        tx = MARGIN + p.bridge_target.x * CELL + CELL // 2
        ty = MARGIN + p.bridge_target.y * CELL + CELL // 2
        line_colour = (
            turn_colour(p.build_turn, t_max)
            if p.build_turn is not None
            else (255, 255, 255)
        )
        odraw.line([(sx, sy), (tx, ty)], fill=(*line_colour, 220), width=3)
        r = 5
        odraw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(*line_colour, 255))
        odraw.ellipse(
            [tx - r, ty - r, tx + r, ty + r],
            outline=(*line_colour, 255),
            width=2,
        )
    img = Image.alpha_composite(img, overlay)

    img.convert("RGB").save(out_path)


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(
            "Usage: python scripts/render_schedule.py <schedule.txt> <blueprint.bp> <map.map26> [output.png]",
            file=sys.stderr,
        )
        return 2
    schedule = Path(argv[1])
    bp = Path(argv[2])
    map_path = Path(argv[3])
    out = Path(argv[4]) if len(argv) > 4 else schedule.with_suffix(".rendered.png")
    render(schedule, bp, map_path, out)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
