"""Builder bot logic — A* pathfind to the opposite corner."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

import random

from astar import COST_IMPASSABLE, NavAstar
from cambc import Controller, Position
from utils import try_move_smart


def run_builder(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    w = ct.get_map_width()
    h = ct.get_map_height()

    if player.core_pos is None:
        player.core_pos = pos

    # Pick a new random target every 50 rounds or on first run
    if player.target is None or pos == player.target:
        player.target = Position(random.randint(0, w - 1), random.randint(0, h - 1))
    # Re-pick if target is known to be impassable
    if player.nav is not None:
        cost = player.nav.get_cost(player.target)
        if cost is not None and cost >= COST_IMPASSABLE:
            player.target = Position(random.randint(0, w - 1), random.randint(0, h - 1))

    # Create NavAstar on first run, then update cost grid each round
    if player.nav is None:
        player.nav = NavAstar(w, h)
    player.nav.set_goal(player.target)

    t0 = ct.get_cpu_time_elapsed()
    player.nav.update(ct, pos)
    t1 = ct.get_cpu_time_elapsed()
    next_pos = player.nav.step(pos, lambda: ct.get_cpu_time_elapsed() < 400)
    t2 = ct.get_cpu_time_elapsed()
    print(f"update={t1 - t0}us step={t2 - t1}us total={t2 - t0}us")

    if next_pos is None:
        return

    direction = pos.direction_to(next_pos)
    try_move_smart(ct, pos, direction)

    ct.draw_indicator_line(ct.get_position(), player.target, 255, 0, 0)
    remaining = player.nav.get_remaining_path()
    if ct.get_id() == 3:
        for i in range(len(remaining) - 1):
            ct.draw_indicator_line(remaining[i], remaining[i + 1], 0, 255, 0)
