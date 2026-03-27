from builder.state import State
from cambc import EntityType, Position
from flow_astar import COST_REUSE, RAX, TI, FlowAstar


class AxChainAstar(FlowAstar):
    def __init__(
        self,
        state: State,
        sx: int,
        sy: int,
        goal_tiles: set[int],
    ) -> None:
        w = state.w
        self._goal_positions = [(i % w, i // w) for i in goal_tiles]
        super().__init__(state, sx, sy, goal_tiles, TI | RAX)

    def heuristic(self, node: int) -> int:
        x, y = node % self._w, node // self._w
        return (
            min(abs(x - gx) + abs(y - gy) for gx, gy in self._goal_positions)
            if self._goal_positions
            else 0
        )

    def get_neighbors(self, node: int) -> list[tuple[int, int]]:
        result = super().get_neighbors(node)
        ent = self._entity[node]
        if ent is not None and ent[0] in (
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
            EntityType.BRIDGE,
        ):
            banned = self._banned_leakage
            mask = self._leakage_mask
            result = [
                (ni, c) for ni, c in result if c != COST_REUSE or mask[ni] & banned == 0
            ]
        return result
