"""Core unit logic — spawn one builder bot."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, Position


def run_core(player: Player, ct: Controller) -> None:
    pos = ct.get_position()

    if player.core_pos is None:
        player.core_pos = pos

    if player.spawned < 1:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    player.spawned += 1
                    return
