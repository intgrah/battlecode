from algorithms import Astar
from builder.state import State
from building import Bridge, Marker, Road
from building import Core as CoreBuilding
from cambc import Controller, Environment
from flow_astar import build_leakage_mask
from util import BRIDGE_DELTAS

COST_REUSE = 0
COST_BRIDGE = 10

_IMPASSABLE_ENV = frozenset(
    (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE),
)


class BridgeFlowAstar(Astar[int]):
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
        self._blocked = state.my_flow.blocked
        self._env = state.env
        self._building = state.building
        self._my_team = state.my_team
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
        x, y = node % self._w, node // self._w
        dx = abs(x - self._gx)
        dy = abs(y - self._gy)
        return max(dx, dy) // 3 * COST_BRIDGE

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
            case CoreBuilding():
                for ddx, ddy in BRIDGE_DELTAS:
                    nx, ny = cx + ddx, cy + ddy
                    if 0 <= nx < w and 0 <= ny < h:
                        ni = ny * w + nx
                        if not blocked[ni] and (
                            env[ni] is None or env[ni] not in _IMPASSABLE_ENV
                        ):
                            result.append((ni, 0))

            case Bridge(target=bt):
                bx, by = bt.x, bt.y
                if 0 <= bx < w and 0 <= by < h:
                    ni = by * w + bx
                    if (
                        not blocked[ni]
                        and (env[ni] is None or env[ni] not in _IMPASSABLE_ENV)
                        and leakage_mask[ni] & banned_leakage == 0
                    ):
                        result.append((ni, COST_REUSE))

            case None | Road() | Marker():
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

        return result
