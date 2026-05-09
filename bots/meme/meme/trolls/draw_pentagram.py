from __future__ import annotations

import math
from typing import TYPE_CHECKING, Generator
from cambc import Position
from god_mode import GodMode

if TYPE_CHECKING:
    from main import Player


def draw_pentagram(p: Player, center: Position, radius: float, angle: float = 0.0) -> Generator:
    offset = math.radians(angle)
    vertices = [
        Position(
            round(center.x + radius * math.sin(2 * math.pi * i / 5 + offset)),
            round(center.y + radius * math.cos(2 * math.pi * i / 5 + offset)),
        )
        for i in range(5)
    ]
    for i in range(5):
        GodMode.draw_line(p, vertices[i], vertices[(i + 2) % 5])
        yield
