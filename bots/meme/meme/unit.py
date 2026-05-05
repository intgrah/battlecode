from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, Position


class Unit:
    my_id: int
    my_pos: Position

    def post_init(self, ct: Controller) -> None:
        self.my_id = ct.get_id()

    def run(self, ct: Controller) -> None:
        self.my_pos = ct.get_position()
