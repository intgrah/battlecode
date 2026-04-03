from algorithms import Astar
from builder.state import State
from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
    BuildingFoundry,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Environment
from util import BRIDGE_DELTAS, DIR4_DELTA

COST_REUSE = 0
COST_CONV = 3
COST_BRIDGE = 30
COST_ROAD_REPLACE = 3

_IMPASSABLE_ENV = frozenset(
    (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE),
)

TI = 0b001
AX = 0b010
RAX = 0b100


def build_leakage_mask(state: State) -> list[int]:
    w, h = state.w, state.h
    n = w * h
    mask = [0] * n
    for i in range(n):
        bld = state.building[i]
        if bld is None:
            continue
        if bld.team != state.my_team:
            continue
        match bld:
            case BuildingFoundry():
                ix, iy = i % w, i // w
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = ix + ddx, iy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        mask[ny * w + nx] |= RAX
            case BuildingSplitter(direction=d):
                ix, iy = i % w, i // w
                dx, dy = d.delta()
                commodity = 0
                f = state.flow
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
        e = state.env[i]
        match e:
            case Environment.ORE_TITANIUM:
                commodity = TI
            case Environment.ORE_AXIONITE:
                commodity = AX
            case _:
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
        state: State,
        sx: int,
        sy: int,
        goals: set[int],
        banned_leakage: int,
    ) -> None:
        self._w = state.w
        self._h = state.h
        self._gx = state.my_core.x
        self._gy = state.my_core.y
        self._banned_leakage = banned_leakage
        self._leakage_mask = build_leakage_mask(state)
        self._blocked = state.flow.blocked
        self._env = state.env
        self._building = state.building
        self._my_team = state.my_team
        self._core_x = state.my_core.x
        self._core_y = state.my_core.y
        self._nav_dist = state.nav_dist
        si = sy * self._w + sx
        super().__init__(si, goals)

    def _is_buildable(self, ni: int) -> bool:
        w, h = self._w, self._h
        nav_dist = self._nav_dist
        if nav_dist[ni] != -1:
            return True
        nx, ny = ni % w, ni // w
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                ax, ay = nx + dx, ny + dy
                if 0 <= ax < w and 0 <= ay < h and nav_dist[ay * w + ax] != -1:
                    return True
        return False

    def heuristic(self, node: int) -> int:
        return abs(node % self._w - self._gx) + abs(node // self._w - self._gy)

    def get_neighbors(self, node: int) -> list[tuple[int, int]]:
        w, h = self._w, self._h
        blocked = self._blocked
        env = self._env
        building = self._building
        leakage_mask = self._leakage_mask
        banned_leakage = self._banned_leakage

        if blocked[node]:
            return []
        e = env[node]
        if e is not None and e in _IMPASSABLE_ENV:
            return []
        bld = building[node]
        if bld is not None and bld.team != self._my_team:
            return []
        if leakage_mask[node] & banned_leakage != 0:
            return []

        cx, cy = node % w, node // w
        result: list[tuple[int, int]] = []

        match bld:
            case BuildingCore():
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if not blocked[ni] and (
                            env[ni] is None or env[ni] not in _IMPASSABLE_ENV
                        ):
                            result.append((ni, 0))

            case BuildingBridge(target=bt):
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
                BuildingConveyor(direction=d)
                | BuildingArmouredConveyor(direction=d)
                | BuildingSplitter(direction=d)
            ):
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

            case BuildingRoad():
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if (
                            not blocked[ni]
                            and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                            and leakage_mask[ni] & banned_leakage == 0
                            and self._is_buildable(ni)
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
                            and self._is_buildable(ni)
                        ):
                            result.append((ni, COST_BRIDGE))

            case None | BuildingMarker():
                for ddx, ddy in DIR4_DELTA:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if (
                            not blocked[ni]
                            and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                            and leakage_mask[ni] & banned_leakage == 0
                            and self._is_buildable(ni)
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
                            and self._is_buildable(ni)
                        ):
                            result.append((ni, COST_BRIDGE))

        return result
