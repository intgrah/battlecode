from __future__ import annotations

from typing import TYPE_CHECKING

from util import Timer

from builder.role import Role

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def update(self: Builder, ct: Controller) -> None:
    with Timer("update"):
        with Timer("prune"):
            self.prune_stale(ct)
        with Timer("vision"):
            self.update_vision(ct)
        with Timer("bfs"):
            self.update_bfs(self.my_pos.x, self.my_pos.y)
        with Timer("ore_deny"):
            self.update_ore_denial()
        with Timer("turrets"):
            self.update_enemy_turrets()
        with Timer("role"):
            self.update_role(ct)
        if self.role != Role.OFFENSE:
            with Timer("econ"):
                self.update_map_econ(ct)
            with Timer("dangling"):
                self.update_dangling()
            with Timer("ore"):
                self.update_ore_target()
