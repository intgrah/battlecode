from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Position
from god_mode import GodMode

if TYPE_CHECKING:
    from collections.abc import Generator

    from main import Player


def snipe(p: Player) -> Generator:
    assert p.core is not None

    target_id = 0
    target_pos: Position | None = None
    for uid in reversed(p.g.unit_order):
        if uid != p.core:
            target_id = uid
            target_pos = p.g.entities[uid].base.position
            break

    if target_pos is None or target_id <= 2:
        return

    GodMode.draw_line(
        p, Position(-1, target_pos.y), Position(p.map.width, target_pos.y)
    )
    yield
    GodMode.draw_line(
        p, Position(target_pos.x, -1), Position(target_pos.x, p.map.height)
    )
    yield
    GodMode.attack(p, target_pos)
    yield
