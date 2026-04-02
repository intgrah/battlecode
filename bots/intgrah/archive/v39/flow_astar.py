from astar import Astar
from cambc import EntityType, Environment
from map_belief import _TRANSPORT, MapBelief

WALK_4 = [(0, -1), (1, 0), (0, 1), (-1, 0)]

BRIDGE_DELTAS = [
    (dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 2 < dx * dx + dy * dy <= 9
]

COST_REUSE = 0
COST_CONV = 3
COST_BRIDGE = 10
COST_ROAD_REPLACE = 3

_IMPASSABLE_ENV = frozenset(
    (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE),
)


class FlowAstar(Astar):
    def __init__(
        self,
        belief: MapBelief,
        sx: int,
        sy: int,
        core_x: int,
        core_y: int,
    ) -> None:
        self.belief = belief
        self.core_x = core_x
        self.core_y = core_y
        self.core_set: set[int] = set()
        w, h = belief.w, belief.h
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                cx, cy = core_x + dx, core_y + dy
                if 0 <= cx < w and 0 <= cy < h:
                    self.core_set.add(cy * w + cx)
        super().__init__(w, h, sx, sy)

    def is_goal(self, x: int, y: int) -> bool:
        return y * self.w + x in self.core_set

    def get_neighbors(self, cx: int, cy: int) -> list[tuple[int, int, int]]:
        b = self.belief
        w, h = b.w, b.h
        ci = cy * w + cx
        blocked = b.blocked
        env = b.env
        if blocked[ci]:
            return []
        e = env[ci]
        if e is not None and e in _IMPASSABLE_ENV:
            return []
        ent = b.entity[ci]
        if ent is not None and ent[1] != b.my_team:
            return []

        def passable(nx: int, ny: int) -> bool:
            if not (0 <= nx < w and 0 <= ny < h):
                return False
            ni = ny * w + nx
            if blocked[ni]:
                return False
            ne = env[ni]
            return ne is None or ne not in _IMPASSABLE_ENV

        result: list[tuple[int, int, int]] = []

        if ent is not None and ent[0] != EntityType.MARKER:
            etype = ent[0]

            if etype == EntityType.CORE:
                for ddx, ddy in WALK_4:
                    nx, ny = cx + ddx, cy + ddy
                    if passable(nx, ny):
                        result.append((nx, ny, 0))

            elif etype in _TRANSPORT:
                d = b.direction[ci]
                bt = b.bridge_target[ci]
                if etype == EntityType.BRIDGE and bt is not None:
                    bx, by = bt
                    if passable(bx, by):
                        result.append((bx, by, COST_REUSE))
                elif d is not None:
                    ddx, ddy = d.delta()
                    nx, ny = cx + ddx, cy + ddy
                    if passable(nx, ny):
                        result.append((nx, ny, COST_REUSE))

            elif etype == EntityType.ROAD:
                for ddx, ddy in WALK_4:
                    nx, ny = cx + ddx, cy + ddy
                    if passable(nx, ny):
                        result.append((nx, ny, COST_ROAD_REPLACE))
                for ddx, ddy in BRIDGE_DELTAS:
                    nx, ny = cx + ddx, cy + ddy
                    if passable(nx, ny):
                        result.append((nx, ny, COST_BRIDGE))

        else:
            for ddx, ddy in WALK_4:
                nx, ny = cx + ddx, cy + ddy
                if passable(nx, ny):
                    result.append((nx, ny, COST_CONV))
            for ddx, ddy in BRIDGE_DELTAS:
                nx, ny = cx + ddx, cy + ddy
                if passable(nx, ny):
                    result.append((nx, ny, COST_BRIDGE))

        return result

    def heuristic(self, x: int, y: int) -> int:
        return abs(x - self.core_x) + abs(y - self.core_y)


def flow_astar(
    belief: MapBelief,
    sx: int,
    sy: int,
    core_x: int,
    core_y: int,
) -> FlowAstar:
    return FlowAstar(belief, sx, sy, core_x, core_y)
