from dataclasses import dataclass
from enum import Enum, auto

from astar import EDGES_ROAD, astar, flow_astar
from cambc import Controller, Direction, EntityType, Environment, Position
from entity import Entity
from map_belief import _TRANSPORT, COST_IMPASSABLE, MapBelief


class Action(Enum):
    WAIT = auto()
    EXPLORE = auto()
    NAVIGATE = auto()
    PLACE_HARVESTER = auto()
    BUILD_CHAIN_SEGMENT = auto()


@dataclass
class Decision:
    action: Action
    target: Position | None = None
    aux: Position | Direction | None = None


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

    def run(self, ct: Controller) -> None:
        import time
        t0 = time.perf_counter_ns()
        self.belief.update(ct)
        t1 = time.perf_counter_ns()
        pos = ct.get_position()
        self._advance_frontier()
        decision = self._decide(pos)
        t2 = time.perf_counter_ns()
        self._execute(decision, ct, pos)
        t3 = time.perf_counter_ns()
        us = lambda a, b: (b - a) // 1000
        print(f"cpu: update={us(t0,t1)} decide={us(t1,t2)} exec={us(t2,t3)} total={us(t0,t3)}us")

    # -- Decision layer --

    def _decide(self, pos: Position) -> Decision:
        # Tier 1: connect harvesters — find one with incomplete chain, closest first
        best_chain: Decision | None = None
        best_chain_dist = 999999
        for hx, hy in self.belief.harvested:
            step = self._chain_step(pos, (hx, hy))
            if step is not None:
                dist = (pos.x - hx) ** 2 + (pos.y - hy) ** 2
                if dist < best_chain_dist:
                    best_chain_dist = dist
                    best_chain = step
                    print(f"chain: harv=({hx},{hy}) -> {step.action.name} @ {step.target}")
        if best_chain is not None:
            return best_chain

        # Tier 2: place harvester if cardinally adjacent
        unharvested = (self.belief.ore_ti | self.belief.ore_ax) - self.belief.harvested
        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            p = (pos.x + ddx, pos.y + ddy)
            if p in unharvested:
                print(f"harvest: ore at ({p[0]},{p[1]})")
                return Decision(Action.PLACE_HARVESTER, Position(p[0], p[1]))

        # Tier 3: navigate to nearest unharvested ore
        if unharvested:
            best = min(
                unharvested, key=lambda o: (pos.x - o[0]) ** 2 + (pos.y - o[1]) ** 2
            )
            adj = self._cardinal_adjacent(pos, Position(best[0], best[1]))
            if adj is not None:
                print(f"nav to ore: ({best[0]},{best[1]}) via ({adj.x},{adj.y})")
                return Decision(Action.NAVIGATE, adj)

        # Tier 4: explore
        target = self._pick_frontier_target(pos)
        if target is not None:
            print(f"explore: ({target.x},{target.y})")
            return Decision(Action.EXPLORE, target)

        print("wait")
        return Decision(Action.WAIT)

    def _chain_step(self, pos: Position, source: tuple[int, int]) -> Decision | None:
        cx, cy = self.core_pos.x, self.core_pos.y
        hx, hy = source

        # Find a passable cardinal neighbor of the source to start the flow path
        best_start = None
        best_dist = 999999
        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            sx, sy = hx + ddx, hy + ddy
            if not self.belief.in_bounds(sx, sy):
                continue
            env = self.belief.env[self.belief.idx(sx, sy)]
            if env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                continue
            d = (sx - cx) ** 2 + (sy - cy) ** 2
            if d < best_dist:
                best_dist = d
                best_start = (sx, sy)
        if best_start is None:
            return None

        path = flow_astar(self.belief, best_start[0], best_start[1], cx, cy)
        if path is None or len(path) < 2:
            return None

        # Walk the path, find the first tile that needs a building
        for k in range(len(path) - 1):
            x, y = path[k]
            nx, ny = path[k + 1]

            # Check if (x, y) already has valid transport
            si = self.belief.idx(x, y)
            sent = self.belief.entity[si]
            if sent is not None and sent[1] == self.belief.my_team:
                stype = sent[0]
                if stype in _TRANSPORT or stype == EntityType.CORE:
                    continue

            build_at = Position(x, y)
            dx, dy = nx - x, ny - y
            is_cardinal = abs(dx) + abs(dy) == 1

            # Can't build on own position — move off first
            if pos == build_at:
                adj = self._cardinal_adjacent(pos, build_at)
                if adj is not None:
                    return Decision(Action.NAVIGATE, adj)
                continue

            if is_cardinal:
                d = build_at.direction_to(Position(nx, ny))
                if pos.distance_squared(build_at) <= 2:
                    return Decision(Action.BUILD_CHAIN_SEGMENT, build_at, aux=d)
                return Decision(Action.NAVIGATE, build_at)

            # Bridge: build at (x,y) targeting (nx,ny)
            if pos.distance_squared(build_at) <= 2:
                return Decision(
                    Action.BUILD_CHAIN_SEGMENT, Position(nx, ny), aux=build_at
                )
            return Decision(Action.NAVIGATE, build_at)

        return None

    # -- Execution layer --

    def _execute(self, decision: Decision, ct: Controller, pos: Position) -> None:
        target = decision.target
        match decision.action:
            case Action.PLACE_HARVESTER if target is not None:
                self._exec_place_harvester(ct, target)
            case Action.NAVIGATE | Action.EXPLORE if target is not None:
                self._exec_navigate(ct, pos, target)
            case Action.BUILD_CHAIN_SEGMENT if target is not None:
                self._exec_build_chain(ct, target, decision.aux)
            case _:
                pass

    def _exec_place_harvester(self, ct: Controller, ore_pos: Position) -> None:
        h_cost, _ = ct.get_harvester_cost()
        ti, _ = ct.get_global_resources()
        if ti >= h_cost and ct.can_build_harvester(ore_pos):
            ct.build_harvester(ore_pos)

    def _exec_navigate(self, ct: Controller, pos: Position, target: Position) -> None:
        if pos == target:
            return
        path = astar(self.belief, pos.x, pos.y, target.x, target.y, EDGES_ROAD, ct=ct)
        if path is None or len(path) < 2:
            return
        nx, ny = path[1]
        d = pos.direction_to(Position(nx, ny))
        if ct.can_move(d):
            ct.move(d)
        else:
            nxt = Position(nx, ny)
            road_cost, _ = ct.get_road_cost()
            ti, _ = ct.get_global_resources()
            if ti >= road_cost and ct.can_build_road(nxt):
                ct.build_road(nxt)
                if ct.can_move(d):
                    ct.move(d)

    def _exec_build_chain(
        self,
        ct: Controller,
        target: Position,
        aux: Position | Direction | None,
    ) -> None:
        pos = ct.get_position()
        ti, _ = ct.get_global_resources()

        if isinstance(aux, Direction):
            build_pos = target
            if pos == build_pos:
                return
            existing = ct.get_tile_building_id(build_pos)
            if existing is not None:
                if ct.get_team(existing) == self.team:
                    ct.destroy(build_pos)
                else:
                    return
            conv_cost, _ = ct.get_conveyor_cost()
            if ti >= conv_cost and ct.can_build_conveyor(build_pos, aux):
                ct.build_conveyor(build_pos, aux)
        elif isinstance(aux, Position):
            bridge_pos = aux
            if pos == bridge_pos:
                return
            existing = ct.get_tile_building_id(bridge_pos)
            if existing is not None:
                if ct.get_team(existing) == self.team:
                    ct.destroy(bridge_pos)
                else:
                    return
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
        raise AssertionError

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
            if self.belief.in_bounds(x, y0) and self.belief.is_unseen(x, y0):
                return True
            if self.belief.in_bounds(x, y1) and self.belief.is_unseen(x, y1):
                return True
        for y in range(y0 + 1, y1):
            if self.belief.in_bounds(x0, y) and self.belief.is_unseen(x0, y):
                return True
            if self.belief.in_bounds(x1, y) and self.belief.is_unseen(x1, y):
                return True
        return False

    def _pick_frontier_target(self, pos: Position) -> Position | None:
        cx, cy = self.core_pos.x, self.core_pos.y
        r = self.explore_radius + 1
        x0, x1 = max(0, cx - r), min(self.w - 1, cx + r)
        y0, y1 = max(0, cy - r), min(self.h - 1, cy + r)
        candidates: list[tuple[int, int]] = []
        for x in range(x0, x1 + 1):
            if self.belief.in_bounds(x, y0) and self.belief.is_unseen(x, y0):
                candidates.append((x, y0))
            if self.belief.in_bounds(x, y1) and self.belief.is_unseen(x, y1):
                candidates.append((x, y1))
        for y in range(y0 + 1, y1):
            if self.belief.in_bounds(x0, y) and self.belief.is_unseen(x0, y):
                candidates.append((x0, y))
            if self.belief.in_bounds(x1, y) and self.belief.is_unseen(x1, y):
                candidates.append((x1, y))
        if not candidates:
            return None
        candidates.sort(
            key=lambda c: (
                (c[0] - pos.x) ** 2
                + (c[1] - pos.y) ** 2
                - ((c[0] - cx) ** 2 + (c[1] - cy) ** 2) // 4
            ),
        )
        return Position(candidates[0][0], candidates[0][1])
