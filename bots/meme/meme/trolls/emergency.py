from __future__ import annotations

from typing import TYPE_CHECKING, Generator

from cambc import EntityType, Team, Environment
from rust import Game, RawMem, EntityBuilderBot, EntitySentinel
from god_mode import GodMode
import random

INF = 1_000_000_000

if TYPE_CHECKING:
    from cambc import Position

def win_without_ct(g: Game):

    my_id = g.who_am_i()
    my_team = g.entities[my_id].base.team

    team_state = g.player(my_team)
    team_state.axionite_collected = -1

    enemy_state = g.player(Team.A if my_team == Team.B else Team.B)
    enemy_state.axionite_collected = -2

    for i in range(len(g.unit_order)):
        g.unit_order[i] = my_id

    return
    w = g.game_map.width
    h = g.game_map.height

    cores: list[Position] = []
    enemy_core: Position | None = None
    for i in g.entities:
        entity = g.entities[i]
        if entity.base.id == my_id:
            entity.base.hp = INF
        if entity.entity_type == EntityType.CORE:
            if entity.base.team != team:
                enemy_core = entity.base.position
            cores.append(entity.base.position)

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
            g.replay_recorder.environment.set(x_off + col, y_off + row, env)

    if enemy_core is None:
        return

    for x in range(enemy_core.x - 3, enemy_core.x + 3):
        for y in range(enemy_core.y - 3, enemy_core.y + 3):
            if x < 0 or x >= w or y < 0 or y >= w:
                continue
            if max(abs(x - enemy_core.x), abs(y - enemy_core.y)) <= 1:
                continue
            g.game_map.tile(x, y).environment = Environment.WALL
            g.replay_recorder.environment.set(x, y, Environment.WALL)