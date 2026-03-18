import random

from cambc import Controller, Direction, EntityType, Environment, Position

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

EXPLORING = 1
HARVESTING = 2
CONNECTING = 3
ATTACKING = 4
DESTRUCTOR = 5
GUNNERPLACER = 6
HEALER = 7

# Offsets for the plus-shaped healer positions (inside the 3×3 core footprint)
PLUS_OFFSETS = [(0, 0), (0, -1), (-1, 0), (1, 0), (0, 1)]
# Corner offsets for regular builder spawns
CORNER_OFFSETS = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
# Rounds on which a healer is spawned, mapped to their plus-tile offset index
HEALER_SPAWN_MAP = {71: 0, 157: 1, 167: 2, 171: 3, 193: 4}

# Marker encoding: pack an ore claim as a recognizable value
# We use (x * 100 + y) + 10000 as the marker value to distinguish from 0
CLAIM_OFFSET = 10000

LATE_GAME_ROUND = 500
MIN_ATTACK_ROUND = 200

# Loop detection settings
HISTORY_LENGTH = 30  # how many recent positions to remember
MIN_CYCLE_LEN = 2  # shortest cycle we look for
MAX_CYCLE_LEN = 10  # longest cycle we look for
CYCLE_REPEATS_NEEDED = 2  # how many full repeats of the cycle to require


def encode_claim(pos: Position) -> int:
    return pos.x * 100 + pos.y + CLAIM_OFFSET


def decode_claim(val: int) -> Position | None:
    if val < CLAIM_OFFSET:
        return None
    val -= CLAIM_OFFSET
    return Position(val // 100, val % 100)


def _detect_loop(history: list[Position]) -> bool:
    """Check if the tail of `history` contains a repeating positional cycle.

    Looks for any cycle of length MIN_CYCLE_LEN..MAX_CYCLE_LEN that repeats
    at least CYCLE_REPEATS_NEEDED times at the end of the history buffer.
    """
    n = len(history)
    if n < MIN_CYCLE_LEN * CYCLE_REPEATS_NEEDED:
        return False
    for cycle_len in range(MIN_CYCLE_LEN, MAX_CYCLE_LEN + 1):
        needed = cycle_len * CYCLE_REPEATS_NEEDED
        if needed > n:
            break
        tail = history[-needed:]
        pattern = tail[:cycle_len]
        is_cycle = True
        for rep in range(1, CYCLE_REPEATS_NEEDED):
            chunk = tail[rep * cycle_len : (rep + 1) * cycle_len]
            if chunk != pattern:
                is_cycle = False
                break
        if is_cycle:
            return True
    return False


class Player:
    def __init__(self) -> None:
        self.round = 0

        self.core_pos = None

        self.prev_pos = None
        self.line = None

        self.is_tracing = False
        self.tracing_dir = None
        self.obs_start_dist = 0

        self.target = None
        self.prev_target: Position = None
        self.builders_spawned = 0

        self.state = EXPLORING
        self.explore_direction = None
        self.first_run = True  # used to detect healer identity on spawn turn

        # Persistent wander direction — each bot picks one and sticks to it
        self.wander_dir = None

        # Track conveyors this builder placed (so we never destroy others')
        self.placed_conveyors: set[Position] = set()

        # Stuck / loop detection
        self.stuck_pos = None
        self.stuck_turns = 0
        self.pos_history: list[Position] = []

        # Last known enemy core position (used by ATTACKING)
        self.enemy_core_pos: Position | None = None

        # DESTRUCTOR/GUNNERPLACER coordination
        self.partner_wait: int = 0
        self.core_wait: int = 0
        self.near_core_turns: int = 0

    def can_path_through(self, pos: Position, ct: Controller) -> bool:
        if not self.in_map(pos, ct):
            return False
        return ct.is_tile_passable(pos)

    def can_explore(self, pos: Position, ct: Controller) -> bool:
        if not self.in_map(pos, ct):
            return False
        if ct.is_tile_passable(pos):
            return True
        env = ct.get_tile_env(pos)
        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            return False
        return ct.get_tile_building_id(pos) is None

    def _is_core_tile(self, pos: Position, ct: Controller) -> bool:
        if not (0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()):
            return False
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            return False
        return (
            ct.get_entity_type(bid) == EntityType.CORE
            and ct.get_team(bid) == ct.get_team()
        )

    def _is_own_conveyor(self, pos: Position, ct: Controller) -> bool:
        """Return True only if there's a conveyor at `pos` that THIS builder placed."""
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            return False
        etype = ct.get_entity_type(bid)
        if etype not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
            return False
        return pos in self.placed_conveyors

    def in_map(self, pos: Position, ct: Controller):
        return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()

    # ------------------------------------------------------------------
    # Stuck + loop detection
    # ------------------------------------------------------------------
    def _check_stuck(self, ct: Controller) -> bool:
        if self.state in (DESTRUCTOR, GUNNERPLACER, HEALER):
            return False

        pos = ct.get_position()

        # --- plain stuck (hasn't moved at all) ---
        if self.stuck_pos is not None and pos == self.stuck_pos:
            self.stuck_turns += 1
        else:
            self.stuck_turns = 0
        self.stuck_pos = pos

        if self.stuck_turns >= 20:
            # If already attacking and stationary within 8 tiles of enemy core,
            # commit as DESTRUCTOR instead of continuing to wander.
            if (
                self.state == ATTACKING
                and self.enemy_core_pos is not None
                and pos.distance_squared(self.enemy_core_pos) <= 8
            ):
                self.state = DESTRUCTOR
                self.partner_wait = 0
                self.core_wait = 0
                self.stuck_turns = 0
                self.pos_history.clear()
                return True
            if ct.get_current_round() >= MIN_ATTACK_ROUND:
                self._enter_attack_mode()
                return True

        # --- loop detection (moving but revisiting a cycle) ---
        self.pos_history.append(pos)
        if len(self.pos_history) > HISTORY_LENGTH:
            self.pos_history = self.pos_history[-HISTORY_LENGTH:]

        if _detect_loop(self.pos_history):
            if self.state == CONNECTING:
                return False
            if ct.get_current_round() >= MIN_ATTACK_ROUND:
                self._enter_attack_mode()
                return True

        return False

    def _enter_attack_mode(self) -> None:
        self.state = ATTACKING
        self.target = None
        self.prev_pos = None
        self.stuck_turns = 0
        self.is_tracing = False
        self.pos_history.clear()
        # Pick a fresh wander direction so the attacker doesn't repeat
        self.wander_dir = random.choice(DIRECTIONS)

    # ------------------------------------------------------------------
    # Ore claiming — read nearby markers to see what's already taken
    # ------------------------------------------------------------------
    def _is_ore_claimed(self, ore_pos: Position, ct: Controller) -> bool:
        """Check if any visible marker claims this ore position."""
        target_val = encode_claim(ore_pos)
        for eid in ct.get_nearby_buildings():
            if ct.get_entity_type(eid) == EntityType.MARKER:
                if ct.get_team(eid) == ct.get_team():
                    if ct.get_marker_value(eid) == target_val:
                        return True
        return False

    def _place_claim(self, ct: Controller, ore_pos: Position) -> None:
        """Place a marker on our current tile claiming this ore."""
        pos = ct.get_position()
        if ct.can_place_marker(pos):
            ct.place_marker(pos, encode_claim(ore_pos))

    # ------------------------------------------------------------------
    # Conveyor helpers (build + track)
    # ------------------------------------------------------------------
    def _build_conveyor_tracked(
        self,
        ct: Controller,
        pos: Position,
        direction: Direction,
    ) -> bool:
        """Build a conveyor and record it in placed_conveyors. Returns True if built."""
        if ct.get_action_cooldown() == 0 and ct.can_build_conveyor(pos, direction):
            ct.build_conveyor(pos, direction)
            self.placed_conveyors.add(pos)
            return True
        return False

    def _destroy_if_own(self, ct: Controller, pos: Position) -> bool:
        """Destroy building at pos ONLY if it's a conveyor we placed, or a road. Returns True if destroyed."""
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            return False
        etype = ct.get_entity_type(bid)

        # Roads are always safe to destroy (they're temporary pathfinding aids)
        if etype == EntityType.ROAD:
            if ct.get_action_cooldown() == 0 and ct.can_destroy(pos):
                ct.destroy(pos)
                return True
            return False

        # Only destroy conveyors that this builder placed
        if etype in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
            if pos in self.placed_conveyors:
                if ct.get_action_cooldown() == 0 and ct.can_destroy(pos):
                    ct.destroy(pos)
                    self.placed_conveyors.discard(pos)
                    return True
            return False

        return False

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    def core_function(self, ct: Controller) -> None:
        self.round += 1
        pos = ct.get_position()

        # --- Healer spawning on designated rounds ---
        if self.round in HEALER_SPAWN_MAP:
            dx, dy = PLUS_OFFSETS[HEALER_SPAWN_MAP[self.round]]
            target = Position(pos.x + dx, pos.y + dy)
            if self.in_map(target, ct) and ct.can_spawn(target):
                ct.spawn_builder(target)
            return

        # --- After round 100: respawn any missing healers ---
        if self.round >= 200:
            for dx, dy in PLUS_OFFSETS:
                target = Position(pos.x + dx, pos.y + dy)
                if not self.in_map(target, ct):
                    continue
                if ct.get_tile_builder_bot_id(target) is None and ct.can_spawn(target):
                    ct.spawn_builder(target)
                    return

        # --- Regular builder spawning on corners only ---
        if self.builders_spawned >= 5 and self.round < LATE_GAME_ROUND:
            return
        if self.round % 10 != 0 and self.round not in {1, 7, 15}:
            return

        for dx, dy in CORNER_OFFSETS:
            target = Position(pos.x + dx, pos.y + dy)
            if not self.in_map(target, ct):
                continue
            if not ct.can_spawn(target):
                continue
            ct.spawn_builder(target)
            self.builders_spawned += 1
            return

    # ------------------------------------------------------------------
    # Exploring — with ore claiming and persistent wander direction
    # ------------------------------------------------------------------
    def builder_explore(self, ct: Controller) -> None:
        pos = ct.get_position()

        # Vision-safe ore check: drop target if tile is no longer empty
        if self.target is not None and ct.is_in_vision(self.target):
            if not ct.is_tile_empty(self.target):
                self.target = None

        # Scan for nearest UNCLAIMED titanium ore
        if self.target is None:
            min_dist = 999999
            for t in ct.get_nearby_tiles():
                if (
                    ct.get_tile_env(t) == Environment.ORE_TITANIUM
                    and ct.is_tile_empty(t)
                    and not self._is_ore_claimed(t, ct)
                ):
                    dist = pos.distance_squared(t)
                    if dist < min_dist:
                        min_dist = dist
                        self.target = t

            # If all unclaimed ore is taken, fall back to any empty ore
            if self.target is None:
                min_dist = 999999
                for t in ct.get_nearby_tiles():
                    if ct.get_tile_env(
                        t,
                    ) == Environment.ORE_TITANIUM and ct.is_tile_empty(t):
                        dist = pos.distance_squared(t)
                        if dist < min_dist:
                            min_dist = dist
                            self.target = t

        # Found ore — claim it and switch to harvesting
        if self.target is not None:
            self._place_claim(ct, self.target)
            self.state = HARVESTING
            return

        # No ore seen — wander with a persistent direction to spread out
        if self.wander_dir is None:
            self.wander_dir = random.choice(DIRECTIONS)

        if self.can_explore(pos.add(self.wander_dir), ct):
            self._move_or_build_road(ct, self.wander_dir)
        else:
            valid = [d for d in DIRECTIONS if self.can_explore(pos.add(d), ct)]
            if valid:
                non_back = [
                    d for d in valid if not self.prev_pos or pos.add(d) != self.prev_pos
                ]
                self.wander_dir = (
                    random.choice(non_back) if non_back else random.choice(valid)
                )
                self._move_or_build_road(ct, self.wander_dir)

    # ------------------------------------------------------------------
    # Harvesting (build harvester on ore)
    # ------------------------------------------------------------------
    def builder_build_harvester(self, ct: Controller) -> None:
        pos = ct.get_position()

        if not self.target:
            self.state = EXPLORING
            return

        if pos.distance_squared(self.target) <= 1:  # includes diagonal
            if ct.is_in_vision(self.target) and not ct.is_tile_empty(self.target):
                self.target = None
                self.state = EXPLORING
                return
            if ct.get_action_cooldown() == 0:
                if ct.can_build_harvester(self.target):
                    ct.build_harvester(self.target)
                    self.target = None
                    if ct.get_current_round() < 100:
                        self.state = EXPLORING
                    else:
                        self.state = CONNECTING
                else:
                    # Can't build despite being adjacent — give up on this ore
                    self.target = None
                    self.state = EXPLORING
            return

        self.bug2(ct)

    # ------------------------------------------------------------------
    # Connecting (conveyors back to core)
    # ------------------------------------------------------------------
    def builder_connect(self, ct: Controller) -> None:
        pos = ct.get_position()

        if self._is_core_tile(pos, ct):
            self.state = EXPLORING
            self.target = None
            return

        for d in CARDINALS:
            adj = pos.add(d)
            if self._is_core_tile(adj, ct):
                self._finish_connect(ct, d)
                return

        if self.target is None or self.target != self.core_pos:
            self.target = self.core_pos

        self.bug2(ct, move_fn=self._connect_move)

    def _finish_connect(self, ct: Controller, direction: Direction) -> None:
        pos = ct.get_position()
        bid_here = ct.get_tile_building_id(pos)
        etype_here = ct.get_entity_type(bid_here) if bid_here is not None else None

        if etype_here == EntityType.ROAD:
            self._destroy_if_own(ct, pos)
            return

        is_conveyor = etype_here in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR)

        if not is_conveyor:
            self._build_conveyor_tracked(ct, pos, direction)
            return

        conveyor_dir = ct.get_direction(bid_here)
        if conveyor_dir != direction:
            # Only re-orient if we placed this conveyor
            if pos in self.placed_conveyors:
                if ct.get_action_cooldown() == 0 and ct.can_destroy(pos):
                    ct.destroy(pos)
                    self.placed_conveyors.discard(pos)
            else:
                # Foreign conveyor — our chain already feeds into this tile,
                # treat it as connected and stop.
                self.state = EXPLORING
                self.target = None
            return

        if ct.get_move_cooldown() == 0 and ct.can_move(direction):
            ct.move(direction)
            self.prev_pos = pos

    # ------------------------------------------------------------------
    # Find an enemy conveyor tile next to the core that has a resource
    # stored on it (titanium flowing into the core).  Returns None if
    # none is currently visible.
    # ------------------------------------------------------------------
    def _find_attack_tile(self, ct: Controller) -> Position | None:
        if self.enemy_core_pos is None:
            return None
        my_team = ct.get_team()
        for eid in ct.get_nearby_buildings():
            if ct.get_team(eid) == my_team:
                continue
            etype = ct.get_entity_type(eid)
            if etype not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            epos = ct.get_position(eid)
            if epos.distance_squared(self.enemy_core_pos) > 6:
                continue
            if ct.get_stored_resource(eid) is None:
                continue
            return epos
        return None

    # ------------------------------------------------------------------
    # Attacking — navigate to the enemy core and surround it.
    # Targets a conveyor tile pointing into the core (with resource flow
    # if possible), then transitions to DESTRUCTOR or GUNNERPLACER.
    # ------------------------------------------------------------------
    def builder_attack(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

        # Update known enemy core position
        for eid in ct.get_nearby_entities():
            if (
                ct.get_entity_type(eid) == EntityType.CORE
                and ct.get_team(eid) != my_team
            ):
                self.enemy_core_pos = ct.get_position(eid)
                break

        if self.enemy_core_pos is None:
            self.near_core_turns = 0
            # Wander until the enemy core comes into view
            if self.wander_dir is None:
                self.wander_dir = random.choice(DIRECTIONS)
            if self.can_explore(pos.add(self.wander_dir), ct):
                self._move_or_build_road(ct, self.wander_dir)
            else:
                valid = [d for d in DIRECTIONS if self.can_explore(pos.add(d), ct)]
                if valid:
                    non_back = [
                        d
                        for d in valid
                        if not self.prev_pos or pos.add(d) != self.prev_pos
                    ]
                    self.wander_dir = (
                        random.choice(non_back) if non_back else random.choice(valid)
                    )
                    self._move_or_build_road(ct, self.wander_dir)
            return

        # If we've been within 8 distance-squared of the core for 20+ turns,
        # stop trying to navigate and commit as DESTRUCTOR.
        if pos.distance_squared(self.enemy_core_pos) <= 8:
            self.near_core_turns += 1
            if self.near_core_turns >= 20:
                self.state = DESTRUCTOR
                self.partner_wait = 0
                self.core_wait = 0
                self.near_core_turns = 0
                return
        else:
            self.near_core_turns = 0

        # Check if a friendly builder is already parked near the core.
        # If so, navigate adjacent to it and become GUNNERPLACER.
        # We must do this check BEFORE attempting attack_tile navigation,
        # otherwise bots target the occupied tile and circle indefinitely.
        parked_pos = None
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(eid) != my_team:
                continue
            bpos = ct.get_position(eid)
            if bpos == pos:
                continue
            if bpos.distance_squared(self.enemy_core_pos) <= 6:
                parked_pos = bpos
                break

        if parked_pos is not None:
            if pos.distance_squared(parked_pos) <= 2:
                # Adjacent to the parked DESTRUCTOR — commit as GUNNERPLACER
                self.state = GUNNERPLACER
                self.partner_wait = 0
            else:
                # Navigate toward the parked builder (bug2 will stop adjacent
                # since the tile itself is occupied)
                self.target = parked_pos
                self.bug2(ct)
            return

        # No friendly builder at core yet — claim the attack tile ourselves.
        attack_tile = self._find_attack_tile(ct)
        if attack_tile is not None:
            if pos == attack_tile:
                self.state = DESTRUCTOR
                self.partner_wait = 0
                self.core_wait = 0
                return
            self.target = attack_tile
        else:
            self.target = self.enemy_core_pos
        self.bug2(ct)

    # ------------------------------------------------------------------
    # Destructor — hold position; once a partner arrives, count 5 turns
    # then self-destruct to clear the tile.
    # ------------------------------------------------------------------
    def builder_destructor(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

        self.core_wait += 1
        if self.core_wait >= 100:
            ct.self_destruct()
            return

        has_partner = False
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(eid) != my_team:
                continue
            bpos = ct.get_position(eid)
            if bpos == pos:
                continue
            if pos.distance_squared(bpos) <= 2:
                has_partner = True
                break

        if has_partner:
            self.partner_wait += 1
            if self.partner_wait >= 5:
                ct.self_destruct()
        else:
            self.partner_wait = 0

    # ------------------------------------------------------------------
    # Gunner placer — wait at the core; each turn scan every adjacent tile
    # near the core for a spot where a gunner can be built (i.e. the tile
    # the DESTRUCTOR just cleared).  Place it and return to ATTACKING.
    # ------------------------------------------------------------------
    def builder_gunnerplacer(self, ct: Controller) -> None:
        if self.enemy_core_pos is None or ct.get_action_cooldown() != 0:
            return

        pos = ct.get_position()
        for d in DIRECTIONS:
            adj = pos.add(d)
            if not self.in_map(adj, ct):
                continue
            if adj.distance_squared(self.enemy_core_pos) > 6:
                continue
            gun_dir = adj.direction_to(self.enemy_core_pos)
            if ct.can_build_gunner(adj, gun_dir):
                ct.build_gunner(adj, gun_dir)
                self.partner_wait = 0
                self.state = ATTACKING
                return

    # ------------------------------------------------------------------
    # Healer — stays put and heals its tile every turn
    # ------------------------------------------------------------------
    def builder_healer(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return
        pos = ct.get_position()
        if ct.can_heal(pos):
            ct.heal(pos)

    # ------------------------------------------------------------------
    # Bug2 pathfinding
    # ------------------------------------------------------------------
    def bug2(self, ct: Controller, move_fn=None) -> None:
        if move_fn is None:
            move_fn = self._move_or_build_road
        pos = ct.get_position()
        if self.target != self.prev_target:
            self.prev_target = self.target
            self.line = self.create_line(pos, self.target)
            self.is_tracing = False

        if not self.is_tracing:
            dir = pos.direction_to(self.target)
            if dir not in CARDINALS:
                dir = dir.rotate_right()
            if self.can_explore(pos.add(dir), ct):
                move_fn(ct, dir)
            else:
                self.is_tracing = True
                self.obs_start_dist = pos.distance_squared(self.target)
                self.tracing_dir = dir
        else:
            if (
                pos in self.line
                and pos.distance_squared(self.target) < self.obs_start_dist
            ):
                self.is_tracing = False
                return

            if self.can_explore(pos.add(self.tracing_dir), ct):
                moved = move_fn(ct, self.tracing_dir)
                if moved:
                    self.tracing_dir = self.tracing_dir.rotate_right()
                    self.tracing_dir = self.tracing_dir.rotate_right()
            else:
                for _i in range(4):
                    self.tracing_dir = self.tracing_dir.rotate_left()
                    self.tracing_dir = self.tracing_dir.rotate_left()
                    if self.can_explore(pos.add(self.tracing_dir), ct):
                        moved = move_fn(ct, self.tracing_dir)
                        if moved:
                            self.tracing_dir = self.tracing_dir.rotate_right()
                            self.tracing_dir = self.tracing_dir.rotate_right()
                        break

    def create_line(self, a: Position, b: Position):
        locs = set()

        x1, y1 = a.x, a.y
        x2, y2 = b.x, b.y

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        x, y = x1, y1
        while True:
            locs.add(Position(x, y))
            if x == x2 and y == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

        return locs

    def builder_get_best_direction(
        self,
        target: Position,
        ct: Controller,
        cardinal: bool = True,
    ):
        pos = ct.get_position()

        best_dir = pos.direction_to(target)
        if cardinal and best_dir not in CARDINALS:
            best_dir = best_dir.rotate_left()

        if not self.can_explore(pos.add(best_dir), ct):
            fallbacks = []
            if cardinal:
                fallbacks = [
                    best_dir.rotate_left().rotate_left(),
                    best_dir.opposite(),
                    best_dir.rotate_right().rotate_right(),
                ]
            else:
                fallbacks = [
                    best_dir.rotate_left(),
                    best_dir.rotate_left().rotate_left(),
                    best_dir.rotate_left().rotate_left().rotate_left(),
                    best_dir.opposite(),
                    best_dir.rotate_right().rotate_right().rotate_right(),
                    best_dir.rotate_right().rotate_right(),
                    best_dir.rotate_right(),
                ]
            best_dir = None
            for f_dir in fallbacks:
                np = pos.add(f_dir)
                if (self.prev_pos and self.prev_pos != np) and self.can_explore(np, ct):
                    best_dir = f_dir
                    break
            if best_dir is None:
                for f_dir in fallbacks:
                    np = pos.add(f_dir)
                    if (self.prev_pos and self.prev_pos != np) and self.can_explore(
                        pos.add(f_dir),
                        ct,
                    ):
                        best_dir = f_dir
                        break
        return best_dir

    def builder_step_to_target(
        self,
        target: Position,
        ct: Controller,
        cardinal: bool = True,
    ) -> None:
        best_dir = self.builder_get_best_direction(target, ct, cardinal)

        if best_dir is not None and best_dir != Direction.CENTRE:
            self._move_or_build_road(ct, best_dir)

    def builder_function(self, ct: Controller) -> None:
        # If exploring/harvesting/connecting and the enemy core comes into
        # view, immediately switch to ATTACKING.
        if self.state == EXPLORING:
            my_team = ct.get_team()
            for eid in ct.get_nearby_entities():
                if (
                    ct.get_entity_type(eid) == EntityType.CORE
                    and ct.get_team(eid) != my_team
                ):
                    self._enter_attack_mode()
                    break

        # While moving toward the enemy core, opportunistically harvest
        # any nearby unclaimed titanium ore.  DESTRUCTOR and GUNNERPLACER
        # must not leave their positions, so they are excluded.
        if self.state == ATTACKING:
            for t in ct.get_nearby_tiles():
                if (
                    ct.get_tile_env(t) == Environment.ORE_TITANIUM
                    and ct.is_tile_empty(t)
                    and not self._is_ore_claimed(t, ct)
                ):
                    self.state = HARVESTING
                    self.target = t
                    self.is_tracing = False
                    break

        if self.state == EXPLORING:
            self.builder_explore(ct)
        elif self.state == HARVESTING:
            self.builder_build_harvester(ct)
        elif self.state == CONNECTING:
            self.builder_connect(ct)
        elif self.state == ATTACKING:
            self.builder_attack(ct)
        elif self.state == DESTRUCTOR:
            self.builder_destructor(ct)
        elif self.state == GUNNERPLACER:
            self.builder_gunnerplacer(ct)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()

        if self.core_pos is None:
            for eid in ct.get_nearby_entities():
                if (
                    ct.get_entity_type(eid) == EntityType.CORE
                    and ct.get_team(eid) == ct.get_team()
                ):
                    self.core_pos = ct.get_position(eid)
                    break
            if self.core_pos is None:
                self.core_pos = ct.get_position()
        if etype == EntityType.GUNNER:
            pos = ct.get_position()
            if ct.can_fire(pos.add(ct.get_direction())):
                pos = ct.get_position()
                ct.fire(pos.add(ct.get_direction()))
        if etype == EntityType.CORE:
            self.core_function(ct)
        elif etype == EntityType.BUILDER_BOT:
            # Identify healers on their very first turn by spawn round
            if self.first_run:
                self.first_run = False
                if ct.get_current_round() in HEALER_SPAWN_MAP:
                    self.state = HEALER
            if self.state == HEALER:
                self.builder_healer(ct)
                return
            if self._check_stuck(ct):
                return
            self.builder_function(ct)

    # ------------------------------------------------------------------
    # Movement helpers
    # ------------------------------------------------------------------
    def _move_or_build_road(self, ct: Controller, direction: Direction) -> bool:
        curr_pos = ct.get_position()
        next_pos = ct.get_position().add(direction)
        if not (
            0 <= next_pos.x < ct.get_map_width()
            and 0 <= next_pos.y < ct.get_map_height()
        ):
            return False
        if ct.get_tile_builder_bot_id(next_pos) is not None:
            return False

        bid = ct.get_tile_building_id(next_pos)
        if bid is None:
            if ct.get_current_round() < 100:
                # Early game: place a backward conveyor (ore flows toward core)
                back = direction.opposite()
                if ct.get_action_cooldown() == 0 and ct.can_build_conveyor(
                    next_pos,
                    back,
                ):
                    ct.build_conveyor(next_pos, back)
                    self.placed_conveyors.add(next_pos)
                return False
            # Late game: build a road and move onto it
            if ct.get_action_cooldown() == 0 and ct.can_build_road(next_pos):
                ct.build_road(next_pos)
                if ct.get_move_cooldown() == 0 and ct.can_move(direction):
                    ct.move(direction)
                    self.prev_pos = curr_pos
                    return True
                return False
            return False
        if ct.get_move_cooldown() == 0 and ct.can_move(direction):
            ct.move(direction)
            self.prev_pos = curr_pos
            return True
        return False

    def _connect_move(self, ct: Controller, direction: Direction) -> bool:
        pos = ct.get_position()
        next_pos = pos.add(direction)
        if not self.in_map(next_pos, ct):
            return False
        if ct.get_tile_builder_bot_id(next_pos) is not None:
            return False

        if self._is_core_tile(next_pos, ct):
            if ct.get_move_cooldown() == 0 and ct.can_move(direction):
                ct.move(direction)
                self.prev_pos = pos
                return True
            return False

        bid_here = ct.get_tile_building_id(pos)
        etype_here = ct.get_entity_type(bid_here) if bid_here is not None else None

        if etype_here == EntityType.ROAD:
            if self._destroy_if_own(ct, pos):
                if not ct.can_build_conveyor(pos, direction):
                    return False
                ct.build_conveyor(pos, direction)
                self.placed_conveyors.add(pos)
            return False

        is_conveyor = etype_here in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR)

        if not is_conveyor:
            self._build_conveyor_tracked(ct, pos, direction)
            return False

        conveyor_dir = ct.get_direction(bid_here)
        if conveyor_dir != direction:
            # Only re-orient if we placed this conveyor
            if pos in self.placed_conveyors:
                if ct.get_action_cooldown() == 0 and ct.can_destroy(pos):
                    ct.destroy(pos)
                    self.placed_conveyors.discard(pos)
            else:
                # Foreign conveyor — our chain already feeds into this tile,
                # treat it as connected and stop.
                self.state = EXPLORING
                self.target = None
            return False

        bid_next = ct.get_tile_building_id(next_pos)
        if bid_next is None and not ct.is_tile_passable(next_pos):
            # Place a conveyor instead of a road so ore starts flowing immediately.
            # Direction is our current heading; if bug2 changes course when we
            # arrive, _connect_move will re-orient our own conveyor.
            if ct.get_action_cooldown() == 0 and ct.can_build_conveyor(
                next_pos,
                direction,
            ):
                ct.build_conveyor(next_pos, direction)
                self.placed_conveyors.add(next_pos)
            return False

        if ct.get_move_cooldown() == 0 and ct.can_move(direction):
            ct.move(direction)
            self.prev_pos = pos
            return True
        return False
