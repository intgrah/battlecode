import heapq
from collections.abc import Callable

from cambc import Controller, Direction, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]
_CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]


class Nav:
    def __init__(self, w: int, h: int) -> None:
        self.w = w
        self.h = h
        self.size = w * h
        self.env: list[int] = [0] * self.size  # 0=unknown, 1=empty, 2=wall, 3=ore
        self.walkable: list[float] = [1.0] * self.size
        self.unreachable = False
        self._prev_target: tuple[int, int] | None = None
        self._stuck: int = 0
        self._prev_pos: tuple[int, int] | None = None

    def update(self, ct: Controller) -> None:
        my = ct.get_team()
        for t in ct.get_nearby_tiles():
            idx = t.y * self.w + t.x
            env = ct.get_tile_env(t)
            if env == Environment.WALL:
                self.env[idx] = 2
                self.walkable[idx] = 999.0
                continue
            if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                self.env[idx] = 3
                self.walkable[idx] = 2.0
            else:
                self.env[idx] = 1
                self.walkable[idx] = 1.0

            bid = ct.get_tile_building_id(t)
            if bid is not None:
                if ct.is_tile_passable(t):
                    self.walkable[idx] = 0.9
                else:
                    self.walkable[idx] = 999.0
            else:
                bot = ct.get_tile_builder_bot_id(t)
                if bot is not None and bot != ct.get_id():
                    self.walkable[idx] = 5.0

    def go(
        self,
        ct: Controller,
        target: Position,
        step_fn: Callable[[Direction], bool],
        cardinal_only: bool = False,
    ) -> bool:
        pos = ct.get_position()
        if pos.x == target.x and pos.y == target.y:
            return False

        px, py = pos.x, pos.y
        if self._prev_pos == (px, py):
            self._stuck += 1
        else:
            self._stuck = 0
        self._prev_pos = (px, py)

        if self._stuck > 10:
            self.unreachable = True
            self._stuck = 0
            return False

        if self._prev_target != (target.x, target.y):
            self._prev_target = (target.x, target.y)
            self.unreachable = False

        d = self._astar(ct, pos, target, cardinal_only)
        if d is None:
            self.unreachable = True
            return False
        if step_fn(d):
            return True

        for alt in DIRS if not cardinal_only else _CARDINALS:
            if alt == d:
                continue
            if step_fn(alt):
                return True
        return False

    def _astar(
        self,
        ct: Controller,
        start: Position,
        goal: Position,
        cardinal_only: bool,
    ) -> Direction | None:
        start_t = ct.get_cpu_time_elapsed()
        w, h = self.w, self.h
        sx, sy = start.x, start.y
        gx, gy = goal.x, goal.y
        start_idx = sy * w + sx
        goal_idx = gy * w + gx

        if start_idx == goal_idx:
            return None

        dirs = _CARDINALS if cardinal_only else DIRS
        inf = 999999
        g_scores = [inf] * self.size
        g_scores[start_idx] = 0

        best_h = self._heuristic(sx, sy, gx, gy, cardinal_only)
        best_move: Direction | None = None

        open_set: list[tuple[float, int, int, Direction]] = []

        for d in dirs:
            dx, dy = d.delta()
            nx, ny = sx + dx, sy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            if self.walkable[ni] >= 999.0:
                continue
            g_scores[ni] = 1
            h = self._heuristic(nx, ny, gx, gy, cardinal_only) * self.walkable[ni]
            heapq.heappush(open_set, (1.0 + h, 1, ni, d))
            if h < best_h:
                best_h = h
                best_move = d

        while open_set:
            f, depth, current, first_move = heapq.heappop(open_set)

            if current == goal_idx:
                return first_move

            if ct.get_cpu_time_elapsed() - start_t > 1500:
                return best_move

            cx, cy = current % w, current // w

            for d in dirs:
                dx, dy = d.delta()
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                ni = ny * w + nx
                if self.walkable[ni] >= 999.0:
                    continue
                new_g = depth + 1
                if new_g < g_scores[ni]:
                    g_scores[ni] = new_g
                    h = (
                        self._heuristic(nx, ny, gx, gy, cardinal_only)
                        * self.walkable[ni]
                    )
                    if h < best_h:
                        best_h = h
                        best_move = first_move
                    heapq.heappush(open_set, (new_g + h, new_g, ni, first_move))

        return best_move

    @staticmethod
    def _heuristic(x: int, y: int, gx: int, gy: int, cardinal_only: bool) -> float:
        dx = abs(x - gx)
        dy = abs(y - gy)
        if cardinal_only:
            return float(dx + dy)
        return float(dx + dy) + (1.414 - 2.0) * min(dx, dy)
