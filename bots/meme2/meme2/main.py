from __future__ import annotations

from typing import TYPE_CHECKING

from trolls import Troll, select_troll

if TYPE_CHECKING:
    from cambc import Controller


class Player:
    def __init__(self) -> None:
        self.troll: Troll | None = None

    def run(self, ct: Controller) -> None:
        if self.troll is None:
            self.troll = select_troll(ct)
        self.troll.run(ct)
