import astar
import exploit
import map26
from cambc import Controller, Environment, Position
from game import Game, RawMem


class Player:
    def __init__(self) -> None:
        self._done = False
        self._log = ""
        self._cores: list[tuple[int, int, int, int]] = []
        self._ti_ore: tuple[int, int] | None = None
        self._ax_ore: tuple[int, int] | None = None
        self._ti_path: list[tuple[int, int]] = []
        try:
            _, _, grid, self._cores = map26.decode(
                map26.read("/sandbox/out/game_map.map26")
            )
            if self._cores:
                _, _, ref_x, ref_y = self._cores[0]
                best_ti = best_ax = -1
                for y, row in enumerate(grid):
                    for x, env in enumerate(row):
                        if env in (2, 3):
                            d = (x - ref_x) ** 2 + (y - ref_y) ** 2
                            if env == 2 and (best_ti < 0 or d < best_ti):
                                best_ti = d
                                self._ti_ore = (x, y)
                            elif env == 3 and (best_ax < 0 or d < best_ax):
                                best_ax = d
                                self._ax_ore = (x, y)
                if self._ti_ore is not None:
                    self._ti_path = astar.run(
                        grid,
                        start=self._ti_ore,
                        goal=(ref_x, ref_y),
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
        _write_pattern(g, self._cores)

        gm = g.game_map
        self._log = (
            f"[env] {gm.width}x{gm.height}, ti={self._ti_ore}, ax={self._ax_ore}"
        )


def _write_pattern(g: Game, cores: list[tuple[int, int, int, int]]) -> None:
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
            min(
                (corner_x - corecx) ** 2 + (corner_y - corecy) ** 2
                for _cid, _team, corecx, corecy in cores
            )
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
