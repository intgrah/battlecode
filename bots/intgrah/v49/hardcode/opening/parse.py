"""Parse string DSL scripts into DslTurn lists."""

from __future__ import annotations

from cambc import Direction

from .dsl import (
    DslActionMove,
    DslPlaceBarrier,
    DslPlaceBridge,
    DslPlaceConveyor,
    DslPlaceFoundry,
    DslPlaceGunner,
    DslPlaceHarvester,
    DslPlaceLauncher,
    DslPlaceRoad,
    DslPlaceSentinel,
    DslPlaceSplitter,
    DslTurn,
)

_DIR_MAP: dict[str, Direction] = {
    "n": Direction.NORTH,
    "ne": Direction.NORTHEAST,
    "e": Direction.EAST,
    "se": Direction.SOUTHEAST,
    "s": Direction.SOUTH,
    "sw": Direction.SOUTHWEST,
    "w": Direction.WEST,
    "nw": Direction.NORTHWEST,
}

_DELTA: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (0, -1),
    Direction.NORTHEAST: (1, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTHEAST: (1, 1),
    Direction.SOUTH: (0, 1),
    Direction.SOUTHWEST: (-1, 1),
    Direction.WEST: (-1, 0),
    Direction.NORTHWEST: (-1, -1),
}


def _parse_dir(s: str) -> Direction | None:
    if s == "x":
        return None
    d = _DIR_MAP.get(s)
    if d is None:
        raise ValueError(f"Unknown direction: {s!r}")
    return d


def parse_script(start_x: int, start_y: int, script: str) -> list[DslTurn]:
    """Parse a string DSL script into a list of DslTurn objects.

    Format per step: ``<build_dir> <building> [args], <move_dir>``
    Steps separated by ``;`` or newlines.
    """
    steps_raw: list[str] = []
    for line in script.split("\n"):
        line = line.split("--")[0].split("#")[0].strip()
        if not line:
            continue
        for part in line.split(";"):
            part = part.strip()
            if part:
                steps_raw.append(part)

    result: list[DslTurn] = []
    x, y = start_x, start_y

    for step in steps_raw:
        if "," not in step:
            raise ValueError(f"Missing comma in step: {step!r}")
        build_str, move_str = step.split(",", 1)
        build_tokens = build_str.strip().split()
        move_dir = _parse_dir(move_str.strip())

        action = None
        if build_tokens and build_tokens[0] != "x":
            build_dir_str = build_tokens[0]
            build_dir = _parse_dir(build_dir_str)
            if build_dir is None:
                raise ValueError(f"Invalid build direction: {build_dir_str!r}")

            if len(build_tokens) < 2:
                raise ValueError(f"Missing building type in step: {step!r}")
            building = build_tokens[1]

            match building:
                case "rd":
                    action = DslPlaceRoad(build_dir)
                case "h":
                    action = DslPlaceHarvester(build_dir)
                case "ba":
                    action = DslPlaceBarrier(build_dir)
                case "c":
                    facing = _parse_dir(build_tokens[2])
                    if facing is None:
                        raise ValueError(
                            f"Conveyor needs facing direction: {step!r}"
                        )
                    action = DslPlaceConveyor(build_dir, facing)
                case "sp":
                    facing = _parse_dir(build_tokens[2])
                    if facing is None:
                        raise ValueError(
                            f"Splitter needs facing direction: {step!r}"
                        )
                    action = DslPlaceSplitter(build_dir, facing)
                case "sn":
                    facing = _parse_dir(build_tokens[2])
                    if facing is None:
                        raise ValueError(
                            f"Sentinel needs facing direction: {step!r}"
                        )
                    action = DslPlaceSentinel(build_dir, facing)
                case "gn":
                    facing = _parse_dir(build_tokens[2])
                    if facing is None:
                        raise ValueError(
                            f"Gunner needs facing direction: {step!r}"
                        )
                    action = DslPlaceGunner(build_dir, facing)
                case "ln":
                    action = DslPlaceLauncher(build_dir)
                case "f":
                    action = DslPlaceFoundry(build_dir)
                case "br":
                    target_x = int(build_tokens[2])
                    target_y = int(build_tokens[3])
                    dx, dy = _DELTA[build_dir]
                    bx, by = x + dx, y + dy
                    tv = (target_x - bx, target_y - by)
                    action = DslPlaceBridge(build_dir, tv)
                case _:
                    raise ValueError(f"Unknown building: {building!r}")

        result.append(DslActionMove(action, move_dir))

        if move_dir is not None:
            dx, dy = _DELTA[move_dir]
            x += dx
            y += dy

    return result
