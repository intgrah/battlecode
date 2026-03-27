from __future__ import annotations

from enum import Enum

from cambc import Controller, Direction, EntityType, Environment, Position


class Symmetry(Enum):
    ROTATIONAL = "rotational"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class BuilderState(Enum):
    BASE_BUILDER = "base_builder"
    HIBERNATE = "hibernate"
    ADVANCE = "advance"
    IDLE = "idle"
    ECONOMY = "economy"
    BRIDGE = "bridge"
    SUICIDE = "suicide"
    DESTROY_CONVEYOR = "destroy_conveyor"
    PROTECT = "protect"
    HEAL = "heal"


SYM_TYPES = tuple(Symmetry)
SYM_TO_IDX = {
    Symmetry.ROTATIONAL: 0,
    Symmetry.HORIZONTAL: 1,
    Symmetry.VERTICAL: 2,
    "unknown": 3,
}
IDX_TO_SYM: dict[int, Symmetry | str] = {v: k for k, v in SYM_TO_IDX.items()}

PHASE_SCOUTING = 0
PHASE_FOUND = 1

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

_COMMS_OFFSETS = [
    Position(dx, dy)
    for dx in range(-2, 3)
    for dy in range(-2, 3)
    if max(abs(dx), abs(dy)) == 2 and dx * dx + dy * dy <= 8
]


def king_dist(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def in_bounds(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def try_move_smart(
    ct: Controller,
    pos: Position,
    direction: Direction,
    destroy_standing: bool = False,
) -> bool:
    if direction == Direction.CENTRE:
        return True

    target = pos.add(direction)
    if not in_bounds(ct, target):
        return False
    if ct.get_tile_env(target) == Environment.WALL:
        return False
    if False:
        pos_bid = ct.get_tile_building_id(pos)
        if pos_bid is not None and ct.get_entity_type(pos_bid) == EntityType.ROAD:
            env = ct.get_tile_env(pos)
            if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                if ct.can_destroy(pos):
                    ct.destroy(pos)
    if ct.can_move(direction):
        ct.move(direction)
        return True
    if ct.can_build_road(target):
        ct.build_road(target)
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


def build_walkable(ct: Controller) -> set:
    walkable = set()
    my_team = ct.get_team()
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) == Environment.WALL:
            continue
        bid = ct.get_tile_building_id(tile)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            eteam = ct.get_team(bid)
            if etype in BLOCKED_BUILDINGS:
                continue
            if etype == EntityType.CORE and eteam != my_team:
                continue
            if (
                etype == EntityType.MARKER
                and eteam == my_team
                and not is_waypoint_marker(ct.get_marker_value(bid))
            ):
                continue
        walkable.add(tile)
    return walkable


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


def encode_comms(
    sym_name: Symmetry | str,
    phase: int,
    ex: int = 0,
    ey: int = 0,
    scout_idx: int = 0,
) -> int:
    sym = SYM_TO_IDX.get(sym_name, 3)
    return (min(scout_idx, 3) << 16) | (ey << 10) | (ex << 4) | (phase << 2) | sym


def decode_comms(value: int) -> tuple[Symmetry | str, int, int, int, int]:
    sym_idx = value & 0x3
    phase = (value >> 2) & 0x3
    ex = (value >> 4) & 0x3F
    ey = (value >> 10) & 0x3F
    scout_idx = (value >> 16) & 0x3
    return IDX_TO_SYM.get(sym_idx, "unknown"), phase, ex, ey, scout_idx


def is_waypoint_marker(value: int) -> bool:
    return bool(value & (1 << 31))


def comms_tiles(ct: Controller, core_pos: Position) -> list[Position]:
    result = []
    for o in _COMMS_OFFSETS:
        p = Position(core_pos.x + o.x, core_pos.y + o.y)
        if not in_bounds(ct, p):
            continue
        if not ct.is_in_vision(p):
            continue
        if ct.get_tile_env(p) == Environment.WALL:
            continue
        result.append(p)
    return result


def read_comms(
    ct: Controller,
    core_pos: Position,
) -> tuple[Symmetry | None, int, Position | None, int]:
    my_team = ct.get_team()
    best_phase = -1
    best: tuple[Symmetry | None, int, Position | None, int] = (None, -1, None, 0)
    for tile in comms_tiles(ct, core_pos):
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != my_team:
            continue
        val = ct.get_marker_value(bid)
        if is_waypoint_marker(val):
            continue
        sym, phase, ex, ey, scout_idx = decode_comms(val)
        if phase > best_phase:
            best_phase = phase
            if isinstance(sym, Symmetry):
                epos = Position(ex, ey)
                best = (sym, phase, epos, scout_idx)
            else:
                best = (None, phase, None, scout_idx)
    return best


def place_comms(ct: Controller, core_pos: Position, value: int) -> bool:
    tiles = comms_tiles(ct, core_pos)

    for tile in tiles:
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) == EntityType.MARKER and ct.can_place_marker(tile):
            print(f"maker at {tile} w/ {value}")
            ct.place_marker(tile, value)
            return True

    for tile in tiles:
        if ct.can_place_marker(tile):
            print(f"empty at {tile} w/ {value}")
            ct.place_marker(tile, value)
            return True

    for tile in tiles:
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) == EntityType.ROAD and ct.can_destroy(tile):
            ct.destroy(tile)
            if ct.can_place_marker(tile):
                print(f"road at {tile} w/ {value}")
                ct.place_marker(tile, value)
                return True

    return False
