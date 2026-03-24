"""Visualize ground-truth flow on the map from a replay file.

Usage: python scripts/flow_visualize.py <replay_file> [output_png]

Colors:
  Green  = flow 0-2 quarter-stacks (healthy)
  Yellow = flow 3-4 quarter-stacks (near capacity)
  Red    = flow 5+ quarter-stacks (congested)
  Blue/purple = core tiles
  Dark green = harvester (H)
  Blue ore = Ti, Brown ore = Ax
  Light brown = roads

Blue curved lines = bridges, yellow arrows = conveyor directions.
Numbers = flow in quarter-stacks (4 = 1.0 = capacity).
"""

from __future__ import annotations

import math
import sys
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proto.cambc_pb2 import Replay

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("pip install Pillow", file=sys.stderr)
    sys.exit(1)

DIR_DELTA = {
    0: (0, 0),
    1: (0, -1),
    2: (1, -1),
    3: (1, 0),
    4: (1, 1),
    5: (0, 1),
    6: (-1, 1),
    7: (-1, 0),
    8: (-1, -1),
}
CARD = [(-1, 0), (1, 0), (0, -1), (0, 1)]
TRANSPORT_TYPES = {"conveyor", "armoured_conveyor", "splitter", "bridge"}


def parse_replay(path: str) -> Replay:
    r = Replay()
    r.ParseFromString(Path(path).read_bytes())
    return r


Pos = tuple[int, int]
Ent = dict[str, Any]
PosSet = set[Pos]
PosEntMap = dict[Pos, Ent]
FlowMap = dict[Pos, float]


def extract_state(
    r: Replay,
) -> tuple[
    int,
    int,
    int,
    int,
    PosSet,
    PosSet,
    PosSet,
    PosSet,
    PosEntMap,
    PosEntMap,
    PosEntMap,
    PosSet,
]:
    w, h = r.map.width, r.map.height
    cx, cy = r.map.cores[0].position.x, r.map.cores[0].position.y

    walls = set()
    ore_ti = set()
    ore_ax = set()
    for y_idx, row in enumerate(r.map.rows):
        for x_idx, tile_env in enumerate(row.tiles):
            if tile_env == 1:
                walls.add((x_idx, y_idx))
            elif tile_env == 2:
                ore_ti.add((x_idx, y_idx))
            elif tile_env == 3:
                ore_ax.add((x_idx, y_idx))

    entities = {}
    for turn in r.turns:
        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = e.WhichOneof("kind")
                ent: Ent = {
                    "team": e.team,
                    "type": ek,
                    "x": e.position.x,
                    "y": e.position.y,
                }
                if ek in ("conveyor", "armoured_conveyor", "splitter"):
                    ent["dir"] = DIR_DELTA.get(getattr(e, ek).direction, (0, 0))
                elif ek == "bridge":
                    ent["target"] = (e.bridge.target.x, e.bridge.target.y)
                entities[e.id] = ent
            elif k == "remove_entity":
                entities.pop(u.remove_entity.id, None)

    core_tiles = set()
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            core_tiles.add((cx + dx, cy + dy))

    pos_map = {}
    for e in entities.values():
        if e["team"] != 0:
            continue
        pos_map[(e["x"], e["y"])] = e

    transports = {p: e for p, e in pos_map.items() if e["type"] in TRANSPORT_TYPES}
    harvesters = {p: e for p, e in pos_map.items() if e["type"] == "harvester"}
    foundries = {p: e for p, e in pos_map.items() if e["type"] == "foundry"}
    roads_set = {p for p, e in pos_map.items() if e["type"] == "road"}

    return (
        w,
        h,
        cx,
        cy,
        core_tiles,
        walls,
        ore_ti,
        ore_ax,
        transports,
        harvesters,
        foundries,
        roads_set,
    )


def compute_flow(
    core_tiles: PosSet,
    transports: PosEntMap,
    harvesters: PosEntMap,
    ore_ti: PosSet,
    ore_ax: PosSet,
    foundries: PosEntMap,
) -> tuple[FlowMap, FlowMap, FlowMap, FlowMap]:
    output_of = {}
    splitter_outs = {}
    for pos, t in transports.items():
        if t["type"] == "bridge":
            output_of[pos] = [t.get("target")] if t.get("target") else []
        elif t["type"] == "splitter" and t.get("dir"):
            dx, dy = t["dir"]
            outs = []
            for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                nb = (pos[0] + odx, pos[1] + ody)
                outs.append(nb)
            splitter_outs[pos] = outs
            output_of[pos] = outs
        elif t.get("dir"):
            dx, dy = t["dir"]
            output_of[pos] = [(pos[0] + dx, pos[1] + dy)]

    all_nodes = set(transports.keys()) | core_tiles | set(foundries.keys())
    in_deg = dict.fromkeys(all_nodes, 0)
    for pos in transports:
        for out in output_of.get(pos, []):
            if out in all_nodes:
                in_deg[out] += 1
    for fpos in foundries:
        for dx, dy in CARD:
            nb = (fpos[0] + dx, fpos[1] + dy)
            if nb in all_nodes and nb not in foundries:
                in_deg[nb] += 1
    for hpos in harvesters:
        for dx, dy in CARD:
            nb = (hpos[0] + dx, hpos[1] + dy)
            if nb in all_nodes:
                in_deg[nb] += 1

    z = dict.fromkeys(all_nodes, 0.0)
    ti_flow = dict(z)
    ax_flow = dict(z)
    rax_flow = dict(z)
    flow_at = dict(z)

    queue: deque = deque()
    for hpos in harvesters:
        outs = [
            (hpos[0] + dx, hpos[1] + dy)
            for dx, dy in CARD
            if (hpos[0] + dx, hpos[1] + dy) in all_nodes
        ]
        n = max(len(outs), 1)
        push = 0.25 / n
        is_ti = hpos in ore_ti
        is_ax = hpos in ore_ax
        for nb in outs:
            if is_ti:
                ti_flow[nb] += push
            elif is_ax:
                ax_flow[nb] += push
            flow_at[nb] += push
            in_deg[nb] -= 1
            if in_deg[nb] == 0:
                queue.append(nb)
    for pos, d in in_deg.items():
        if d == 0 and pos not in core_tiles and (pos in transports or pos in foundries):
            queue.append(pos)

    processed: set = set()
    while queue:
        pos = queue.popleft()
        if pos in processed:
            continue
        processed.add(pos)
        if pos in core_tiles:
            continue

        if pos in foundries:
            ti_in = ti_flow[pos]
            ax_in = ax_flow[pos]
            refined = min(ti_in, ax_in)
            rax_in = rax_flow[pos]
            rax_out = rax_in + refined
            for dx, dy in CARD:
                nb = (pos[0] + dx, pos[1] + dy)
                if nb in all_nodes and nb not in foundries:
                    rax_flow[nb] += rax_out
                    flow_at[nb] += rax_out
                    in_deg[nb] -= 1
                    if in_deg[nb] == 0:
                        queue.append(nb)
            continue

        if pos not in transports:
            continue
        t = transports[pos]
        ti_in = ti_flow[pos]
        ax_in = ax_flow[pos]
        rax_in = rax_flow[pos]
        divisor = 3 if t["type"] == "splitter" else 1
        ti_push = ti_in / divisor
        ax_push = ax_in / divisor
        rax_push = rax_in / divisor
        total_push = ti_push + ax_push + rax_push
        for out in output_of.get(pos, []):
            if out in all_nodes:
                ti_flow[out] += ti_push
                ax_flow[out] += ax_push
                rax_flow[out] += rax_push
                flow_at[out] += total_push
                in_deg[out] -= 1
                if in_deg[out] == 0:
                    queue.append(out)

    return flow_at, ti_flow, ax_flow, rax_flow


def render(
    w: int,
    h: int,
    _cx: int,
    _cy: int,
    core_tiles: PosSet,
    walls: PosSet,
    ore_ti: PosSet,
    ore_ax: PosSet,
    transports: PosEntMap,
    harvesters: PosEntMap,
    foundries: PosEntMap,
    roads_set: PosSet,
    flow_qs: FlowMap,
    ti_flow: FlowMap,
    ax_flow: FlowMap,
    rax_flow: FlowMap,
    output_path: str,
) -> None:
    cell = 72
    img = Image.new("RGB", (w * cell, h * cell), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    for path in [
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]:
        try:
            font = ImageFont.truetype(path, 16)
            sfont = ImageFont.truetype(path, 12)
            break
        except OSError:
            pass
    else:
        font = sfont = ImageFont.load_default()

    for y in range(h):
        for x in range(w):
            px, py = x * cell, y * cell
            pos = (x, y)
            if pos in walls:
                bg = (50, 35, 35)
            elif pos in core_tiles:
                f = flow_qs.get(pos, 0.0)
                bg = (
                    (180, 50, 50)
                    if f > 1.0
                    else (70, 70, 160)
                    if f > 0
                    else (50, 50, 100)
                )
            elif pos in foundries:
                bg = (140, 80, 30)
            elif pos in harvesters:
                bg = (55, 65, 55)
            elif pos in transports:
                f = flow_qs.get(pos, 0.0)
                g = min(220, int(50 + f * 130))
                bg = (g, g, g)
            elif pos in ore_ti:
                bg = (35, 70, 120)
            elif pos in ore_ax:
                bg = (120, 70, 35)
            elif pos in roads_set:
                bg = (65, 60, 42)
            else:
                bg = (35, 35, 35)

            draw.rectangle(
                [px, py, px + cell - 1, py + cell - 1],
                fill=bg,
                outline=(20, 20, 20),
            )
            tc = (255, 255, 255) if max(bg) < 160 else (0, 0, 0)
            if pos in core_tiles:
                f = flow_qs.get(pos, 0.0)
                if f > 0.001:
                    draw.text((px + 2, py + 1), f"{f:.2f}", fill=tc, font=font)
                draw.text(
                    (px + 2, py + cell - 15),
                    "Core",
                    fill=(180, 180, 180),
                    font=sfont,
                )
            elif pos in foundries:
                ti_f = ti_flow.get(pos, 0.0)
                ax_f = ax_flow.get(pos, 0.0)
                rax_f = rax_flow.get(pos, 0.0)
                draw.text((px + 2, py + 1), "Foundry", fill=tc, font=font)
                draw.text(
                    (px + 2, py + 14),
                    f"T{ti_f:.1f}",
                    fill=(100, 180, 255),
                    font=sfont,
                )
                draw.text(
                    (px + 2, py + 24),
                    f"A{ax_f:.1f}",
                    fill=(255, 160, 80),
                    font=sfont,
                )
                draw.text(
                    (px + 2, py + 34),
                    f"R{rax_f:.1f}",
                    fill=(200, 100, 255),
                    font=sfont,
                )
            elif pos in harvesters:
                draw.text((px + 2, py + 1), "Harvest", fill=tc, font=font)
                dot_x = px + cell - 12
                dot_y = py + 10
                dot_r = 6
                if pos in ore_ti:
                    draw.ellipse(
                        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                        fill=(80, 150, 255),
                    )
                elif pos in ore_ax:
                    draw.ellipse(
                        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                        fill=(255, 160, 50),
                    )
            elif pos in transports:
                f = flow_qs.get(pos, 0.0)
                ti_f = ti_flow.get(pos, 0.0)
                ax_f = ax_flow.get(pos, 0.0)
                rax_f = rax_flow.get(pos, 0.0)
                t = transports[pos]
                label = {
                    "conveyor": "Conv",
                    "armoured_conveyor": "AConv",
                    "splitter": "Split",
                    "bridge": "Bridge",
                }.get(t["type"], "?")
                draw.text((px + 2, py + 1), label, fill=(180, 180, 180), font=sfont)
                draw.text((px + 2, py + 14), f"{f:.2f}", fill=tc, font=font)
                dot_x = px + cell - 12
                dot_y = py + 10
                dot_r = 6
                if ti_f > 0.001:
                    draw.ellipse(
                        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                        fill=(80, 150, 255),
                    )
                    dot_y += 16
                if ax_f > 0.001:
                    draw.ellipse(
                        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                        fill=(255, 160, 50),
                    )
                    dot_y += 16
                if rax_f > 0.001:
                    draw.ellipse(
                        [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                        fill=(200, 80, 255),
                    )
                y_off = 34
                if ti_f > 0.001:
                    draw.text(
                        (px + 2, py + y_off),
                        f"Ti{ti_f:.1f}",
                        fill=(100, 180, 255),
                        font=sfont,
                    )
                    y_off += 13
                if ax_f > 0.001:
                    draw.text(
                        (px + 2, py + y_off),
                        f"Ax{ax_f:.1f}",
                        fill=(255, 160, 80),
                        font=sfont,
                    )
                    y_off += 13
                if rax_f > 0.001:
                    draw.text(
                        (px + 2, py + y_off),
                        f"RA{rax_f:.1f}",
                        fill=(200, 100, 255),
                        font=sfont,
                    )
            elif pos in ore_ti:
                draw.text((px + 2, py + 1), "Ti Ore", fill=tc, font=font)
            elif pos in ore_ax:
                draw.text((px + 2, py + 1), "Ax Ore", fill=tc, font=font)

    def _draw_arrow(
        sx: int,
        sy: int,
        ex: int,
        ey: int,
        color: tuple[int, int, int],
        width: int = 3,
    ) -> None:
        draw.line([(sx, sy), (ex, ey)], fill=color, width=width)
        angle = math.atan2(ey - sy, ex - sx)
        a1, a2 = angle + 2.5, angle - 2.5
        alen = 7
        draw.polygon(
            [
                (ex, ey),
                (int(ex - alen * math.cos(a1)), int(ey - alen * math.sin(a1))),
                (int(ex - alen * math.cos(a2)), int(ey - alen * math.sin(a2))),
            ],
            fill=color,
        )

    for pos, t in transports.items():
        if t["type"] in ("conveyor", "armoured_conveyor", "splitter") and t.get("dir"):
            dx, dy = t["dir"]
            if dx == 0 and dy == 0:
                continue
            sx = pos[0] * cell + cell // 2
            sy = pos[1] * cell + cell // 2
            ex = sx + dx * (cell // 3)
            ey = sy + dy * (cell // 3)
            _draw_arrow(sx, sy, ex, ey, (255, 255, 0), width=2)

    bridge_pairs: dict = {}
    for pos, t in transports.items():
        if t["type"] == "bridge" and t.get("target"):
            tgt = t["target"]
            pair_key = (min(pos, tgt), max(pos, tgt))
            bridge_pairs.setdefault(pair_key, []).append((pos, tgt))

    for bridges in bridge_pairs.values():
        for idx, (src, tgt) in enumerate(bridges):
            sx = src[0] * cell + cell // 2
            sy = src[1] * cell + cell // 2
            ex = tgt[0] * cell + cell // 2
            ey = tgt[1] * cell + cell // 2
            dx, dy = ex - sx, ey - sy
            length = max(1, math.sqrt(dx * dx + dy * dy))
            nx, ny = -dy / length, dx / length
            offset = (idx - (len(bridges) - 1) / 2) * 4
            mx = (sx + ex) / 2 + nx * (15 + offset * 3)
            my = (sy + ey) / 2 + ny * (15 + offset * 3)
            color = (100, 200, 255)
            draw.line([(sx, sy), (int(mx), int(my)), (ex, ey)], fill=color, width=3)
            angle = math.atan2(ey - my, ex - mx)
            a1, a2 = angle + 2.5, angle - 2.5
            alen = 8
            draw.polygon(
                [
                    (ex, ey),
                    (int(ex - alen * math.cos(a1)), int(ey - alen * math.sin(a1))),
                    (int(ex - alen * math.cos(a2)), int(ey - alen * math.sin(a2))),
                ],
                fill=color,
            )

    img.save(output_path)
    print(f"Saved {output_path} ({w * cell}x{h * cell})")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <replay_file> [output_png]")
        sys.exit(1)
    replay_path = sys.argv[1]
    default_out = str(Path(tempfile.gettempdir()) / "flow_map.png")
    output_path = sys.argv[2] if len(sys.argv) > 2 else default_out

    r = parse_replay(replay_path)
    (
        w,
        h,
        ccx,
        ccy,
        core_tiles,
        walls,
        ore_ti,
        ore_ax,
        transports,
        harvesters,
        foundries,
        roads_set,
    ) = extract_state(r)
    flow_qs, ti_flow, ax_flow, rax_flow = compute_flow(
        core_tiles,
        transports,
        harvesters,
        ore_ti,
        ore_ax,
        foundries,
    )

    over_1 = sum(1 for f in flow_qs.values() if f > 1.0)
    over_half = sum(1 for f in flow_qs.values() if f > 0.5)
    total_core = sum(flow_qs.get(ct, 0.0) for ct in core_tiles)
    ti_core = sum(ti_flow.get(ct, 0.0) for ct in core_tiles)
    ax_core = sum(ax_flow.get(ct, 0.0) for ct in core_tiles)
    rax_core = sum(rax_flow.get(ct, 0.0) for ct in core_tiles)
    n_conv = sum(1 for t in transports.values() if t["type"] == "conveyor")
    n_aconv = sum(1 for t in transports.values() if t["type"] == "armoured_conveyor")
    n_bridge = sum(1 for t in transports.values() if t["type"] == "bridge")
    n_splitter = sum(1 for t in transports.values() if t["type"] == "splitter")
    n_mixed = sum(
        1
        for p in transports
        if (ti_flow.get(p, 0) > 0.001)
        + (ax_flow.get(p, 0) > 0.001)
        + (rax_flow.get(p, 0) > 0.001)
        > 1
    )
    print(f"Harvesters: {len(harvesters)}, Foundries: {len(foundries)}")
    print(
        f"Conv: {n_conv}, Armoured: {n_aconv}, Bridge: {n_bridge}, Splitter: {n_splitter}",
    )
    if n_mixed > 0:
        print(f"MIXED FLOW TILES: {n_mixed} (BUG)")
    print(f"Congested (>1.0): {over_1}, Near capacity (>0.5): {over_half}")
    print(
        f"Total flow to core: {total_core:.2f}/turn (Ti={ti_core:.2f} Ax={ax_core:.2f} rAx={rax_core:.2f})",
    )

    render(
        w,
        h,
        ccx,
        ccy,
        core_tiles,
        walls,
        ore_ti,
        ore_ax,
        transports,
        harvesters,
        foundries,
        roads_set,
        flow_qs,
        ti_flow,
        ax_flow,
        rax_flow,
        output_path,
    )


if __name__ == "__main__":
    main()
