"""Parse opening book DSL.

format per step (semicolon-separated):
  "<build_dir> <building> [args], <move_dir>"
  build_dir: direction to build relative to current pos (n/ne/e/se/s/sw/w/nw)
  building: rd/h/c/sp/g/sn/l/a/f/br + optional facing dir or target coords
  move_dir: direction to move (n/ne/e/se/s/sw/w/nw) or x for stay

examples:
  "sw rd, sw"         -> build road to sw, move sw
  "nw h, x"           -> build harvester to nw, stay put
  "w br 6 12, x"      -> build bridge to w targeting (6,12), stay
  "sw sp e, sw"        -> build splitter to sw facing east, move sw
"""

from __future__ import annotations

from builder.build import (
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceGunner,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
    PlaceSplitter,
)
from cambc import Direction, Position

from . import Build, Move, Step, Wait

_DIR: dict[str, Direction] = {
    "n": Direction.NORTH,
    "ne": Direction.NORTHEAST,
    "e": Direction.EAST,
    "se": Direction.SOUTHEAST,
    "s": Direction.SOUTH,
    "sw": Direction.SOUTHWEST,
    "w": Direction.WEST,
    "nw": Direction.NORTHWEST,
}

_DELTA: dict[str, tuple[int, int]] = {
    "n": (0, -1),
    "ne": (1, -1),
    "e": (1, 0),
    "se": (1, 1),
    "s": (0, 1),
    "sw": (-1, 1),
    "w": (-1, 0),
    "nw": (-1, -1),
}


def _make_building(
    kind: str,
    pos: Position,
    tokens: list[str],
) -> Build | None:
    match kind:
        case "rd":
            return Build(PlaceRoad(pos))
        case "h":
            return Build(PlaceHarvester(pos))
        case "c":
            d = _DIR.get(tokens[0]) if tokens else None
            return Build(PlaceConveyor(pos, d)) if d else None
        case "sp":
            d = _DIR.get(tokens[0]) if tokens else None
            return Build(PlaceSplitter(pos, d)) if d else None
        case "gn":
            d = _DIR.get(tokens[0]) if tokens else None
            return Build(PlaceGunner(pos, d)) if d else None
        case "sn":
            d = _DIR.get(tokens[0]) if tokens else None
            return Build(PlaceSentinel(pos, d)) if d else None
        case "ln":
            return Build(PlaceLauncher(pos))
        case "ba":
            return Build(PlaceBarrier(pos))
        case "f":
            return Build(PlaceFoundry(pos))
        case "br":
            if len(tokens) < 2:
                return None
            return Build(PlaceBridge(pos, Position(int(tokens[0]), int(tokens[1]))))
    return None


def parse_script(spawn_x: int, spawn_y: int, script: str) -> list[Step]:
    steps: list[Step] = []
    cx, cy = spawn_x, spawn_y

    for raw_step in script.replace("\n", ";").split(";"):
        step_str = raw_step.strip()
        if not step_str:
            continue

        parts = [p.strip() for p in step_str.split(",")]
        build_part = parts[0] if len(parts) >= 2 else None
        move_part = (
            parts[1].strip().lower() if len(parts) >= 2 else parts[0].strip().lower()
        )

        if len(parts) == 1:
            if move_part == "x":
                steps.append(Wait())
                continue
            d = _DIR.get(move_part)
            if d is not None:
                steps.append(Move(d))
                dx, dy = _DELTA[move_part]
                cx += dx
                cy += dy
                continue

        build_action: Build | None = None
        if build_part is not None:
            tokens = build_part.strip().lower().split()
            build_dir_str = tokens[0]
            dx, dy = _DELTA.get(build_dir_str, (0, 0))
            bx, by = cx + dx, cy + dy
            kind = tokens[1] if len(tokens) >= 2 else ""
            rest = tokens[2:]
            build_action = _make_building(kind, Position(bx, by), rest)

        move_dir: Direction | None = None
        if move_part != "x":
            move_dir = _DIR.get(move_part)

        if build_action is not None:
            steps.append(build_action)
        if move_dir is not None:
            steps.append(Move(move_dir))
            dx, dy = _DELTA[move_part]
            cx += dx
            cy += dy
        elif build_action is None:
            steps.append(Wait())
        steps.append(Wait())

    return steps
