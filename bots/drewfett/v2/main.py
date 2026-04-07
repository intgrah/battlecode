import traceback
from typing import TYPE_CHECKING

from builder import Builder
from cambc import Controller, EntityType
from core import Core
from gunner import Gunner
from launcher import Launcher
from navigation.grid import PassableGrid
from navigation.nav_bfs import NavBfs
from sentinel import Sentinel

if TYPE_CHECKING:
    from unit import Unit


class Player:
    def __init__(self) -> None:
        self.unit: Unit | None = None
        # Pre-init State for max 50x50 in 5s budget. Builder will patch for actual size.
        from builder.state import State

        self._pre_state = State.prealloc_max()

        # Grid created on first run() when we know map size
        self._grid_init = False

    def run(self, ct: Controller) -> None:
        if not self._grid_init:
            self._grid_init = True
            w, h = ct.get_map_width(), ct.get_map_height()
            grid = PassableGrid(w, h)
            grid.init_pnb_chunk(lambda: True)
            nav = NavBfs(grid)
            grid.navs.append(nav)
            self._pre_state.grid = grid
            self._pre_state.nav_bfs = nav
        if self.unit is None:
            match ct.get_entity_type():
                case EntityType.CORE:
                    self.unit = Core(ct)
                case EntityType.BUILDER_BOT:
                    if ct.get_cpu_time_elapsed() > 1400:
                        # Too late in the turn to run builder init safely
                        self._pre_state.pos = ct.get_position()
                        return
                    self.unit = Builder(ct, self._pre_state)
                case EntityType.SENTINEL:
                    self.unit = Sentinel(ct)
                case EntityType.GUNNER:
                    self.unit = Gunner(ct)
                case EntityType.LAUNCHER:
                    self.unit = Launcher(ct)
                case _:
                    return
        try:
            self.unit.run(ct)
        except Exception:  # noqa: BLE001
            print(traceback.format_exc())
