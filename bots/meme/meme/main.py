from __future__ import annotations

import astar
import exploit
from cambc import Controller, Environment, Position
from game import Game, RawMem
from map26 import Core, Map26


class Player:
    def __init__(self) -> None:
        self._done = False
        self._log = ""
        self._map: Map26 | None = None
        self._ti_ore: tuple[int, int] | None = None
        self._ax_ore: tuple[int, int] | None = None
        self._ti_path: list[tuple[int, int]] = []
        try:
            self._map = m = Map26.read()
            if m.cores:
                ref = m.cores[0]
                best_ti = best_ax = -1
                for y in range(m.height):
                    for x in range(m.width):
                        env = m.tile(x, y)
                        if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                            d = (x - ref.x) ** 2 + (y - ref.y) ** 2
                            if env == Environment.ORE_TITANIUM and (
                                best_ti < 0 or d < best_ti
                            ):
                                best_ti = d
                                self._ti_ore = (x, y)
                            elif env == Environment.ORE_AXIONITE and (
                                best_ax < 0 or d < best_ax
                            ):
                                best_ax = d
                                self._ax_ore = (x, y)
                if self._ti_ore is not None:
                    self._ti_path = astar.run(
                        m,
                        start=self._ti_ore,
                        goal=(ref.x, ref.y),
                    )
        except (OSError, LookupError, ValueError) as e:
            self._log = f"[map] {e}"

    def run(self, c: Controller) -> None:
        if self._done:
            if self._log:
                print(self._log)
                self._log = ""
            return

        path = self._ti_path
        for i in range(len(path) - 1):
            ax, ay = path[i]
            bx, by = path[i + 1]
            c.draw_indicator_line(Position(ax, ay), Position(bx, by), 255, 200, 0)

        self._done = True

        mem, anchor = exploit.acquire()
        g = Game.open(RawMem(mem, anchor), c)
        if self._map is not None:
            _write_pattern(g, self._map.cores)

        gm = g.game_map
        self._log = (
            f"[env] {gm.width}x{gm.height}, ti={self._ti_ore}, ax={self._ax_ore}"
        )


def _write_pattern(g: Game, cores: list[Core]) -> None:
    pattern: tuple[str, ...] = (
        "###.###",
        "#...#..",
        "#.#.#.#",
        "###.###",
    )
    pat_h = len(pattern)
    pat_w = len(pattern[0])

    gm = g.game_map
    w = gm.width
    h = gm.height

    corners: tuple[tuple[int, int], ...] = (
        (0, 0),
        (w - 1, 0),
        (0, h - 1),
        (w - 1, h - 1),
    )
    best_corner: tuple[int, int] = corners[0]
    best_score = -1
    for corner_x, corner_y in corners:
        score = (
            min((corner_x - c.x) ** 2 + (corner_y - c.y) ** 2 for c in cores)
            if cores
            else 0
        )
        if score > best_score:
            best_score = score
            best_corner = (corner_x, corner_y)

    bx, by = best_corner
    x_off = (w - pat_w) if bx != 0 else 0
    y_off = (h - pat_h) if by != 0 else 0

    for row, line in enumerate(pattern):
        for col, ch in enumerate(line):
            gm.tile(x_off + col, y_off + row).environment = (
                Environment.WALL if ch == "#" else Environment.EMPTY
            )
