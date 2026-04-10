"""A* connect-back chain planning for conveyor/bridge routing.

Holds its own classification grid (one int per tile) plus precomputed
cardinal and bridge neighbor tables.

The grid is padded by 3 tiles on every side. All padding tiles are
permanently `IMPASSABLE`, so every real tile has full cardinal and
bridge neighborhoods with no bounds checks anywhere.
"""

from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from cambc import Controller, Direction, EntityType, Environment, Position

# Building instruction: (entity_type, where_to_build, extra)
#   CONVEYOR / SPLITTER / etc → extra is a Direction
#   BRIDGE                    → extra is the target Position
#   anything directionless    → extra is None
BuildInstruction = tuple[EntityType, Position, "Direction | Position | None"]

from lib.visualiser.src.visualiser import Grid, Palette, emit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

INF = 1_000_000

# cost[classification] for cardinal (conveyor) and bridge edges
IMPASSABLE = 0
FRIENDLY_ROAD = 1
ENEMY_ROAD = 2
ORE = 3
UNREACHABLE = 4
_CARD_COST: tuple[int, ...] = (INF, 1, 4, 4, INF)
_BRIDGE_COST: tuple[int, ...] = (INF, 10, 15, 10, INF)

CARDINAL_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))

BRIDGE_OFFSETS: tuple[tuple[int, int], ...] = tuple(
    (dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 0 < dx * dx + dy * dy <= 9
)

_EDGE_CONV = 0
_EDGE_BRIDGE = 1

_PAD = 3


class ChainAstar:
    """A* chain planner with a tailored classification grid + static
    cardinal/bridge neighbor tables. Grid is padded by 3 on each side
    so all real tiles use unconditional int-offset neighbor lookups.
    """

    def __init__(self, map_w: int, map_h: int) -> None:
        self.map_w = map_w
        self.map_h = map_h
        pw = map_w + 2 * _PAD
        ph = map_h + 2 * _PAD
        self._pw = pw
        self._ph = ph
        n = pw * ph
        self._n = n

        # Padded classification grid. Padding stays IMPASSABLE forever;
        # real tiles start UNSEEN until observed.
        self._cls: list[int] = [IMPASSABLE] * n
        for ry in range(map_h):
            row = (ry + _PAD) * pw + _PAD
            self._cls[row : row + map_w] = [UNREACHABLE] * map_w

        # Effective classification used by the pathfinder. Mirrors `_cls`
        # except where `block()` has overlaid IMPASSABLE for the current
        # plan attempt. Cleared between plan attempts via `clear_blocked()`
        # without disturbing observations on `_cls`.
        self._eff_cls: list[int] = list(self._cls)
        self._blocked: set[int] = set()

        # Flat-index neighbor offsets in padded coordinates.
        self._card_offsets: tuple[int, ...] = tuple(
            dy * pw + dx for dx, dy in CARDINAL_DELTAS
        )
        self._bridge_offsets: tuple[int, ...] = tuple(
            dy * pw + dx for dx, dy in BRIDGE_OFFSETS
        )

        # Neighbor tables (flat padded indices). Only real tiles are filled.
        self._cnb: list[list[int]] = [[] for _ in range(n)]
        self._bnb: list[list[int]] = [[] for _ in range(n)]
        self._cnb_row: int = 0
        self._bnb_row: int = 0
        self._nb_done: bool = False

        self._starts: tuple[tuple[int, int], ...] = ()
        self._last_g: dict[int, int] = {}
        self._gx = 0
        self._gy = 0

    def _pi(self, x: int, y: int) -> int:
        """Real (x, y) → padded flat index."""
        return (y + _PAD) * self._pw + (x + _PAD)

    def _init_nb_chunk(self, within_budget: Callable[[], bool]) -> bool:
        """Build cnb/bnb incrementally over real tiles. Returns True when complete."""
        w = self.map_w
        pw = self._pw
        total = w * self.map_h
        skip = 2 * _PAD  # right padding + left padding of next row
        cnb = self._cnb
        bnb = self._bnb
        card_offsets = self._card_offsets
        bridge_offsets = self._bridge_offsets

        # Phase 1: cnb for every real tile.
        progress = self._cnb_row
        rx = progress % w
        pi = (progress // w + _PAD) * pw + _PAD + rx
        while progress < total:
            cnb[pi] = [pi + o for o in card_offsets]
            progress += 1
            rx += 1
            if rx == w:
                rx = 0
                pi += skip + 1
            else:
                pi += 1
            if progress & 255 == 0 and not within_budget():
                self._cnb_row = progress
                return False
        self._cnb_row = progress

        # Phase 2: bnb for every real tile.
        progress = self._bnb_row
        rx = progress % w
        pi = (progress // w + _PAD) * pw + _PAD + rx
        while progress < total:
            bnb[pi] = [pi + o for o in bridge_offsets]
            progress += 1
            rx += 1
            if rx == w:
                rx = 0
                pi += skip + 1
            else:
                pi += 1
            if progress & 255 == 0 and not within_budget():
                self._bnb_row = progress
                return False
        self._bnb_row = progress
        self._nb_done = True
        return True

    def update_tile(
        self,
        x: int,
        y: int,
        env: Environment,
        building_type: EntityType | None,
        is_allied: bool,
        force_update: bool = False,
    ) -> None:

        pi = self._pi(x, y)
        if not force_update and self._cls[pi] == UNREACHABLE:
            return

        if env == Environment.WALL:
            cls = IMPASSABLE
        elif env == Environment.ORE_TITANIUM or env == Environment.ORE_AXIONITE:
            cls = ORE
        else:
            cls = FRIENDLY_ROAD

        if building_type is not None:
            if building_type == EntityType.ROAD:
                if cls < FRIENDLY_ROAD and is_allied:
                    cls = FRIENDLY_ROAD
                if cls < ENEMY_ROAD and not is_allied:
                    cls = ENEMY_ROAD
            else:
                cls = IMPASSABLE

        self._cls[pi] = cls
        if pi not in self._blocked:
            self._eff_cls[pi] = cls

    def block(self, x: int, y: int) -> None:
        """Mark (x, y) as IMPASSABLE for the current plan attempt only.
        Does not mutate `_cls`; observations remain authoritative.
        """
        pi = self._pi(x, y)
        if pi not in self._blocked:
            self._blocked.add(pi)
            self._eff_cls[pi] = IMPASSABLE

    def clear_blocked(self) -> None:
        """Drop all per-plan blocks, restoring `_eff_cls` from `_cls`."""
        cls = self._cls
        eff = self._eff_cls
        for pi in self._blocked:
            eff[pi] = cls[pi]
        self._blocked.clear()

    def set_starts(self, starts: Iterable[tuple[int, int]]) -> None:
        self._starts = tuple(starts)

    def set_goal(self, x: int, y: int) -> None:
        self._gx, self._gy = x, y

    def ore_offset(
        self, ore: tuple[int, int], ref: tuple[int, int]
    ) -> tuple[int, int] | None:
        """Pick the best cardinally-adjacent tile to `ore`.

        Picks the neighbor with the lowest `_CARD_COST`; ties broken by
        smallest Manhattan distance to `ref`. Returns ``None`` if every
        candidate neighbor has INF cost (out of bounds or impassable).
        """
        w, h = self.map_w, self.map_h
        cls = self._eff_cls
        ox, oy = ore
        sx, sy = ref
        best: tuple[int, int, int, int] = (INF, 0, ox, oy)
        for dx, dy in CARDINAL_DELTAS:
            nx, ny = ox + dx, oy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = self._pi(nx, ny)
            cost = _CARD_COST[cls[ni]]
            dist = abs(nx - sx) + abs(ny - sy)
            key = (cost, dist, nx, ny)
            if key < best:
                best = key
        if best[0] >= INF:
            return None
        return (best[2], best[3])

    def plan(
        self,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> list[BuildInstruction] | None:
        # Spend remaining startup-round budget building the nb tables.
        if not self._nb_done:
            if not self._init_nb_chunk(within_budget):
                return None
        return self._compute(within_budget)

    def draw_path(
        self,
        ct: Controller,
        chain_path: list[BuildInstruction],
    ) -> None:
        """Draw a planned chain on the visualiser. Conveyors are yellow
        line segments from the build tile toward where their output flows;
        bridges are red lines from the bridge tile to the target tile.
        """
        for entity, pos, extra in chain_path:
            if entity == EntityType.BRIDGE:
                ct.draw_indicator_line(pos, extra, 255, 0, 0)
            elif entity == EntityType.CONVEYOR:
                ct.draw_indicator_line(pos, pos.add(extra), 255, 200, 0)

    def emit_vis(self) -> None:
        """Emit the A* g-score (distance) field to the visualiser."""
        w, h = self.map_w, self.map_h
        pw = self._pw
        cls = self._cls
        dist_list: list[int] = [-1] * (w * h)
        cls_list: list[int] = [UNREACHABLE] * (w * h)
        for i, g in self._last_g.items():
            py, px = divmod(i, pw)
            ry, rx = py - _PAD, px - _PAD
            if 0 <= rx < w and 0 <= ry < h:
                dist_list[ry * w + rx] = g
        for i in range(len(cls)):
            py, px = divmod(i, pw)
            ry, rx = py - _PAD, px - _PAD
            if 0 <= rx < w and 0 <= ry < h:
                cls_list[ry * w + rx] = cls[i]
        emit(
            astar_dist=Grid(
                dist_list,
                palette=Palette(
                    stops=[(0.0, 0, 200, 0, 120), (1.0, 200, 0, 0, 180)],
                    special={-1: (0, 0, 0, 0)},
                ),
            ),
            astar_cls=Grid(
                cls_list,
                palette=Palette(
                    stops=[(0.0, 0, 200, 0, 120), (1.0, 200, 0, 0, 180)],
                    special={-1: (0, 0, 0, 0)},
                ),
            ),
        )

    def _reconstruct(
        self,
        node: int,
        came_from: dict[int, tuple[int, int]],
    ) -> list[BuildInstruction]:
        """Walk `came_from` from goal back to start and emit a list of
        building instructions, ordered goal → start.

        Each instruction places a building at the *child* tile of an edge
        (the tile farther from the chosen start), oriented so that
        resources flow back toward the parent (closer to the start).

        Conveyors point at the parent; bridges target the parent.
        """
        pw = self._pw
        path: list[BuildInstruction] = []
        while node in came_from:
            edge_type, parent = came_from[node]
            py, px = divmod(parent, pw)
            ny, nx = divmod(node, pw)
            child_pos = Position(nx - _PAD, ny - _PAD)
            parent_pos = Position(px - _PAD, py - _PAD)
            if edge_type == _EDGE_CONV:
                path.append(
                    (
                        EntityType.CONVEYOR,
                        child_pos,
                        child_pos.direction_to(parent_pos),
                    ),
                )
            else:
                path.append((EntityType.BRIDGE, child_pos, parent_pos))
            node = parent
        return path

    def _compute(
        self,
        within_budget: Callable[[], bool] = lambda: True,
    ) -> list[BuildInstruction] | None:
        pw = self._pw
        cls = self._eff_cls
        cnb = self._cnb
        bnb = self._bnb
        card_cost = _CARD_COST
        bridge_cost = _BRIDGE_COST

        _abs = abs
        _divmod = divmod

        goal = self._pi(self._gx, self._gy)
        gy_p, gx_p = _divmod(goal, pw)

        # Heap entries: (f, counter, node, g_at_push). Stale entries are
        # skipped via `g_at_push != g_score[node]` (canonical A* idiom),
        # avoiding a recompute of the heuristic at pop.
        open_heap: list[tuple[int, int, int, int]] = []
        g_score: dict[int, int] = {}
        self._last_g = g_score
        came_from: dict[int, tuple[int, int]] = {}
        counter = 0

        if not self._starts:
            print("no starts in AStar!")
            return None

        best_h_node = self._pi(*self._starts[0])
        best_h_val = INF
        for sx, sy in self._starts:
            s = self._pi(sx, sy)
            if g_score.get(s, INF) <= 0:
                continue
            g_score[s] = 0
            sy_p, sx_p = _divmod(s, pw)
            h0 = _abs(sx_p - gx_p) + _abs(sy_p - gy_p)
            heapq.heappush(open_heap, (h0, counter, s, 0))
            counter += 1
            if h0 < best_h_val:
                best_h_val = h0
                best_h_node = s
        iterations = 0

        _heappush = heapq.heappush
        _heappop = heapq.heappop
        _g_get = g_score.get

        while open_heap:
            _, _, node, g_at_push = _heappop(open_heap)

            if node == goal:
                return self._reconstruct(node, came_from)

            if g_at_push != _g_get(node, INF):
                continue
            current_g = g_at_push

            for ni in cnb[node]:
                c = card_cost[cls[ni]]
                if c >= INF:
                    if ni != goal:
                        continue
                    c = _CARD_COST[1]
                ng = current_g + c
                if ng < _g_get(ni, INF):
                    g_score[ni] = ng
                    came_from[ni] = (_EDGE_CONV, node)
                    ny, nx = _divmod(ni, pw)
                    nh = _abs(nx - gx_p) + _abs(ny - gy_p)
                    if nh < best_h_val:
                        best_h_val = nh
                        best_h_node = ni
                    _heappush(open_heap, (ng + nh, counter, ni, ng))
                    counter += 1

            for ni in bnb[node]:
                c = bridge_cost[cls[ni]]
                if c >= INF:
                    if ni != goal:
                        continue
                    c = _BRIDGE_COST[1]
                ng = current_g + c
                if ng < _g_get(ni, INF):
                    g_score[ni] = ng
                    came_from[ni] = (_EDGE_BRIDGE, node)
                    ny, nx = _divmod(ni, pw)
                    nh = _abs(nx - gx_p) + _abs(ny - gy_p)
                    if nh < best_h_val:
                        best_h_val = nh
                        best_h_node = ni
                    _heappush(open_heap, (ng + nh, counter, ni, ng))
                    counter += 1

            iterations += 1
            if iterations & 255 == 0 and not within_budget():
                if best_h_node in came_from:
                    return self._reconstruct(best_h_node, came_from)
                print("no best node in AStar!")
                return None

        print("no route found in AStar!")
        return None
