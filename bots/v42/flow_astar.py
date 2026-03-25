from algorithms import Astar
from cambc import Controller, EntityType, Environment
from map_belief import MapBelief
from util import BRIDGE_DELTAS, DIR4_DELTA

COST_REUSE = 0
COST_CONV = 3
COST_BRIDGE = 10
COST_ROAD_REPLACE = 3
CONV_CUTOFF_SQ = 0

_IMPASSABLE_ENV = frozenset(
    (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE),
)

TI = 0b001
AX = 0b010
RAX = 0b100


def build_leakage_mask(belief: MapBelief) -> list[int]:
    w, h = belief.w, belief.h
    n = w * h
    mask = [0] * n
    for i in range(n):
        ent = belief.entity[i]
        if ent is None:
            continue
        etype, team = ent
        if team != belief.my_team:
            continue
        if etype == EntityType.FOUNDRY:
            ix, iy = i % w, i // w
            for ddx, ddy in DIR4_DELTA:
                nx, ny = ix + ddx, iy + ddy
                if 0 <= nx < w and 0 <= ny < h:
                    mask[ny * w + nx] |= RAX
        elif etype == EntityType.SPLITTER:
            d = belief.direction[i]
            if d is None:
                continue
            ix, iy = i % w, i // w
            dx, dy = d.delta()
            commodity = 0
            f = belief.my_flow
            if f.ti[i] > 0:
                commodity |= TI
            if f.ax[i] > 0:
                commodity |= AX
            if f.rax[i] > 0:
                commodity |= RAX
            if commodity == 0:
                continue
            for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                nx, ny = ix + odx, iy + ody
                if 0 <= nx < w and 0 <= ny < h:
                    mask[ny * w + nx] |= commodity

    for i in range(n):
        e = belief.env[i]
        if e == Environment.ORE_TITANIUM:
            commodity = TI
        elif e == Environment.ORE_AXIONITE:
            commodity = AX
        else:
            continue
        ix, iy = i % w, i // w
        for ddx, ddy in DIR4_DELTA:
            nx, ny = ix + ddx, iy + ddy
            if 0 <= nx < w and 0 <= ny < h:
                mask[ny * w + nx] |= commodity

    return mask


class FlowAstar(Astar[int]):
    def __init__(
        self,
        belief: MapBelief,
        sx: int,
        sy: int,
        goals: set[int],
        banned_leakage: int,
    ) -> None:
        self._w = belief.w
        self._h = belief.h
        core_x, core_y = belief.my_core
        self._gx = core_x
        self._gy = core_y
        self._banned_leakage = banned_leakage
        self._leakage_mask = build_leakage_mask(belief)
        self._blocked = belief.my_flow.blocked
        self._env = belief.env
        self._entity = belief.entity
        self._direction = belief.direction
        self._bridge_target = belief.bridge_target
        self._my_team = belief.my_team
        self._core_x = core_x
        self._core_y = core_y
        self._ct: Controller | None = None
        self._budget_us = 0
        si = sy * self._w + sx
        super().__init__(si, goals)

    def set_budget(self, ct: Controller, budget_us: int) -> None:
        self._ct = ct
        self._budget_us = budget_us

    def should_continue(self) -> bool:
        if self._ct is None:
            return True
        return self._ct.get_cpu_time_elapsed() < self._budget_us

    def heuristic(self, node: int) -> int:
        return abs(node % self._w - self._gx) + abs(node // self._w - self._gy)

    def get_neighbors(self, node: int) -> list[tuple[int, int]]:
        w, h = self._w, self._h
        blocked = self._blocked
        env = self._env
        entity = self._entity
        direction = self._direction
        bridge_target = self._bridge_target
        leakage_mask = self._leakage_mask
        banned_leakage = self._banned_leakage

        if blocked[node]:
            return []
        e = env[node]
        if e is not None and e in _IMPASSABLE_ENV:
            return []
        ent = entity[node]
        if ent is not None and ent[1] != self._my_team:
            return []
        if leakage_mask[node] & banned_leakage != 0:
            return []

        cx, cy = node % w, node // w
        result: list[tuple[int, int]] = []

        match ent:
            case (EntityType.CORE, _):
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if not blocked[ni] and (
                            env[ni] is None or env[ni] not in _IMPASSABLE_ENV
                        ):
                            result.append((ni, 0))

            case (EntityType.BRIDGE, _):
                bt = bridge_target[node]
                if bt is not None:
                    bx, by = bt
                    if 0 <= bx < w and 0 <= by < h:
                        ni = by * w + bx
                        if (
                            not blocked[ni]
                            and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                            and leakage_mask[ni] & banned_leakage == 0
                        ):
                            result.append((ni, COST_REUSE))

            case (
                EntityType.CONVEYOR
                | EntityType.ARMOURED_CONVEYOR
                | EntityType.SPLITTER,
                _,
            ):
                d = direction[node]
                if d is not None:
                    ddx, ddy = d.delta()
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if (
                            not blocked[ni]
                            and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                            and leakage_mask[ni] & banned_leakage == 0
                        ):
                            result.append((ni, COST_REUSE))

            case (EntityType.ROAD, _):
                core_dist_sq = (cx - self._core_x) ** 2 + (cy - self._core_y) ** 2
                if core_dist_sq > CONV_CUTOFF_SQ:
                    for ddx, ddy in DIR4_DELTA:
                        nx, ny = cx + ddx, cy + ddy
                        if 0 <= nx < w and 0 <= ny < h:
                            ni = ny * w + nx
                            if (
                                not blocked[ni]
                                and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                                and leakage_mask[ni] & banned_leakage == 0
                            ):
                                result.append((ni, COST_ROAD_REPLACE))
                for ddx, ddy in BRIDGE_DELTAS:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if (
                            not blocked[ni]
                            and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                            and leakage_mask[ni] & banned_leakage == 0
                        ):
                            result.append((ni, COST_BRIDGE))

            case None | (EntityType.MARKER, _):
                core_dist_sq = (cx - self._core_x) ** 2 + (cy - self._core_y) ** 2
                if core_dist_sq > CONV_CUTOFF_SQ:
                    for ddx, ddy in DIR4_DELTA:
                        nx, ny = cx + ddx, cy + ddy
                        if 0 <= nx < w and 0 <= ny < h:
                            ni = ny * w + nx
                            if (
                                not blocked[ni]
                                and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                                and leakage_mask[ni] & banned_leakage == 0
                            ):
                                result.append((ni, COST_CONV))
                for ddx, ddy in BRIDGE_DELTAS:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if (
                            not blocked[ni]
                            and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                            and leakage_mask[ni] & banned_leakage == 0
                        ):
                            result.append((ni, COST_BRIDGE))

        if banned_leakage:
            for ni, c in result:
                if leakage_mask[ni] & banned_leakage != 0:
                    nx, ny = ni % w, ni // w
                    cx, cy = node % w, node // w
                    print(f"EDGE TO LEAKY: ({cx},{cy})->({nx},{ny}) leak={leakage_mask[ni]} banned={banned_leakage} cost={c} ent={entity[node]}")
        return result
