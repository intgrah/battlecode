"""v4 bot - symmetry-based enemy core detection with marker flooding.

Strategy:
  - Core: spawns builders assigned to sectors (same as v3 for economy).
  - Builders: explore and build harvesters with conveyor chains (v3 base),
    but ALSO detect enemy core location via map symmetry.
  - Symmetry detection: The map is guaranteed symmetric (rotational, horizontal,
    or vertical). Given our core position, there are 3 candidate enemy core
    positions. Builders eliminate candidates via environment mismatches and
    direct vision of candidate tiles.
  - When a builder resolves the enemy core, it enters "broadcast" phase:
    retraces its steps to own core, placing a marker every step encoding
    the symmetry type. Any other builder that sees one of these markers
    instantly learns the enemy core location.

Marker protocol for symmetry type:
  Bit 31 (0x80000000): flag indicating this is a symmetry marker
  Bits 0-1: symmetry type index (0=rotational, 1=horizontal, 2=vertical)
  Only 2 bits needed since there are only 3 possible symmetry types.
"""

from enum import Enum

from cambc import Controller, Direction, EntityType, Environment, Position


class Phase(Enum):
    EXPLORE = "explore"
    LAY_CONVEYORS = "lay_conveyors"
    BROADCAST = "broadcast"


class Symmetry(Enum):
    ROTATIONAL = "rotational"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


CARDINAL = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
ALL_DIRS = [d for d in Direction if d != Direction.CENTRE]

SECTOR_DIRS = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
]

SYM_NAMES: tuple[Symmetry, ...] = (
    Symmetry.ROTATIONAL,
    Symmetry.HORIZONTAL,
    Symmetry.VERTICAL,
)
SYM_INDEX: dict[Symmetry, int] = {sym: i for i, sym in enumerate(SYM_NAMES)}
SYM_UNKNOWN = 3

# Offsets from core centre for candidate comms tiles (outside 3x3, within action r^2=8)
COMMS_OFFSETS = [(0, -2), (2, 0), (0, 2), (-2, 0), (-2, -2), (2, -2), (2, 2), (-2, 2)]


# ── Helpers ───────────────────────────────────────────────────────────


def in_bounds(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def snap_cardinal(d: Direction) -> Direction:
    return {
        Direction.NORTH: Direction.NORTH,
        Direction.SOUTH: Direction.SOUTH,
        Direction.EAST: Direction.EAST,
        Direction.WEST: Direction.WEST,
        Direction.NORTHEAST: Direction.EAST,
        Direction.NORTHWEST: Direction.NORTH,
        Direction.SOUTHEAST: Direction.SOUTH,
        Direction.SOUTHWEST: Direction.WEST,
        Direction.CENTRE: Direction.NORTH,
    }[d]


def cardinal_toward(src: Position, dst: Position) -> Direction:
    dx = dst.x - src.x
    dy = dst.y - src.y
    if abs(dx) >= abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    return Direction.SOUTH if dy > 0 else Direction.NORTH


def cardinal_priority(preferred: Direction) -> list[Direction]:
    opp = preferred.opposite()
    perps = [d for d in CARDINAL if d not in (preferred, opp)]
    return [preferred, *perps, opp]


def try_move(
    ct: Controller,
    pos: Position,
    direction: Direction,
    build_road: bool = True,
    reserved: Position | None = None,
) -> bool:
    target = pos.add(direction)
    if not in_bounds(ct, target):
        return False
    if (
        build_road
        and target != reserved
        and ct.get_action_cooldown() == 0
        and ct.can_build_road(target)
    ):
        ct.build_road(target)
    if ct.can_move(direction):
        ct.move(direction)
        return True
    return False


def try_move_toward(
    ct: Controller,
    pos: Position,
    target: Position,
    reserved: Position | None = None,
) -> bool:
    if ct.get_move_cooldown() > 0:
        return False
    for d in cardinal_priority(cardinal_toward(pos, target)):
        if try_move(ct, pos, d, reserved=reserved):
            return True
    return False


def find_nearest_ore(ct: Controller, pos: Position) -> Position | None:
    best, best_dist = None, 999999
    for tile in ct.get_nearby_tiles():
        env = ct.get_tile_env(tile)
        if (
            env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE)
            and ct.get_tile_building_id(tile) is None
        ):
            d = pos.distance_squared(tile)
            if d < best_dist:
                best_dist = d
                best = tile
    return best


def find_core(ct: Controller) -> Position | None:
    my_team = ct.get_team()
    for eid in ct.get_nearby_buildings():
        if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == my_team:
            return ct.get_position(eid)
    return None


def is_on_core(pos: Position, core_pos: Position) -> bool:
    return abs(pos.x - core_pos.x) <= 1 and abs(pos.y - core_pos.y) <= 1


CONVEYOR_TYPES = {
    EntityType.CONVEYOR,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
}


def tile_has_friendly_conveyor(ct: Controller, pos: Position) -> bool:
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return False
    if ct.get_team(bid) != ct.get_team():
        return False
    return ct.get_entity_type(bid) in CONVEYOR_TYPES


def can_feed_into(ct: Controller, from_pos: Position, conv_pos: Position) -> bool:
    bid = ct.get_tile_building_id(conv_pos)
    if bid is None:
        return False
    try:
        facing = ct.get_direction(bid)
    except Exception:
        return False
    feed_dir = cardinal_toward(conv_pos, from_pos)
    return feed_dir != facing


def clean_path(path: list[Position]) -> list[Position]:
    last_seen: dict[Position, int] = {}
    for i, p in enumerate(path):
        last_seen[p] = i
    result = []
    i = 0
    while i < len(path):
        p = path[i]
        result.append(p)
        i = last_seen[p] + 1
    return result


# ── Symmetry helpers ─────────────────────────────────────────────────


def get_symmetry_candidates(core: Position, w: int, h: int) -> dict[Symmetry, Position]:
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


def encode_symmetry(sym: Symmetry) -> int:
    return SYM_INDEX[sym]


def decode_symmetry(value: int) -> Symmetry | None:
    idx = value & 0x3
    if idx < len(SYM_NAMES):
        return SYM_NAMES[idx]
    return None


def resolve_enemy_core(core_pos: Position, sym: Symmetry, w: int, h: int) -> Position:
    return mirror_pos(core_pos, sym, w, h)


def get_comms_candidates(ct: Controller, core_pos: Position) -> list[Position]:
    """Return valid comms tile candidates around a core position."""
    cx, cy = core_pos.x, core_pos.y
    result = []
    for dx, dy in COMMS_OFFSETS:
        p = Position(cx + dx, cy + dy)
        if in_bounds(ct, p) and ct.get_tile_env(p) != Environment.WALL:
            result.append(p)
    return result


def read_comms_marker(ct: Controller, marker_pos: Position) -> Symmetry | None:
    bid = ct.get_tile_building_id(marker_pos)
    if bid is None:
        return None
    if ct.get_entity_type(bid) != EntityType.MARKER:
        return None
    if ct.get_team(bid) != ct.get_team():
        return None
    return decode_symmetry(ct.get_marker_value(bid))


# ── Player ────────────────────────────────────────────────────────────


class Player:
    def __init__(self) -> None:
        self.spawned = 0
        self.core_pos: Position | None = None
        self.comms_tile: Position | None = None  # current comms marker tile
        self.comms_candidates: list[Position] = []  # all valid comms tile candidates
        self.comms_idx = 0  # index into comms_candidates
        self.phase: Phase = Phase.EXPLORE
        self.sector: Direction | None = None
        self.path: list[Position] = []
        self.return_path: list[Position] = []
        self.return_idx = 0
        self.stuck_turns = 0
        self.harvester_dir: Direction = Direction.NORTH
        self.visited: set[Position] = set()
        self.explore_stale = 0

        # Symmetry detection state
        self.sym_candidates: dict[Symmetry, Position] | None = None
        self.sym_eliminated: set[Symmetry] = set()
        self.sym_resolved: Symmetry | None = None
        self.enemy_core: Position | None = None
        self.known_env: dict[Position, Environment] = {}
        self.learned_from_marker = (
            False  # True if we learned from a marker (no need to broadcast)
        )
        self.has_broadcast = False  # True once we've successfully broadcast

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    # ── Core ──────────────────────────────────────────────────────────

    def _run_core(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        pos = ct.get_position()
        w = ct.get_map_width()
        h = ct.get_map_height()

        if rnd % 200 == 1:
            ti, ax = ct.get_global_resources()
            print(
                f"R{rnd} Ti:{ti} Ax:{ax} spawned:{self.spawned} scale:{ct.get_scale_percent():.0f}%",
            )

        # Build comms candidate list once
        if not self.comms_candidates:
            self.comms_candidates = get_comms_candidates(ct, pos)
            if self.comms_candidates:
                self.comms_tile = self.comms_candidates[0]
                self.comms_idx = 0

        # Check if current comms tile was destroyed/overwritten by enemy
        if self.comms_tile is not None:
            bid = ct.get_tile_building_id(self.comms_tile)
            if bid is not None:
                is_our_marker = (
                    ct.get_entity_type(bid) == EntityType.MARKER
                    and ct.get_team(bid) == ct.get_team()
                )
                if not is_our_marker:
                    # Enemy built something over our marker — pick next candidate
                    self.comms_idx += 1
                    if self.comms_idx < len(self.comms_candidates):
                        self.comms_tile = self.comms_candidates[self.comms_idx]
                    else:
                        self.comms_tile = None  # no more candidates

        # Read comms marker — a builder may have written to any candidate tile
        if self.sym_resolved is None:
            for candidate in self.comms_candidates:
                sym = read_comms_marker(ct, candidate)
                if sym is not None:
                    self.sym_resolved = sym
                    self.enemy_core = resolve_enemy_core(pos, sym, w, h)
                    print(
                        f"Core learned: enemy at ({self.enemy_core.x},{self.enemy_core.y}) [{sym.value}]",
                    )
                    break

        # Core symmetry detection via environment mismatch (vision r^2=36)
        if self.sym_resolved is None:
            if self.sym_candidates is None:
                self.sym_candidates = get_symmetry_candidates(pos, w, h)
                for s, epos in self.sym_candidates.items():
                    if epos == pos:
                        self.sym_eliminated.add(s)
            for tile in ct.get_nearby_tiles():
                if tile not in self.known_env:
                    env = ct.get_tile_env(tile)
                    self.known_env[tile] = env
                    for s in list(self.sym_candidates):
                        if s in self.sym_eliminated:
                            continue
                        mirrored = mirror_pos(tile, s, w, h)
                        if (
                            mirrored in self.known_env
                            and self.known_env[mirrored] != env
                        ):
                            self.sym_eliminated.add(s)
            remaining = [s for s in self.sym_candidates if s not in self.sym_eliminated]
            if len(remaining) == 1:
                self.sym_resolved = remaining[0]
                self.enemy_core = self.sym_candidates[remaining[0]]
                print(
                    f"Core detected: enemy at ({self.enemy_core.x},{self.enemy_core.y}) [{self.sym_resolved.value}]",
                )
            elif len(remaining) > 1:
                positions = {self.sym_candidates[s] for s in remaining}
                if len(positions) == 1:
                    self.sym_resolved = remaining[0]
                    self.enemy_core = positions.pop()
                    print(
                        f"Core detected: enemy at ({self.enemy_core.x},{self.enemy_core.y}) [{self.sym_resolved.value}]",
                    )

        if self.comms_tile is not None and self.sym_resolved is not None:
            value = encode_symmetry(self.sym_resolved)
            if ct.can_place_marker(self.comms_tile):
                ct.place_marker(self.comms_tile, value)

        max_spawned = min(2 + rnd // 100, 8)
        if self.spawned >= max_spawned:
            return

        candidates = []
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    candidates.append(p)
        if candidates:
            sector = SECTOR_DIRS[self.spawned % len(SECTOR_DIRS)]
            sdx, sdy = sector.delta()
            candidates.sort(key=lambda p: -(p.x * sdx + p.y * sdy))
            ct.spawn_builder(candidates[0])
            self.spawned += 1

    # ── Builder ───────────────────────────────────────────────────────

    def _find_comms_tile(self, ct: Controller) -> None:
        """Locate the team's comms marker tile by scanning candidates.
        Prefers a tile that already has our team's marker; falls back to first candidate.
        """
        if self.core_pos is None:
            return
        if not self.comms_candidates:
            self.comms_candidates = get_comms_candidates(ct, self.core_pos)
        # Check all candidates for an existing friendly marker
        for candidate in self.comms_candidates:
            if ct.is_in_vision(candidate):
                sym = read_comms_marker(ct, candidate)
                if sym is not None:
                    self.comms_tile = candidate
                    return
        # No marker found yet — use first candidate (matches core's initial choice)
        if self.comms_tile is None and self.comms_candidates:
            self.comms_tile = self.comms_candidates[0]

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if self.core_pos is None:
            self.core_pos = find_core(ct)
        if self.core_pos is not None:
            self._find_comms_tile(ct)
        if self.sector is None and self.core_pos:
            self.sector = snap_cardinal(self.core_pos.direction_to(pos))
            if self.sector == Direction.NORTH:
                self.sector = SECTOR_DIRS[ct.get_id() % len(SECTOR_DIRS)]

        # Symmetry detection (runs every round until resolved)
        self._detect_symmetry(ct, pos)

        # Opportunistic broadcast: if we know the answer, write to any nearby comms tile
        if (
            self.sym_resolved
            and not self.learned_from_marker
            and not self.has_broadcast
        ):
            for candidate in self.comms_candidates:
                if pos.distance_squared(candidate) <= 2 and ct.can_place_marker(
                    candidate
                ):
                    ct.place_marker(candidate, encode_symmetry(self.sym_resolved))
                    print(
                        f"Broadcast: wrote [{self.sym_resolved.value}] to comms tile",
                    )
                    self.has_broadcast = True
                    break

        # Switch to broadcast phase if we detected symmetry during explore
        if (
            self.phase == Phase.EXPLORE
            and self.sym_resolved
            and not self.learned_from_marker
            and not self.has_broadcast
        ):
            self._start_broadcast(pos)

        match self.phase:
            case Phase.EXPLORE:
                self._explore(ct, pos)
            case Phase.LAY_CONVEYORS:
                self._lay_conveyors(ct, pos)
            case Phase.BROADCAST:
                self._broadcast(ct, pos)

    # ── Symmetry detection ────────────────────────────────────────────

    def _detect_symmetry(self, ct: Controller, pos: Position) -> None:
        if self.enemy_core is not None:
            return  # Already resolved

        if self.core_pos is None:
            return

        w = ct.get_map_width()
        h = ct.get_map_height()

        # Check if the core has posted the answer on any comms candidate tile
        for candidate in self.comms_candidates:
            if ct.is_in_vision(candidate):
                sym = read_comms_marker(ct, candidate)
                if sym is not None:
                    self.sym_resolved = sym
                    self.enemy_core = resolve_enemy_core(self.core_pos, sym, w, h)
                    self.comms_tile = candidate
                    self.learned_from_marker = True
                    return

        # Initialise candidates on first call
        if self.sym_candidates is None:
            self.sym_candidates = get_symmetry_candidates(self.core_pos, w, h)
            for s, epos in self.sym_candidates.items():
                if epos == self.core_pos:
                    self.sym_eliminated.add(s)
            # If all remaining candidates agree on same position, resolve
            if self._try_resolve_from_remaining(w, h):
                return

        # Direct verification: if we can see a candidate core tile, check it
        remaining = [s for s in self.sym_candidates if s not in self.sym_eliminated]
        my_team = ct.get_team()
        for s in list(remaining):
            epos = self.sym_candidates[s]
            if ct.is_in_vision(epos):
                bid = ct.get_tile_building_id(epos)
                if bid is not None:
                    if (
                        ct.get_entity_type(bid) == EntityType.CORE
                        and ct.get_team(bid) != my_team
                    ):
                        self.sym_resolved = s
                        self.enemy_core = epos
                        print(f"Enemy core at ({epos.x},{epos.y}) [{s.value}]")
                        return
                    self.sym_eliminated.add(s)
                else:
                    self.sym_eliminated.add(s)

        if self._try_resolve_from_remaining(w, h):
            return

        # Environment mismatch elimination
        new_tiles = []
        for tile in ct.get_nearby_tiles():
            if tile not in self.known_env:
                self.known_env[tile] = ct.get_tile_env(tile)
                new_tiles.append(tile)

        if not new_tiles:
            return

        remaining = [s for s in self.sym_candidates if s not in self.sym_eliminated]
        for s in list(remaining):
            if s in self.sym_eliminated:
                continue
            for tile in new_tiles:
                mirrored = mirror_pos(tile, s, w, h)
                if not in_bounds(ct, mirrored):
                    self.sym_eliminated.add(s)
                    break
                if (
                    mirrored in self.known_env
                    and self.known_env[mirrored] != self.known_env[tile]
                ):
                    self.sym_eliminated.add(s)
                    break

        self._try_resolve_from_remaining(w, h)

    def _try_resolve_from_remaining(self, w: int, h: int) -> bool:
        """Check if elimination has narrowed to a single answer. Returns True if resolved."""
        remaining = [s for s in self.sym_candidates if s not in self.sym_eliminated]
        if len(remaining) == 1:
            self.sym_resolved = remaining[0]
            self.enemy_core = self.sym_candidates[remaining[0]]
            print(
                f"Enemy core at ({self.enemy_core.x},{self.enemy_core.y}) [{self.sym_resolved.value}]",
            )
            return True
        if len(remaining) > 1:
            positions = {self.sym_candidates[s] for s in remaining}
            if len(positions) == 1:
                self.sym_resolved = remaining[0]
                self.enemy_core = positions.pop()
                print(
                    f"Enemy core at ({self.enemy_core.x},{self.enemy_core.y}) [{self.sym_resolved.value}]",
                )
                return True
        return False

    # ── Broadcast phase ───────────────────────────────────────────────

    def _start_broadcast(self, pos: Position) -> None:
        """Switch to broadcast: retrace explore path back toward core."""
        # Ensure current position is in the path (detection happens before _explore)
        if not self.path or self.path[-1] != pos:
            self.path.append(pos)
        cleaned = clean_path(self.path)
        self.return_path = list(reversed(cleaned))
        self.return_idx = 0
        self.stuck_turns = 0
        self.phase = Phase.BROADCAST

    def _broadcast(self, ct: Controller, pos: Position) -> None:
        """Retrace explore path back to core to deliver symmetry info."""
        # Already broadcast via opportunistic check? Done.
        if self.has_broadcast:
            self._finish_return()
            return

        # Advance index to current position
        while self.return_idx < len(self.return_path):
            if self.return_path[self.return_idx] == pos:
                break
            self.return_idx += 1

        # Reached core?
        if self.core_pos and is_on_core(pos, self.core_pos):
            self._finish_return()
            return

        if ct.get_move_cooldown() > 0:
            return

        if self.return_idx < len(self.return_path) - 1:
            next_pos = self.return_path[self.return_idx + 1]
            d = pos.direction_to(next_pos)
            if try_move(ct, pos, d, build_road=True, reserved=self.comms_tile):
                self.return_idx += 1
                self.stuck_turns = 0
                return
            self.stuck_turns += 1
            if self.stuck_turns > 3:
                for alt in cardinal_priority(cardinal_toward(pos, next_pos)):
                    if try_move(
                        ct,
                        pos,
                        alt,
                        build_road=True,
                        reserved=self.comms_tile,
                    ):
                        self.stuck_turns = 0
                        return
            if self.stuck_turns > 10:
                self.return_idx += 1
                self.stuck_turns = 0
        # End of path — walk directly toward core
        elif self.core_pos:
            try_move_toward(ct, pos, self.core_pos, reserved=self.comms_tile)

    # ── Explore ───────────────────────────────────────────────────────

    def _explore(self, ct: Controller, pos: Position) -> None:
        if pos in self.visited:
            self.explore_stale += 1
        else:
            self.explore_stale = 0
        self.visited.add(pos)
        if not self.path or self.path[-1] != pos:
            self.path.append(pos)

        # Build harvester on cardinally-adjacent ore
        if ct.get_action_cooldown() == 0:
            best_ore = None
            best_dir = None
            best_dist = 999999
            for d in CARDINAL:
                check = pos.add(d)
                if in_bounds(ct, check) and ct.can_build_harvester(check):
                    dist = check.distance_squared(self.core_pos) if self.core_pos else 0
                    if dist < best_dist:
                        best_dist = dist
                        best_ore = check
                        best_dir = d
            if best_ore and best_dir:
                ct.build_harvester(best_ore)
                self._start_return(best_dir)
                return

        if ct.get_move_cooldown() > 0:
            return

        # Decide preferred direction
        ore = find_nearest_ore(ct, pos)
        if ore:
            preferred = cardinal_toward(pos, ore)
        elif self.explore_stale > 4:
            nearest_unvisited: Position | None = None
            nearest_dist = 999999
            for tile in ct.get_nearby_tiles():
                if tile not in self.visited:
                    d = pos.distance_squared(tile)
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest_unvisited = tile
            if nearest_unvisited:
                preferred = cardinal_toward(pos, nearest_unvisited)
            else:
                return
        elif self.sector:
            preferred = snap_cardinal(self.sector)
        else:
            preferred = Direction.NORTH

        scored: list[tuple[int, Direction]] = []
        for d in CARDINAL:
            target = pos.add(d)
            if not in_bounds(ct, target):
                continue
            score = 0
            if target not in self.visited:
                score += 10
            if d == preferred:
                score += 3
            elif d != preferred.opposite():
                score += 1
            scored.append((score, d))

        scored.sort(key=lambda x: -x[0])
        for _, d in scored:
            if try_move(ct, pos, d, reserved=self.comms_tile):
                return

    # ── Return path (conveyor laying) ────────────────────────────────

    def _start_return(self, harvester_dir: Direction) -> None:
        cleaned = clean_path(self.path)
        self.return_path = list(reversed(cleaned))
        self.return_idx = 0
        self.stuck_turns = 0
        self.harvester_dir = harvester_dir
        self.phase = Phase.LAY_CONVEYORS

    def _lay_conveyors(self, ct: Controller, pos: Position) -> None:
        while self.return_idx < len(self.return_path):
            if self.return_path[self.return_idx] == pos:
                break
            self.return_idx += 1

        if self.core_pos and is_on_core(pos, self.core_pos):
            self._finish_return()
            return

        if self.return_idx > 0 and tile_has_friendly_conveyor(ct, pos):
            prev_pos = self.return_path[max(0, self.return_idx - 1)]
            if can_feed_into(ct, prev_pos, pos):
                # If we have a pending broadcast, keep walking toward core
                pending_broadcast = (
                    self.sym_resolved
                    and not self.learned_from_marker
                    and not self.has_broadcast
                )
                if not pending_broadcast:
                    self._finish_return()
                    return

        if self.return_idx >= len(self.return_path) - 1:
            if self.core_pos and try_move_toward(
                ct,
                pos,
                self.core_pos,
                reserved=self.comms_tile,
            ):
                return
            self._finish_return()
            return

        next_pos = self.return_path[self.return_idx + 1]

        if ct.get_action_cooldown() == 0:
            skip = (
                self.core_pos and is_on_core(pos, self.core_pos)
            ) or pos == self.comms_tile
            if not skip:
                conv_dir = cardinal_toward(pos, next_pos)
                if self.return_idx == 0 and conv_dir == self.harvester_dir:
                    for alt in cardinal_priority(conv_dir):
                        if alt != self.harvester_dir:
                            conv_dir = alt
                            break
                bid = ct.get_tile_building_id(pos)
                if bid is not None and ct.can_destroy(pos):
                    ct.destroy(pos)
                if ct.can_build_conveyor(pos, conv_dir):
                    ct.build_conveyor(pos, conv_dir)

        if ct.get_move_cooldown() > 0:
            return

        d = pos.direction_to(next_pos)
        if try_move(ct, pos, d, build_road=True, reserved=self.comms_tile):
            self.return_idx += 1
            self.stuck_turns = 0
        else:
            self.stuck_turns += 1
            if self.stuck_turns <= 3:
                return
            for alt in cardinal_priority(cardinal_toward(pos, next_pos)):
                if try_move(ct, pos, alt, build_road=True, reserved=self.comms_tile):
                    self.stuck_turns = 0
                    return
            if self.stuck_turns > 10:
                self.return_idx += 1
                self.stuck_turns = 0

    def _finish_return(self) -> None:
        self.phase = Phase.EXPLORE
        self.path = []
        self.return_path = []
        self.return_idx = 0
        self.stuck_turns = 0
        self.explore_stale = 0
