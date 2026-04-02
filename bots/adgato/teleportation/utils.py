"""Shared constants, helpers, symmetry, marker protocol, and comms for v5."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, Direction, EntityType, Environment, Position
from pathfinding import bug2_step

# ── Constants ─────────────────────────────────────────────────────────

SYM_TYPES = ["rotational", "horizontal", "vertical"]
SYM_TO_IDX = {"rotational": 0, "horizontal": 1, "vertical": 2, "unknown": 3}
IDX_TO_SYM = {v: k for k, v in SYM_TO_IDX.items()}

PHASE_SCOUTING = 0
PHASE_FOUND = 1
PHASE_ASSAULT_READY = 2
PHASE_BLOCKED = 3

# Buildings that permanently block movement (can't walk on or build over)
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

# Tiles adjacent to core (outside 3x3, within action r²=8 from centre)
_COMMS_OFFSETS = [
    Position(dx, dy)
    for dx in range(-2, 3)
    for dy in range(-2, 3)
    if max(abs(dx), abs(dy)) == 2  # ring just outside the 3x3
    and dx * dx + dy * dy <= 8  # within core action radius
]


# ── Helpers ───────────────────────────────────────────────────────────


def king_dist(a: Position, b: Position) -> int:
    """Chebyshev (king-move) distance between two positions."""
    return max(abs(a.x - b.x), abs(a.y - b.y))


def in_bounds(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def try_move_smart(ct: Controller, pos: Position, direction: Direction) -> bool:
    """Move in direction. Uses existing walkable tile if possible, else builds road."""
    if direction == Direction.CENTRE:
        return True

    target = pos.add(direction)
    if not in_bounds(ct, target):
        return False

    # Already walkable (enemy/friendly conveyor, road, allied core)
    if ct.can_move(direction):
        ct.move(direction)
        return True
    # Build road if action available
    if ct.can_build_road(target):
        ct.build_road(target)
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


def build_walkable(ct: Controller) -> set:
    """Build walkable set from visible tiles. Includes empty tiles
    (where roads can be built) and tiles with walkable buildings.
    """
    walkable = set()
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

    # Mark tiles adjacent to enemy launchers as unwalkable
    # for bid in ct.get_nearby_buildings():
    #    if ct.get_entity_type(bid) != EntityType.LAUNCHER or ct.get_team(bid) == my_team:
    #        continue
    #    lp = ct.get_position(bid)
    #    for d in _ALL_DIRS:
    #        walkable.discard(lp.add(d))

    walkable.add(ct.get_position())
    return walkable


def pf_move(player: Player, ct: Controller, target: Position) -> None:

    current = ct.get_position()

    if target is None:
        return

    if target != player.agent.goal:
        player.agent.retarget(current, target)

    player.walkable = build_walkable(ct)
    next_pos = bug2_step(player.agent, current, player.walkable)
    if try_move_smart(ct, current, current.direction_to(next_pos)):
        player.agent.current = next_pos

    ct.draw_indicator_line(player.agent.current, player.agent.goal, 255, 255, 0)


# ── Symmetry ──────────────────────────────────────────────────────────


def get_symmetry_candidates(core: Position, w: int, h: int) -> dict[str, Position]:
    cx, cy = core.x, core.y
    return {
        "rotational": Position(w - 1 - cx, h - 1 - cy),
        "horizontal": Position(w - 1 - cx, cy),
        "vertical": Position(cx, h - 1 - cy),
    }


def mirror_pos(pos: Position, sym: str, w: int, h: int) -> Position:
    x, y = pos.x, pos.y
    if sym == "rotational":
        return Position(w - 1 - x, h - 1 - y)
    if sym == "horizontal":
        return Position(w - 1 - x, y)
    return Position(x, h - 1 - y)


# ── Marker protocol ──────────────────────────────────────────────────
#
# COMMS marker (near own core):
#   Bits 0-1:   symmetry (0=rot, 1=horiz, 2=vert, 3=unknown)
#   Bits 2-3:   phase (0=scouting, 1=found, 2=assault_ready, 3=blocked)
#   Bits 4-9:   enemy core x
#   Bits 10-15: enemy core y
#   Bits 16-17: next scout index (0-2, used by newly spawned builders)
#
# WAYPOINT marker (adjacent to launcher):
#   Bit  31:    1 (distinguishes from comms marker, which has bit 31 = 0)
#   Bits 0-5:   team core x
#   Bits 6-11:  team core y
#   Bits 12-17: enemy core x
#   Bits 18-23: enemy core y


def encode_comms(
    sym_name: str,
    phase: int,
    ex: int = 0,
    ey: int = 0,
    scout_idx: int = 0,
) -> int:
    sym = SYM_TO_IDX.get(sym_name, 3)
    return (min(scout_idx, 3) << 16) | (ey << 10) | (ex << 4) | (phase << 2) | sym


def decode_comms(value: int) -> tuple[str, int, int, int, int]:
    sym_idx = value & 0x3
    phase = (value >> 2) & 0x3
    ex = (value >> 4) & 0x3F
    ey = (value >> 10) & 0x3F
    scout_idx = (value >> 16) & 0x3
    return IDX_TO_SYM.get(sym_idx, "unknown"), phase, ex, ey, scout_idx


def encode_waypoint(team_x: int, team_y: int, enemy_x: int, enemy_y: int) -> int:
    return (1 << 31) | (enemy_y << 18) | (enemy_x << 12) | (team_y << 6) | team_x


def decode_waypoint(value: int) -> tuple[int, int, int, int]:
    tx = value & 0x3F
    ty = (value >> 6) & 0x3F
    ex = (value >> 12) & 0x3F
    ey = (value >> 18) & 0x3F
    return tx, ty, ex, ey


def is_waypoint_marker(value: int) -> bool:
    return bool(value & (1 << 31))


# ── Comms helpers ─────────────────────────────────────────────────────


def comms_tiles(ct: Controller, core_pos: Position) -> list[Position]:
    """Return candidate comms tile positions adjacent to core (in vision only)."""
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
) -> tuple[str | None, int, Position | None, int]:
    """Read best comms marker near core.
    Returns (sym, phase, enemy_pos, scout_idx). sym is None if nothing found.
    """
    my_team = ct.get_team()
    best_phase = -1
    best = (None, -1, None, 0)
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
            epos = Position(ex, ey) if sym != "unknown" else None
            best = (sym if sym != "unknown" else None, phase, epos, scout_idx)
    return best


def place_comms(ct: Controller, core_pos: Position, value: int) -> bool:
    """Place a comms marker adjacent to core.
    Strategy: merge with existing friendly comms marker > free tile > destroy road and place.
    """
    tiles = comms_tiles(ct, core_pos)

    # 1. Try to overwrite an existing friendly comms marker
    for tile in tiles:
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) == EntityType.MARKER and ct.can_place_marker(tile):
            print(f"maker at {tile} w/ {value}")
            ct.place_marker(tile, value)
            return True

    # 2. Try a tile with no building
    for tile in tiles:
        if ct.can_place_marker(tile):
            print(f"empty at {tile} w/ {value}")
            ct.place_marker(tile, value)
            return True

    # 3. Destroy a friendly road and place
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
