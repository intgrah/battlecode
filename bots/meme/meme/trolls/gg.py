from __future__ import annotations

from typing import TYPE_CHECKING, Generator

from cambc import EntityType, Team, Environment, Position
from rust import Game, RawMem, EntityBuilderBot, EntitySentinel
from god_mode import GodMode
from map26 import Map26
import random

INF = 1_000_000_000

def write_gg(g: Game, map: Map26):

    w = g.game_map.width
    h = g.game_map.height

    cores = [Position(core.x, core.y) for core in map.cores]

    PATTERN: tuple[str, ...] = (
            "###.###",
            "#...#..",
            "#.#.#.#",
            "###.###",
        )
    pat_h = len(PATTERN)    # 4
    pat_w = len(PATTERN[0]) # 7

    corners: tuple[tuple[int, int], ...] = (
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)
    )
    best_corner: tuple[int, int] = corners[0]
    best_score = -1
    for corner_x, corner_y in corners:
        score = (
            min(
                (corner_x - pos.x) ** 2 + (corner_y - pos.y) ** 2
                for pos in cores
            )
            if cores
            else 0
        )
        if score > best_score:
            best_score = score
            best_corner = (corner_x, corner_y)

    bx, by = best_corner
    x_off = (w - pat_w) if bx != 0 else 0
    y_off = (h - pat_h) if by != 0 else 0
    for row, line in enumerate(PATTERN):
        for col, ch in enumerate(line):
            env = Environment.WALL if ch == "#" else Environment.EMPTY
            g.game_map.tile(x_off + col, y_off + row).environment = env
            g.replay_recorder.environment[y_off + row][x_off + col] = env