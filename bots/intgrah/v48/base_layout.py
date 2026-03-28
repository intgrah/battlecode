from building import (
    BuildingBarrier,
    BuildingBridge,
    BuildingGunner,
    BuildingLauncher,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Direction, Position, Team

type BuildSpec = tuple[
    Position,
    BuildingBarrier
    | BuildingBridge
    | BuildingGunner
    | BuildingLauncher
    | BuildingRoad
    | BuildingSplitter,
]


def base_layout(core: Position, team: Team) -> list[BuildSpec]:
    cx, cy = core.x, core.y

    def p(dx: int, dy: int) -> Position:
        return Position(cx + dx, cy + dy)

    return [
        (p(-3, -1), BuildingBarrier(team)),
        (p(-3, 0), BuildingBarrier(team)),
        (p(-3, 1), BuildingBarrier(team)),
        (p(-2, -1), BuildingGunner(team, Direction.SOUTH)),
        (p(-2, 0), BuildingRoad(team)),
        (p(-2, 1), BuildingBarrier(team)),
        (p(-2, -2), BuildingSplitter(team, Direction.EAST)),
        (p(-2, -3), BuildingBridge(team, p(-1, -1))),
        (p(-1, -2), BuildingGunner(team, Direction.EAST)),
        (p(-1, -3), BuildingLauncher(team)),
        (p(-1, 2), BuildingBarrier(team)),
        (p(-1, 3), BuildingBarrier(team)),
        (p(0, -2), BuildingRoad(team)),
        (p(0, -3), BuildingBarrier(team)),
        (p(0, 2), BuildingRoad(team)),
        (p(0, 3), BuildingBarrier(team)),
        (p(1, -2), BuildingBarrier(team)),
        (p(1, -3), BuildingBarrier(team)),
        (p(1, 2), BuildingGunner(team, Direction.WEST)),
        (p(1, 3), BuildingBarrier(team)),
        (p(2, -1), BuildingBarrier(team)),
        (p(2, 0), BuildingRoad(team)),
        (p(2, 1), BuildingGunner(team, Direction.NORTH)),
        (p(2, 2), BuildingSplitter(team, Direction.NORTH)),
        (p(3, -1), BuildingBarrier(team)),
        (p(3, 0), BuildingBarrier(team)),
        (p(3, 1), BuildingLauncher(team)),
        (p(3, 2), BuildingBridge(team, p(1, 1))),
    ]


EXECUTION_CELLS_OFFSETS: list[tuple[int, int]] = [
    (-2, 0),
    (0, -2),
    (2, 0),
    (0, 2),
]


SPLITTER_OFFSETS: list[tuple[int, int]] = [
    (-2, -2),
    (2, 2),
]


def execution_cells(core: Position) -> list[Position]:
    return [Position(core.x + dx, core.y + dy) for dx, dy in EXECUTION_CELLS_OFFSETS]


def splitter_tiles(core: Position) -> list[Position]:
    return [Position(core.x + dx, core.y + dy) for dx, dy in SPLITTER_OFFSETS]
