from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, Direction, EntityType, Environment, Position
from pathfinding import _ALL_DIRS, _DIR_IDX, bug2_step


class Symmetry(Enum):
    ROTATIONAL = "rotational"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class BuilderMode(Enum):
    ADVANCE = "advance"
    RETURN = "return"
    SECURE = "secure"
    BRIDGE = "bridge"
    HEAL = "heal"
    PROTECT = "protect"


SYM_TYPES = tuple(Symmetry)

BLOCKED_BUILDINGS = frozenset(
    {
        EntityType.GUNNER,
        EntityType.SENTINEL,
        EntityType.BREACH,
        EntityType.LAUNCHER,
        EntityType.HARVESTER,
        EntityType.FOUNDRY,
        EntityType.BARRIER,
    },
)


def king_dist(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def in_bounds(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def try_move_smart(ct: Controller, pos: Position, direction: Direction) -> bool:
    if direction == Direction.CENTRE:
        return True

    target = pos.add(direction)
    if not in_bounds(ct, target):
        return False

    if ct.can_move(direction):
        ct.move(direction)
        return True
    if ct.can_build_road(target):
        ct.build_road(target)
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


def build_walkable(ct: Controller) -> set[Position]:
    walkable: set[Position] = set()
    my_team = ct.get_team()
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) == Environment.WALL:
            continue
        if ct.get_tile_builder_bot_id(tile) is not None:
            continue
        bid = ct.get_tile_building_id(tile)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            eteam = ct.get_team(bid)
            if etype in BLOCKED_BUILDINGS:
                continue
            if etype == EntityType.CORE and eteam != my_team:
                continue

        walkable.add(tile)

    for bid in ct.get_nearby_buildings():
        if (
            ct.get_entity_type(bid) != EntityType.LAUNCHER
            or ct.get_team(bid) == my_team
        ):
            continue
        lp = ct.get_position(bid)
        for d in _ALL_DIRS:
            walkable.discard(lp.add(d))

    walkable.add(ct.get_position())
    return walkable


def pf_move(player: Player, ct: Controller, target: Position) -> None:
    current = ct.get_position()

    if target is None:
        return

    player.pos_history.append(current)
    if len(player.pos_history) > 5:
        player.pos_history.pop(0)

    stuck = any(
        len(player.pos_history) > i and player.pos_history[-1 - i] == current
        for i in range(2, 5)
    )

    if stuck:
        player.stuck_count += 1
    else:
        player.stuck_count = 0

    if player.stuck_count >= 16:
        goal_dir = current.direction_to(target)
        if goal_dir not in _DIR_IDX:
            return
        gi = _DIR_IDX[goal_dir]
        visited = set(player.pos_history)
        for offset in [0, 1, -1, 2, -2, 3, -3, 4]:
            d = _ALL_DIRS[(gi + offset) % 8]
            if current.add(d) not in visited and try_move_smart(ct, current, d):
                player.pos_history = []
                return
        for offset in [0, 1, -1, 2, -2, 3, -3, 4]:
            d = _ALL_DIRS[(gi + offset) % 8]
            if try_move_smart(ct, current, d):
                player.pos_history = []
                return
        return

    if target != player.agent.goal:
        player.agent.retarget(current, target)

    player.walkable = build_walkable(ct)
    next_pos = bug2_step(player.agent, current, player.walkable)
    if try_move_smart(ct, current, current.direction_to(next_pos)):
        player.agent.current = next_pos

    ct.draw_indicator_line(player.agent.current, player.agent.goal, 255, 255, 0)


def get_symmetry_candidates(
    core: Position,
    w: int,
    h: int,
) -> dict[Symmetry, Position]:
    cx, cy = core.x, core.y
    return {
        Symmetry.ROTATIONAL: Position(w - 1 - cx, h - 1 - cy),
        Symmetry.HORIZONTAL: Position(w - 1 - cx, cy),
        Symmetry.VERTICAL: Position(cx, h - 1 - cy),
    }


def mirror_pos(pos: Position, sym: Symmetry, w: int, h: int) -> Position:
    x, y = pos.x, pos.y
    match sym:
        case Symmetry.ROTATIONAL:
            return Position(w - 1 - x, h - 1 - y)
        case Symmetry.HORIZONTAL:
            return Position(w - 1 - x, y)
        case Symmetry.VERTICAL:
            return Position(x, h - 1 - y)
