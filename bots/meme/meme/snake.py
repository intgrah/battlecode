from __future__ import annotations

from typing import TYPE_CHECKING, Generator

from cambc import EntityType, Position, Team, Direction, ResourceType
from rust import Game, RawMem, EntityBuilderBot, EntitySentinel
from god_mode import GodMode

INF = 1_000_000_000

if TYPE_CHECKING:
    from main import Player
    from cambc import Controller

class Snake:

    def __init__(self, n) -> None:
        self.n = n
        self.head: tuple[int, Position] | None = None
        self.tail: list[tuple[int, Position] | None] = [None] * (n - 1)

    def step_towards(self, p: Player, target: Position, dist: bytearray) -> None:
        pass