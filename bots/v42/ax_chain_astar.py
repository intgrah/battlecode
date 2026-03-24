from flow_astar import RAX, TI, FlowAstar
from map_belief import MapBelief


class AxChainAstar(FlowAstar):
    def __init__(
        self,
        belief: MapBelief,
        sx: int,
        sy: int,
        goal_tiles: set[int],
    ) -> None:
        w = belief.w
        self._goal_positions = [(i % w, i // w) for i in goal_tiles]
        super().__init__(belief, sx, sy, goal_tiles, TI | RAX)

    def heuristic(self, node: int) -> int:
        x, y = node % self._w, node // self._w
        return (
            min(abs(x - gx) + abs(y - gy) for gx, gy in self._goal_positions)
            if self._goal_positions
            else 0
        )
