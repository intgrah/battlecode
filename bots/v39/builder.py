import random
import time

from cambc import Controller, Direction, EntityType, Environment, Position
from entity import Entity
from map_belief import _TRANSPORT, COST_IMPASSABLE, MapBelief
from nav import flow_astar, nav_astar


class Builder(Entity):
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.core_pos = self._find_core(ct)
        self.belief = MapBelief(
            self.w,
            self.h,
            self.team,
            (self.core_pos.x, self.core_pos.y),
        )
        self.explore_radius = 0
        self._cached_chain_source: tuple[int, int] | None = None
        self._cached_chain_path: list[tuple[int, int]] | None = None
        self._flow_search = None
        self._rng = random.Random()
        self._goal: tuple[str, tuple[int, int]] | None = None
        self._recent_pos: list[tuple[int, int]] = []

    def run(self, ct: Controller) -> None:
        self._eid = ct.get_id()
        t0 = time.perf_counter_ns()
        changed = self.belief.update(ct)
        needs_reflow = any(
            self.belief.idx(cx, cy) in self.belief.transport_tiles
            or self.belief.idx(cx, cy) in self.belief.harvester_tiles
            for cx, cy in changed
        )
        self._reflow_this_turn = False
        if needs_reflow:
            self.belief.recompute_flow()
            self._flow_search = None
            self._cached_chain_path = None
            self._reflow_this_turn = True

        t1 = time.perf_counter_ns()
        pos = ct.get_position()
        self._advance_frontier()
        self._action = "idle"
        self._act(ct, pos)
        t2 = time.perf_counter_ns()

        if not hasattr(self, "_cpu_log"):
            self._cpu_log = open(f"/tmp/v39_cpu_{self._eid}.log", "w")
        rnd = ct.get_current_round()
        nav_fail = getattr(self, "_nav_fail", "")
        extra = f" [{nav_fail}]" if nav_fail else ""
        self._nav_fail = ""
        self._cpu_log.write(f"{rnd} {pos.x},{pos.y} {self._action}{extra}\n")

    def _act(self, ct: Controller, pos: Position) -> None:
        if self._try_place_harvester(ct, pos):
            self._goal = None
            return

        self._validate_goal()

        if self._goal is None:
            self._goal = self._pick_goal(pos)
        if self._goal is None:
            return

        kind, target = self._goal
        self._action = f"{kind} -> {target[0]},{target[1]}"
        if kind == "fix_excess":
            i = self.belief.idx(target[0], target[1])
            self._action += f" ex={self.belief.excess[i]:.2f} fl={self.belief.flow_in[i]:.2f} ent={self.belief.entity[i]}"
            if not self._build_chain(ct, pos, target):
                self._goal = None
        elif kind == "harvest":
            adj = self._cardinal_adjacent(pos, Position(target[0], target[1]))
            if adj is None:
                self._goal = None
            else:
                self._navigate(ct, pos, adj)
        elif kind == "explore":
            self._navigate(ct, pos, Position(target[0], target[1]))

    def _validate_goal(self) -> None:
        if self._goal is None:
            return
        kind, target = self._goal
        if kind == "fix_excess":
            i = self.belief.idx(target[0], target[1])
            if self.belief.excess[i] <= 0.01:
                self._goal = None
        elif kind == "harvest":
            if target in self.belief.harvested:
                self._goal = None
        elif kind == "explore":
            if not self.belief.is_unseen(target[0], target[1]):
                self._goal = None

    def _pick_goal(self, pos: Position) -> tuple[str, tuple[int, int]] | None:
        best_tile = None
        best_dist = 999999
        for i in self.belief.harvester_tiles | self.belief.transport_tiles:
            if self.belief.excess[i] > 0.01:
                x, y = i % self.belief.w, i // self.belief.w
                dist = (pos.x - x) ** 2 + (pos.y - y) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best_tile = (x, y)
        if best_tile is not None:
            return ("fix_excess", best_tile)

        unharvested = (self.belief.ore_ti | self.belief.ore_ax) - self.belief.harvested
        if unharvested:
            candidates = sorted(
                unharvested,
                key=lambda o: (pos.x - o[0]) ** 2 + (pos.y - o[1]) ** 2,
            )
            for ore in candidates:
                adj = self._cardinal_adjacent(pos, Position(ore[0], ore[1]))
                if adj is not None:
                    return ("harvest", ore)

        target = self._pick_frontier_target(pos)
        if target is not None:
            return ("explore", (target.x, target.y))

        unseen = sum(1 for e in self.belief.env if e is None)
        self._action = f"idle r={self.explore_radius} unseen={unseen}"
        return None

    def _try_place_harvester(self, ct: Controller, pos: Position) -> bool:
        unharvested = (self.belief.ore_ti | self.belief.ore_ax) - self.belief.harvested
        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            p = (pos.x + ddx, pos.y + ddy)
            if p in unharvested:
                ore_pos = Position(p[0], p[1])
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti >= h_cost and ct.can_build_harvester(ore_pos):
                    ct.build_harvester(ore_pos)
                    self._action = "place_harv"
                    return True
        return False

    def _navigate(self, ct: Controller, pos: Position, target: Position) -> None:
        if pos == target:
            return
        cur = (pos.x, pos.y)
        self._recent_pos.append(cur)
        if len(self._recent_pos) > 6:
            self._recent_pos.pop(0)

        oscillating = len(self._recent_pos) >= 4 and cur in self._recent_pos[:-2]
        if oscillating:
            self._goal = None

        path = nav_astar(
            self.belief,
            pos.x,
            pos.y,
            target.x,
            target.y,
            max_expand=2500,
        )
        if path is None or len(path) < 2:
            self._action += f" nopath->{target.x},{target.y}"
            return
        if len(path) <= 6:
            self._action += f" path={path}"
        else:
            self._action += f" path={path[:3]}...{path[-1]} len={len(path)}"
        nx, ny = path[1]
        d = pos.direction_to(Position(nx, ny))
        if ct.can_move(d):
            ct.move(d)
        else:
            self._action += f" blocked@{nx},{ny}"
            nxt = Position(nx, ny)
            road_cost, _ = ct.get_road_cost()
            ti, _ = ct.get_global_resources()
            if ti >= road_cost and ct.can_build_road(nxt):
                ct.build_road(nxt)
                if ct.can_move(d):
                    ct.move(d)

    def _build_chain(
        self, ct: Controller, pos: Position, source: tuple[int, int]
    ) -> bool:
        cx, cy = self.core_pos.x, self.core_pos.y
        sx, sy = source

        si = self.belief.idx(sx, sy)
        ent = self.belief.entity[si]

        if ent is not None:
            etype = ent[0]
            if etype == EntityType.HARVESTER:
                best_start = None
                best_d = 999999
                for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = sx + ddx, sy + ddy
                    if not self.belief.in_bounds(nx, ny):
                        continue
                    env = self.belief.env[self.belief.idx(nx, ny)]
                    if env in (
                        Environment.WALL,
                        Environment.ORE_TITANIUM,
                        Environment.ORE_AXIONITE,
                    ):
                        continue
                    d = (nx - cx) ** 2 + (ny - cy) ** 2
                    if d < best_d:
                        best_d = d
                        best_start = (nx, ny)
                if best_start is None:
                    return False
                sx, sy = best_start
            elif etype in _TRANSPORT:
                d = self.belief.direction[si]
                bt = self.belief.bridge_target[si]
                if d is not None:
                    dx, dy = d.delta()
                    ox, oy = sx + dx, sy + dy
                    if self.belief.in_bounds(ox, oy):
                        sx, sy = ox, oy
                elif bt is not None:
                    sx, sy = bt

        start = (sx, sy)
        path = self._cached_chain_path
        if path is None or self._cached_chain_source != start:
            if self._flow_search is None or self._cached_chain_source != start:
                self._flow_search = flow_astar(
                    self.belief,
                    sx,
                    sy,
                    self.core_pos.x,
                    self.core_pos.y,
                )
                self._cached_chain_source = start
            self._flow_search.compute(30 if self._reflow_this_turn else 60)
            path = self._flow_search.get_path()
            if self._flow_search.done:
                self._flow_search = None
            self._cached_chain_path = path
        if path is None or len(path) < 2:
            self._cached_chain_path = None
            self._action += f" chain:nopath start=({sx},{sy}) env={self.belief.env[self.belief.idx(sx,sy)]}"
            return False

        for k in range(len(path) - 1):
            x, y = path[k]
            nx, ny = path[k + 1]

            pi = self.belief.idx(x, y)
            pent = self.belief.entity[pi]
            if pent is not None and pent[1] == self.belief.my_team:
                ptype = pent[0]
                if ptype in _TRANSPORT or ptype == EntityType.CORE:
                    continue

            build_at = Position(x, y)
            dx, dy = nx - x, ny - y
            is_cardinal = abs(dx) + abs(dy) == 1

            if pos == build_at:
                adj = self._cardinal_adjacent(pos, build_at)
                if adj is not None:
                    self._navigate(ct, pos, adj)
                    return True
                continue

            if is_cardinal:
                if pos.distance_squared(build_at) <= 2:
                    self._place_conveyor(ct, build_at, Position(nx, ny))
                    return True
                adj = self._cardinal_adjacent(pos, build_at)
                if adj is not None:
                    self._navigate(ct, pos, adj)
                    return True
                continue

            if pos.distance_squared(build_at) <= 2:
                self._place_bridge(ct, build_at, Position(nx, ny))
                return True
            adj = self._cardinal_adjacent(pos, build_at)
            if adj is not None:
                self._navigate(ct, pos, adj)
                return True

        self._action += f" chain:allbuilt path={path[:3]}..{path[-1]} len={len(path)}"
        return False

    def _place_conveyor(
        self, ct: Controller, build_pos: Position, toward: Position
    ) -> None:
        pos = ct.get_position()
        if pos == build_pos:
            return
        d = build_pos.direction_to(toward)
        existing = ct.get_tile_building_id(build_pos)
        if existing is not None:
            if ct.get_team(existing) == self.team:
                ct.destroy(build_pos)
            else:
                return
        ti, _ = ct.get_global_resources()
        conv_cost, _ = ct.get_conveyor_cost()
        if ti >= conv_cost and ct.can_build_conveyor(build_pos, d):
            ct.build_conveyor(build_pos, d)

    def _place_bridge(
        self, ct: Controller, bridge_pos: Position, target: Position
    ) -> None:
        pos = ct.get_position()
        if pos == bridge_pos:
            return
        existing = ct.get_tile_building_id(bridge_pos)
        if existing is not None:
            if ct.get_team(existing) == self.team:
                ct.destroy(bridge_pos)
            else:
                return
        ti, _ = ct.get_global_resources()
        bridge_cost, _ = ct.get_bridge_cost()
        if ti >= bridge_cost and ct.can_build_bridge(bridge_pos, target):
            ct.build_bridge(bridge_pos, target)

    # -- Helpers --

    def _cardinal_adjacent(self, pos: Position, target: Position) -> Position | None:
        best = None
        best_dist = 999999
        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ax, ay = target.x + ddx, target.y + ddy
            if not self.belief.in_bounds(ax, ay):
                continue
            if self.belief.walkable(ax, ay) >= COST_IMPASSABLE:
                continue
            dist = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
            if dist < best_dist:
                best_dist = dist
                best = Position(ax, ay)
        return best

    def _find_core(self, ct: Controller) -> Position:
        my = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
                return ct.get_position(bid)
        msg = "core not found"
        raise RuntimeError(msg)

    def _advance_frontier(self) -> None:
        cx, cy = self.core_pos.x, self.core_pos.y
        limit = max(self.w, self.h)
        while self.explore_radius < limit:
            r = self.explore_radius + 1
            if self._ring_has_unseen(cx, cy, r):
                break
            self.explore_radius = r

    def _ring_has_unseen(self, cx: int, cy: int, r: int) -> bool:
        x0, x1 = max(0, cx - r), min(self.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.h - 1, cy + r)
        for x in range(x0, x1 + 1):
            if self.belief.is_unseen(x, y0):
                return True
            if self.belief.is_unseen(x, y1):
                return True
        for y in range(y0 + 1, y1):
            if self.belief.is_unseen(x0, y):
                return True
            if self.belief.is_unseen(x1, y):
                return True
        return False

    def _pick_frontier_target(self, pos: Position) -> Position | None:
        cx, cy = self.core_pos.x, self.core_pos.y
        r = self.explore_radius + 1
        x0, x1 = max(0, cx - r), min(self.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.h - 1, cy + r)
        candidates: list[tuple[int, int]] = []
        for x in range(x0, x1 + 1):
            if self.belief.is_unseen(x, y0):
                candidates.append((x, y0))
            if self.belief.is_unseen(x, y1):
                candidates.append((x, y1))
        for y in range(y0 + 1, y1):
            if self.belief.is_unseen(x0, y):
                candidates.append((x0, y))
            if self.belief.is_unseen(x1, y):
                candidates.append((x1, y))
        if not candidates:
            return None
        candidates.sort(
            key=lambda c: (c[0] - pos.x) ** 2 + (c[1] - pos.y) ** 2,
        )
        return Position(candidates[0][0], candidates[0][1])
