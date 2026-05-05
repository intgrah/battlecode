from __future__ import annotations

import astar
from cambc import Controller, Environment, Position, Team
from game import Game
from map26 import Core, Map26
from raw_mem import RawMem
from rust_types import Entity


class Player:
    def __init__(self) -> None:
        self._done = False
        self._log = ""
        self._cores: list[Core] = []
        self._ti_ore: tuple[int, int] | None = None
        self._ax_ore: tuple[int, int] | None = None
        self._ti_path: list[tuple[int, int]] = []
        try:
            m = Map26.read()
            self._cores = m.cores
            if m.cores:
                ref_x, ref_y = m.cores[0].x, m.cores[0].y
                best_ti = best_ax = -1
                for y in range(m.height):
                    for x in range(m.width):
                        env = m.tile(x, y)
                        match env:
                            case Environment.ORE_TITANIUM:
                                d = (x - ref_x) ** 2 + (y - ref_y) ** 2
                                if best_ti < 0 or d < best_ti:
                                    best_ti = d
                                    self._ti_ore = (x, y)
                            case Environment.ORE_AXIONITE:
                                d = (x - ref_x) ** 2 + (y - ref_y) ** 2
                                if best_ax < 0 or d < best_ax:
                                    best_ax = d
                                    self._ax_ore = (x, y)
                if self._ti_ore is not None:
                    self._ti_path = astar.run(
                        m, start=self._ti_ore, goal=(ref_x, ref_y)
                    )
        except Exception as e:
            self._log = f"[map] {e}"

    def run(self, ct: Controller) -> None:
        if self._done:
            if self._log:
                print(self._log)
                self._log = ""
            return

        for i in range(len(self._ti_path) - 1):
            ax, ay = self._ti_path[i]
            bx, by = self._ti_path[i + 1]
            ct.draw_indicator_line(Position(ax, ay), Position(bx, by), 255, 200, 0)

        try:
            g = Game.open(RawMem(), ct)
        except Exception as e:
            print(f"[exploit] {type(e).__name__}: {e}")
            self._done = True
            return

        self._done = True

        gm = g.game_map
        print(f"game_map: {gm.width}x{gm.height}")
        print(f"turn={g.turn} next_id={g.next_id} resign_message={g.resign_message!r}")
        print(f"unit_order: {list(g.unit_order)}")
        print(f"harvesters: {list(g.harvesters)}")
        for team in Team:
            p = g.player(team)
            print(
                f"player_{team.name.lower()}: ti={p.titanium} ax={p.axionite}"
                f" ti_coll={p.titanium_collected} ax_coll={p.axionite_collected}"
                f" scale_milli={p.scale_milli}"
            )
        print(f"entities ({g.entities.items}):")
        for slot in g.entities._occupied_slots():
            print(f"  {Entity(g._raw, slot)!r}")

        self._log = (
            f"[env] {gm.width}x{gm.height}, ti={self._ti_ore}, ax={self._ax_ore}"
        )
