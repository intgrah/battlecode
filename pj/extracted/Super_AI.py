from enum import Enum

from cambc import Controller, Direction, EntityType, Environment, Position
from combat import RushManager
from economy import EconomyManager
from movement import MovementManager
from symmetry import SymmetryDetector
from utils import DIRECTIONS, RUSH_MARKER_VALUE, can_afford, find_core_pos


class BuilderState(Enum):
    EXPLORING = "exploring"
    PATH_TO_ORE = "path_to_ore"
    BUILD_HARVESTER = "build_harvester"
    BUILD_CONVEYOR = "build_conveyor"
    RETURN_TO_CORE = "return_to_core"


class BuilderRole(Enum):
    ECONOMY = "economy"
    RUSHER = "rusher"


class BuilderHandler:
    def __init__(self) -> None:
        self.state = BuilderState.EXPLORING
        self.movement = MovementManager()
        self.economy = EconomyManager()
        self.symmetry = SymmetryDetector()
        self.target_ore: Position | None = None
        self.core_pos: Position | None = None

        self.chain_path: list[tuple[Position, Direction]] = []
        self.chain_index: int = 0

        self.known_ores: list[Position] = []
        self._known_ore_set: set[Position] = set()
        self._mirror_checked: set[Position] = set()

        self.explore_target: Position | None = None
        self.explore_sector: int = 0
        self.stuck_turns: int = 0
        self.last_pos: Position | None = None

        # Cached explore grid (populated on first use)
        self._explore_grid: list[Position] | None = None

        # Handler dispatch dict (moved to __init__ from play())
        self._handlers = {
            BuilderState.EXPLORING: self._do_exploring,
            BuilderState.PATH_TO_ORE: self._do_path_to_ore,
            BuilderState.BUILD_HARVESTER: self._do_build_harvester,
            BuilderState.BUILD_CONVEYOR: self._do_build_conveyor,
            BuilderState.RETURN_TO_CORE: self._do_return_to_core,
        }

        # Role system: economy (default) or rusher
        self.role = BuilderRole.ECONOMY
        self._role_assigned = False
        self.rush_manager: RushManager | None = None

    def init_turn(self, ct: Controller) -> None:
        if self.core_pos is None:
            self.core_pos = find_core_pos(ct)
        my_pos = ct.get_position()
        if self.last_pos is not None and my_pos == self.last_pos:
            self.stuck_turns += 1
        else:
            self.stuck_turns = 0
        self.last_pos = my_pos
        self.symmetry.update(ct)

        # Role assignment: check if core placed a rush marker on our spawn tile
        if not self._role_assigned:
            self._assign_role(ct)
            self._role_assigned = True

        # Only scan for ore if economy builder
        if self.role == BuilderRole.ECONOMY:
            self._scan_for_ore(ct)

    def _assign_role(self, ct: Controller) -> None:
        """Assign role based on rush marker placed by core near spawn tile."""
        for eid in ct.get_nearby_entities():
            try:
                if ct.get_entity_type(eid) != EntityType.MARKER:
                    continue
                if ct.get_team(eid) != ct.get_team():
                    continue
                val = ct.get_marker_value(eid)
                if val == RUSH_MARKER_VALUE:
                    self.role = BuilderRole.RUSHER
                    self.rush_manager = RushManager()
                    mpos = ct.get_position(eid)
                    if ct.can_destroy(mpos):
                        ct.destroy(mpos)
                    return
            except Exception:
                continue

    def play(self, ct: Controller) -> None:
        # Rush builders delegate to RushManager
        if self.role == BuilderRole.RUSHER and self.rush_manager is not None:
            still_rushing = self.rush_manager.play(
                ct,
                self.movement,
                self.core_pos,
                self.symmetry,
            )
            if not still_rushing:
                # Rush failed/done, convert to economy builder
                self.role = BuilderRole.ECONOMY
                self.rush_manager = None
            return

        # Economy builder: normal FSM
        self._handlers[self.state](ct)

    def end_turn(self, ct: Controller) -> None:
        pass

    # -- State handlers -------------------------------------------------------

    def _do_exploring(self, ct: Controller) -> None:
        my_pos = ct.get_position()
        ti, _ = ct.get_global_resources()

        # Only seek ore if we can afford harvester + estimated chain
        harvester_cost = ct.get_harvester_cost()[0]
        conveyor_cost = ct.get_conveyor_cost()[0]
        core = self.core_pos or my_pos
        best_ore = self._pick_best_known_ore(ct, core)
        if best_ore is not None:
            est_chain = abs(best_ore.x - core.x) + abs(best_ore.y - core.y)
            total_cost = harvester_cost + conveyor_cost * est_chain + 10
            if ti >= total_cost:
                self.target_ore = best_ore
                self.state = BuilderState.PATH_TO_ORE
                self._do_path_to_ore(ct)
                return

        # Out of titanium and far from core? Head back
        if ti < ct.get_road_cost()[0] and self.core_pos is not None:
            if my_pos.distance_squared(self.core_pos) > 20:
                self.state = BuilderState.RETURN_TO_CORE
                return

        # Systematic exploration sweep
        if (
            self.explore_target is None
            or my_pos.distance_squared(self.explore_target) < 4
            or self.stuck_turns > 8
        ):
            self.explore_target = self._pick_explore_target(ct)
            self.stuck_turns = 0

        if self.explore_target is not None:
            self.movement.move_to(ct, self.explore_target)

    def _do_path_to_ore(self, ct: Controller) -> None:
        if self.target_ore is None:
            self.state = BuilderState.EXPLORING
            return

        my_pos = ct.get_position()

        # Validate ore is still free
        if ct.is_in_vision(self.target_ore):
            if ct.get_tile_building_id(self.target_ore) is not None:
                self.target_ore = self._pick_best_known_ore(ct, self.core_pos or my_pos)
                if self.target_ore is None:
                    self.state = BuilderState.EXPLORING
                    return

        if my_pos.distance_squared(self.target_ore) <= 2:
            self.state = BuilderState.BUILD_HARVESTER
            self._do_build_harvester(ct)
            return

        if self.stuck_turns > 15:
            self.target_ore = None
            self.state = BuilderState.EXPLORING
            self.stuck_turns = 0
            return

        self.movement.move_to(ct, self.target_ore)

    def _do_build_harvester(self, ct: Controller) -> None:
        if self.target_ore is None:
            self.state = BuilderState.EXPLORING
            return

        if self.economy.try_build_harvester(ct, self.target_ore):
            harvester_pos = self.target_ore
            self.target_ore = None
            self._start_chain(ct, harvester_pos)
            return

        if not can_afford(ct, ct.get_harvester_cost()):
            self.target_ore = None
            self.state = BuilderState.EXPLORING

    def _do_build_conveyor(self, ct: Controller) -> None:
        if not self.chain_path or self.chain_index >= len(self.chain_path):
            self._finish_chain()
            return
        if self.core_pos is None:
            self._finish_chain()
            return

        my_pos = ct.get_position()
        target_pos, face_dir = self.chain_path[self.chain_index]

        # Handle existing buildings at target
        if ct.is_in_vision(target_pos):
            building_id = ct.get_tile_building_id(target_pos)
            if building_id is not None:
                btype = ct.get_entity_type(building_id)
                if (
                    btype == EntityType.ROAD
                    and ct.get_team(building_id) == ct.get_team()
                ):
                    # Destroy our road to make room (free action)
                    if my_pos.distance_squared(target_pos) <= 2 and ct.can_destroy(
                        target_pos,
                    ):
                        ct.destroy(target_pos)
                    else:
                        self.movement.move_to(ct, target_pos)
                        return
                elif btype == EntityType.CONVEYOR:
                    self.chain_index += 1
                    return
                else:
                    self.chain_index += 1
                    return

        # Build if adjacent and ready
        if my_pos.distance_squared(target_pos) <= 2 and ct.get_action_cooldown() == 0:
            if self.economy.try_build_chain_segment(ct, target_pos, face_dir):
                self.chain_index += 1
                dir_to_new = my_pos.direction_to(target_pos)
                if ct.can_move(dir_to_new):
                    ct.move(dir_to_new)
                return
            # Hit a wall -- replan chain
            if (
                ct.is_in_vision(target_pos)
                and ct.get_tile_env(target_pos) == Environment.WALL
            ):
                replan_from = (
                    self.chain_path[self.chain_index - 1][0]
                    if self.chain_index > 0
                    else target_pos
                )
                self.chain_path = self.economy.plan_chain_path(
                    ct,
                    replan_from,
                    self.core_pos,
                )
                if self.chain_path and self.chain_path[0][0] == replan_from:
                    self.chain_path = self.chain_path[1:]
                self.chain_index = 0
                return

        # Waiting for resources -- don't count as stuck
        if not can_afford(ct, ct.get_conveyor_cost()):
            self.stuck_turns = 0
            return

        # Use movement manager to reach chain target
        self.movement.move_to(ct, target_pos)

        if self.stuck_turns > 50:
            self._finish_chain()
            self.stuck_turns = 0

    def _do_return_to_core(self, ct: Controller) -> None:
        if self.core_pos is None:
            self.state = BuilderState.EXPLORING
            return

        my_pos = ct.get_position()
        if my_pos.distance_squared(self.core_pos) <= 18:
            self.state = BuilderState.EXPLORING
            return

        best_ore = self._pick_best_known_ore(ct, self.core_pos)
        if best_ore is not None:
            self.target_ore = best_ore
            self.state = BuilderState.PATH_TO_ORE
            return

        self.movement.move_to(ct, self.core_pos)

    # -- Chain helpers --------------------------------------------------------

    def _start_chain(self, ct: Controller, harvester_pos: Position) -> None:
        if self.core_pos is None:
            self.state = BuilderState.EXPLORING
            return
        self.chain_path = self.economy.plan_chain_path(ct, harvester_pos, self.core_pos)
        # Skip harvester tile (can't build conveyor on it)
        if self.chain_path and self.chain_path[0][0] == harvester_pos:
            self.chain_path = self.chain_path[1:]
        self.chain_index = 0
        self.state = (
            BuilderState.BUILD_CONVEYOR if self.chain_path else BuilderState.EXPLORING
        )

    def _finish_chain(self) -> None:
        self.chain_path = []
        self.chain_index = 0
        self.state = BuilderState.EXPLORING

    # -- Movement helpers -----------------------------------------------------

    def _pick_explore_target(self, ct: Controller) -> Position:
        w = ct.get_map_width()
        h = ct.get_map_height()
        core = self.core_pos or Position(w // 2, h // 2)

        # Build and cache explore grid on first use
        if self._explore_grid is None:
            GRID_SPACING = 8
            targets = []
            for gx in range(GRID_SPACING // 2, w, GRID_SPACING):
                for gy in range(GRID_SPACING // 2, h, GRID_SPACING):
                    targets.append(Position(gx, gy))
            targets.sort(key=lambda p: p.distance_squared(core))
            self._explore_grid = targets

        my_pos = self.last_pos or core
        targets = self._explore_grid
        for _ in range(len(targets)):
            idx = self.explore_sector % len(targets)
            self.explore_sector += 1
            target = targets[idx]
            if my_pos.distance_squared(target) < 9:
                continue
            return target

        return Position(w // 2, h // 2)

    def _scan_for_ore(self, ct: Controller) -> None:
        """Scan visible tiles and remember any ore deposits.
        If symmetry is confirmed, also add mirrored ore positions."""
        for pos in ct.get_nearby_tiles():
            env = ct.get_tile_env(pos)
            if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            if ct.get_tile_building_id(pos) is not None:
                continue
            if pos not in self._known_ore_set:
                self.known_ores.append(pos)
                self._known_ore_set.add(pos)

        # Mirror known ores via symmetry (only ores closer to our core than original)
        if self.symmetry.get_confirmed() is not None and self.core_pos is not None:
            current_ores = list(self.known_ores)
            mirrored = self.symmetry.mirror_ore_list(current_ores)
            for i, mpos in enumerate(mirrored):
                if mpos in self._known_ore_set or mpos in self._mirror_checked:
                    continue
                orig = current_ores[i]
                if mpos.distance_squared(self.core_pos) >= orig.distance_squared(
                    self.core_pos,
                ):
                    continue
                if not ct.is_in_vision(mpos):
                    self.known_ores.append(mpos)
                    self._known_ore_set.add(mpos)
                else:
                    self._mirror_checked.add(mpos)

    def _pick_best_known_ore(
        self,
        ct: Controller,
        core_pos: Position,
    ) -> Position | None:
        """Pick the best ore from known_ores, pruning stale entries."""
        best_pos = None
        best_score = -1.0
        still_valid = []

        for pos in self.known_ores:
            if ct.is_in_vision(pos):
                if ct.get_tile_building_id(pos) is not None:
                    continue
                env = ct.get_tile_env(pos)
                if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                    continue
            still_valid.append(pos)

            dist_sq = pos.distance_squared(core_pos)
            score = 1.0 / (dist_sq + 1)
            if (
                ct.is_in_vision(pos)
                and ct.get_tile_env(pos) == Environment.ORE_TITANIUM
            ) and ct.get_current_round() < 200:
                score *= 1.5
            if score > best_score:
                best_score = score
                best_pos = pos

        self.known_ores = still_valid
        self._known_ore_set = set(still_valid)
        return best_pos

    def _move_adjacent_to(self, ct: Controller, target: Position) -> bool:
        """Greedy move toward target, building a road if needed."""
        my_pos = ct.get_position()
        best_dir = None
        best_dist = my_pos.distance_squared(target)

        for d in DIRECTIONS:
            new_pos = my_pos.add(d)
            dist = new_pos.distance_squared(target)
            if dist < best_dist and ct.can_move(d):
                best_dir = d
                best_dist = dist

        if best_dir is not None:
            ct.move(best_dir)
            return True

        if ct.get_action_cooldown() == 0:
            best_dir = None
            best_dist = my_pos.distance_squared(target)
            for d in DIRECTIONS:
                new_pos = my_pos.add(d)
                dist = new_pos.distance_squared(target)
                if dist < best_dist and ct.can_build_road(new_pos):
                    best_dir = d
                    best_dist = dist
            if best_dir is not None:
                ct.build_road(my_pos.add(best_dir))
                if ct.can_move(best_dir):
                    ct.move(best_dir)
                    return True

        return False


"""Parasitic gunner rush — simple version.

Every rush builder does the same thing:
1. Navigate to enemy core
2. If standing on an enemy conveyor near core: self-destruct (create gap)
3. If can build gunner on adjacent empty tile: build it
4. Otherwise: move closer and try again

No coordination needed. Every rush builder is the same role.
"""

from cambc import Controller, Position

GUNNER_RANGE_SQ = 13
SETUP_DIST_SQ = 36
MAX_NAVIGATE_ROUNDS = 300


class RushManager:
    def __init__(self, role: str = "rush") -> None:
        self.enemy_core_pos: Position | None = None
        self.phase: str = "navigate"
        self.navigate_rounds: int = 0
        self.gave_up: bool = False
        self._found_real_core: bool = False
        self._setup_rounds: int = 0
        self._built_gunner: bool = False

    def estimate_enemy_core(self, ct, our_core_pos, symmetry):
        if symmetry is not None:
            m = symmetry.mirror_position(our_core_pos)
            if m is not None:
                return m
        return None

    def _scan_for_enemy_core(self, ct):
        my_team = ct.get_team()
        for eid in ct.get_nearby_entities():
            if (
                ct.get_entity_type(eid) == EntityType.CORE
                and ct.get_team(eid) != my_team
            ):
                return ct.get_position(eid)
        return None

    def play(self, ct, movement, core_pos, symmetry):
        if self.gave_up:
            return False

        real_core = self._scan_for_enemy_core(ct)
        if real_core is not None and not self._found_real_core:
            self.enemy_core_pos = real_core
            self._found_real_core = True

        if self.enemy_core_pos is None:
            est = self.estimate_enemy_core(ct, core_pos, symmetry)
            if est is None:
                w, h = ct.get_map_width(), ct.get_map_height()
                movement.move_to(ct, Position(w // 2, h // 2))
                return True
            self.enemy_core_pos = est

        my_pos = ct.get_position()
        ct.draw_indicator_line(my_pos, self.enemy_core_pos, 255, 0, 0)

        if self.phase == "navigate":
            return self._do_navigate(ct, movement)
        if self.phase == "attack":
            return self._do_attack(ct, movement)
        return False

    def _do_navigate(self, ct, movement):
        self.navigate_rounds += 1
        if self.navigate_rounds > MAX_NAVIGATE_ROUNDS:
            self.gave_up = True
            return False

        my_pos = ct.get_position()
        if my_pos.distance_squared(self.enemy_core_pos) <= SETUP_DIST_SQ:
            self.phase = "attack"
            return self._do_attack(ct, movement)

        movement.move_to(ct, self.enemy_core_pos)
        return True

    def _do_attack(self, ct, movement) -> bool:
        """Simple loop: try to build gunner, or self-destruct on enemy conveyor, or reposition."""
        self._setup_rounds += 1
        my_pos = ct.get_position()

        if self._setup_rounds > 100:
            self.gave_up = True
            return False

        # Priority 1: Build a gunner if we can
        if ct.get_action_cooldown() == 0 and can_afford(ct, ct.get_gunner_cost()):
            placement = self._find_best_gunner_spot(ct)
            if placement is not None:
                pos, facing = placement
                ct.build_gunner(pos, facing)
                self._built_gunner = True
                # After building, stay and try to build more or heal
                return True

        # Priority 2: If on an enemy conveyor, self-destruct to create a gap
        if not self._built_gunner:
            bid = ct.get_tile_building_id(my_pos)
            if bid is not None:
                bteam = ct.get_team(bid)
                btype = ct.get_entity_type(bid)
                if (
                    bteam != ct.get_team()
                    and btype
                    in (
                        EntityType.CONVEYOR,
                        EntityType.SPLITTER,
                        EntityType.ARMOURED_CONVEYOR,
                    )
                    and my_pos.distance_squared(self.enemy_core_pos) <= 8
                ):
                    ct.self_destruct()
                    return False  # Dead

        # Priority 3: Walk onto enemy conveyor for self-destruct
        if not self._built_gunner and self._move_onto_enemy_conveyor(ct):
            return True

        # Priority 4: Get closer to core
        if my_pos.distance_squared(self.enemy_core_pos) > 4:
            movement.move_to(ct, self.enemy_core_pos)
        else:
            self._try_reposition(ct, movement)

        return True

    def _find_best_gunner_spot(self, ct):
        """Find adjacent tile for a gunner. Just place it close to enemy core."""
        my_pos = ct.get_position()
        best = None
        best_dist = 999

        for d in DIRECTIONS:
            tile = my_pos.add(d)
            dist = tile.distance_squared(self.enemy_core_pos)
            if dist > 8:  # Adjacent to 3x3 core footprint
                continue

            facing = tile.direction_to(self.enemy_core_pos)
            if facing == Direction.CENTRE:
                facing = Direction.NORTH

            if ct.can_build_gunner(tile, facing) and dist < best_dist:
                best_dist = dist
                best = (tile, facing)

        return best

    def _move_onto_enemy_conveyor(self, ct) -> bool:
        """Walk onto a nearby enemy conveyor for self-destruct next turn."""
        my_pos = ct.get_position()
        my_team = ct.get_team()

        for d in DIRECTIONS:
            new_pos = my_pos.add(d)
            if new_pos.distance_squared(self.enemy_core_pos) > 10:
                continue
            if not ct.can_move(d):
                continue
            bid = ct.get_tile_building_id(new_pos)
            if bid is None:
                continue
            if ct.get_team(bid) == my_team:
                continue
            if ct.get_entity_type(bid) in (
                EntityType.CONVEYOR,
                EntityType.SPLITTER,
                EntityType.ARMOURED_CONVEYOR,
            ):
                ct.move(d)
                return True
        return False

    def _try_reposition(self, ct, movement) -> None:
        my_pos = ct.get_position()
        for d in DIRECTIONS:
            new_pos = my_pos.add(d)
            if new_pos.distance_squared(self.enemy_core_pos) > 10:
                continue
            if ct.can_move(d):
                ct.move(d)
                return
            if ct.get_action_cooldown() == 0 and ct.can_build_road(new_pos):
                ct.build_road(new_pos)
                if ct.can_move(d):
                    ct.move(d)
                return


from cambc import Controller, Position
from utils import ALL_SPAWN_DIRS, MapSize, classify_map

MIN_ECONOMY_BUILDERS = 3
MIN_RUSH_ROUND = 100
MAX_RUSH_BUILDERS = 18
MIN_RUSH_TI = 100
RUSH_SPAWN_GAP = 3  # Min rounds between rush spawns


class CoreHandler:
    def __init__(self) -> None:
        self.builders_spawned: int = 0
        self.rush_builders_spawned: int = 0
        self.economy: EconomyManager = EconomyManager()
        self.symmetry: SymmetryDetector = SymmetryDetector()
        self.last_rush_round: int = 0

    def init_turn(self, ct: Controller) -> None:
        self.symmetry.update(ct)

    def play(self, ct: Controller) -> None:
        if not self._should_spawn(ct):
            return

        # Decide if next builder should be a rusher
        is_rush = self._should_spawn_rusher(ct)

        if is_rush:
            spawn_pos = self._pick_rush_spawn_pos(ct)
        else:
            spawn_pos = self._pick_spawn_pos(ct)

        if spawn_pos is not None and ct.can_spawn(spawn_pos):
            # Place rush marker BEFORE spawning (marker doesn't use action cooldown)
            if is_rush:
                # Place rush marker nearby. Core tiles can't hold markers,
                # so we search all tiles within core action radius (r^2=8)
                ct.get_position()
                # Try the spawn position first, then scan outward
                candidates = [spawn_pos]
                # Add all tiles within action radius, sorted by distance to spawn
                for tile in ct.get_nearby_tiles(8):
                    if tile != spawn_pos:
                        candidates.append(tile)
                candidates.sort(key=lambda p: p.distance_squared(spawn_pos))
                marker_val = RUSH_MARKER_VALUE
                for mpos in candidates:
                    if ct.can_place_marker(mpos):
                        ct.place_marker(mpos, marker_val)
                        break

            ct.spawn_builder(spawn_pos)
            self.builders_spawned += 1
            if is_rush:
                self.rush_builders_spawned += 1
                self.last_rush_round = ct.get_current_round()

    def end_turn(self, ct: Controller) -> None:
        pass

    def _should_spawn(self, ct: Controller) -> bool:
        if ct.get_action_cooldown() != 0:
            return False
        if not can_afford(ct, ct.get_builder_bot_cost()):
            return False

        # Phase 1: 2 builders to bootstrap economy
        if ct.get_current_round() < 50:
            return self.builders_spawned < 2

        ti, _ = ct.get_global_resources()

        # Check if we should spawn a rush builder (high Ti threshold)
        if self._should_spawn_rusher(ct):
            return True  # Rush conditions already check Ti >= MIN_RUSH_TI

        # Economy spawning: need Ti > 200
        if ti < 200:
            return False

        max_builders = {
            MapSize.SMALL: 4,
            MapSize.MEDIUM: 6,
            MapSize.LARGE: 8,
        }[classify_map(ct)]

        # Economy builders only (rush builders don't count against economy limit)
        economy_builders = self.builders_spawned - self.rush_builders_spawned
        return economy_builders < max_builders

    def _should_spawn_rusher(self, ct: Controller) -> bool:
        if self.rush_builders_spawned >= MAX_RUSH_BUILDERS:
            return False
        if ct.get_current_round() < MIN_RUSH_ROUND:
            return False
        # Prefer symmetry confirmed, but don't hard-block
        # Rush builder will handle unconfirmed symmetry by moving to center
        economy_builders = self.builders_spawned - self.rush_builders_spawned
        if economy_builders < MIN_ECONOMY_BUILDERS:
            return False
        # Space out rush spawns
        if ct.get_current_round() - self.last_rush_round < RUSH_SPAWN_GAP:
            return False
        ti, _ = ct.get_global_resources()
        return not ti < MIN_RUSH_TI

    def _pick_rush_spawn_pos(self, ct: Controller) -> Position | None:
        """Spawn rush builder toward estimated enemy core."""
        core_pos = ct.get_position()
        w = ct.get_map_width()
        h = ct.get_map_height()

        # Estimate enemy core position
        enemy_core = self.symmetry.mirror_position(core_pos)
        if enemy_core is None:
            # Default: rotational symmetry (just for spawn direction hint)
            enemy_core = Position(w - 1 - core_pos.x, h - 1 - core_pos.y)

        # Spawn toward enemy core
        spawn_dir = core_pos.direction_to(enemy_core)
        spawn_pos = core_pos.add(spawn_dir)
        if ct.can_spawn(spawn_pos):
            return spawn_pos

        # Try adjacent directions
        for d in [
            spawn_dir.rotate_left(),
            spawn_dir.rotate_right(),
            spawn_dir.rotate_left().rotate_left(),
            spawn_dir.rotate_right().rotate_right(),
        ]:
            spawn_pos = core_pos.add(d)
            if ct.can_spawn(spawn_pos):
                return spawn_pos

        # Fallback: any tile
        for d in ALL_SPAWN_DIRS:
            spawn_pos = core_pos.add(d)
            if ct.can_spawn(spawn_pos):
                return spawn_pos

        return None

    def _pick_spawn_pos(self, ct: Controller) -> Position | None:
        core_pos = ct.get_position()

        # Prefer spawning toward nearest ore
        best_ore = self.economy.get_best_ore(ct, core_pos)
        if best_ore is not None:
            spawn_pos = core_pos.add(core_pos.direction_to(best_ore))
            if ct.can_spawn(spawn_pos):
                return spawn_pos

        # Fallback: any available spawn tile (using cached constant)
        for d in ALL_SPAWN_DIRS:
            spawn_pos = core_pos.add(d)
            if ct.can_spawn(spawn_pos):
                return spawn_pos

        return None


from collections import deque

from cambc import Controller, Position
from utils import CARDINALS, best_cardinal_toward, direction_between

MAX_CHAIN_LEN = 40


class EconomyManager:
    def __init__(self) -> None:
        self.harvesters_built: int = 0

    def get_best_ore(self, ct: Controller, core_pos: Position) -> Position | None:
        best_pos = None
        best_score = -1.0

        for pos in ct.get_nearby_tiles():
            env = ct.get_tile_env(pos)
            if env not in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            if ct.get_tile_building_id(pos) is not None:
                continue
            dist_sq = pos.distance_squared(core_pos)
            # Score: closer to core = better; titanium preferred early
            score = 1.0 / (dist_sq + 1)
            if env == Environment.ORE_TITANIUM and ct.get_current_round() < 200:
                score *= 1.5
            if score > best_score:
                best_score = score
                best_pos = pos

        return best_pos

    def try_build_harvester(self, ct: Controller, pos: Position) -> bool:
        if ct.can_build_harvester(pos):
            ct.build_harvester(pos)
            self.harvesters_built += 1
            return True
        return False

    def plan_chain_path(
        self,
        ct: Controller,
        start_pos: Position,
        core_pos: Position,
        goal_dist_sq: int = 5,
    ) -> list[tuple[Position, Direction]]:
        """BFS from start_pos to a tile near target (dist^2<=goal_dist_sq).

        Cardinal-only movement. Walls in vision are impassable.
        Out-of-vision tiles are treated as passable (optimistic).
        Returns [(position, facing_direction), ...] ordered start->target.
        """
        w = ct.get_map_width()
        h = ct.get_map_height()

        parent: dict[Position, Position | None] = {start_pos: None}
        queue: deque[Position] = deque([start_pos])
        goal: Position | None = None

        while queue:
            if len(parent) > MAX_CHAIN_LEN * 8:
                break  # safety cap

            current = queue.popleft()

            if current.distance_squared(core_pos) <= goal_dist_sq:
                goal = current
                break

            for d in CARDINALS:
                delta = d.delta()
                nx, ny = current.x + delta[0], current.y + delta[1]
                next_pos = Position(nx, ny)

                if next_pos in parent:
                    continue
                if not (0 <= nx < w and 0 <= ny < h):
                    continue

                if ct.is_in_vision(next_pos):
                    if ct.get_tile_env(next_pos) == Environment.WALL:
                        continue
                    bid = ct.get_tile_building_id(next_pos)
                    if bid is not None:
                        btype = ct.get_entity_type(bid)
                        if btype not in (EntityType.ROAD, EntityType.CONVEYOR):
                            continue

                parent[next_pos] = current
                queue.append(next_pos)

        if goal is None:
            return []

        # Reconstruct path
        positions: list[Position] = []
        cur: Position | None = goal
        while cur is not None:
            positions.append(cur)
            cur = parent[cur]
        positions.reverse()

        # Convert to (position, facing_direction) tuples
        path: list[tuple[Position, Direction]] = []
        for i in range(len(positions) - 1):
            face_dir = direction_between(positions[i], positions[i + 1])
            path.append((positions[i], face_dir))

        # Last tile: face toward core, but verify the target tile is passable
        if positions:
            last = positions[-1]
            face_dir = best_cardinal_toward(last, core_pos)

            # Verify the tile we'd push resources to isn't a wall
            target_tile = last.add(face_dir)
            if (
                ct.is_in_vision(target_tile)
                and ct.get_tile_env(target_tile) == Environment.WALL
            ):
                # Try other cardinal directions toward core
                best_alt = None
                best_alt_dist = 999
                for d in CARDINALS:
                    check = last.add(d)
                    if (
                        ct.is_in_vision(check)
                        and ct.get_tile_env(check) == Environment.WALL
                    ):
                        continue
                    dist = check.distance_squared(core_pos)
                    if dist < best_alt_dist:
                        best_alt_dist = dist
                        best_alt = d
                if best_alt is not None:
                    face_dir = best_alt

            path.append((last, face_dir))

        return path

    def try_build_chain_segment(
        self,
        ct: Controller,
        pos: Position,
        face_dir: Direction,
    ) -> bool:
        if ct.can_build_conveyor(pos, face_dir):
            ct.build_conveyor(pos, face_dir)
            return True
        return False


from builder import BuilderHandler
from cambc import Controller
from core import CoreHandler
from turrets import BreachHandler, GunnerHandler, LauncherHandler, SentinelHandler


class Player:
    def __init__(self) -> None:
        self.handler = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()

        if self.handler is None:
            if etype == EntityType.CORE:
                self.handler = CoreHandler()
            elif etype == EntityType.BUILDER_BOT:
                self.handler = BuilderHandler()
            elif etype == EntityType.GUNNER:
                self.handler = GunnerHandler()
            elif etype == EntityType.SENTINEL:
                self.handler = SentinelHandler()
            elif etype == EntityType.BREACH:
                self.handler = BreachHandler()
            elif etype == EntityType.LAUNCHER:
                self.handler = LauncherHandler()
            else:
                return

        self.handler.init_turn(ct)
        self.handler.play(ct)
        self.handler.end_turn(ct)


from cambc import Controller, Direction, Position
from pathfinder import Pathfinder


class MovementManager:
    """Wraps Pathfinder with road-building and movement execution.

    Responsibilities:
    - Call Pathfinder for direction
    - If direction is passable, move there
    - If blocked but can build road, build road then move
    - Handle action cooldown checks
    - Future: danger zone avoidance (stub)
    """

    def __init__(self) -> None:
        self.pathfinder = Pathfinder()

    def move_to(self, ct: Controller, target: Position) -> bool:
        """Try to move one step toward target. Returns True if moved.

        Will build a road if the recommended direction is blocked but buildable.
        """
        direction = self.pathfinder.get_direction(ct, target)
        if direction is None:
            return False

        return self._execute_move(ct, direction)

    def _execute_move(self, ct: Controller, direction: Direction) -> bool:
        """Execute a move in the given direction, building a road if needed."""
        # If already passable, just move
        if ct.can_move(direction):
            ct.move(direction)
            return True

        # If tile is buildable, try building a road to walk on
        new_pos = ct.get_position().add(direction)
        if ct.get_action_cooldown() == 0 and ct.can_build_road(new_pos):
            ct.build_road(new_pos)
            if ct.can_move(direction):
                ct.move(direction)
                return True

        return False

    def is_dangerous(self, ct: Controller, pos: Position) -> bool:
        """Stub for future danger zone avoidance.

        TODO: Check for enemy turret ranges, breach splash zones, etc.
        """
        return False


from cambc import Controller, Direction, Position
from utils import DIR_TO_ORD, INF


class BugNav:
    """Pure BugNav pathfinding. Returns Direction | None. Never builds or moves.

    Handles state desync: if the caller doesn't execute the returned direction
    (e.g., can't afford road), BugNav detects this on the next call and
    restores its state.
    """

    # Max turns to trace before resetting (longer than old 15, still finite)
    MAX_TRACE_TURNS: int = 30

    def __init__(self) -> None:
        self.target: Position | None = None
        self.rotate_right: bool | None = None
        self.last_obstacle_dir: Direction | None = None
        self.closest_dist: int = INF
        self.min_location_to_target: Position | None = None
        self.visited_states: set[int] = set()
        self.turns_moving_to_obstacle: int = 0
        self.tracing_turns: int = 0
        self._map_w: int = 0
        self._map_h: int = 0

        # State snapshot for rollback on failed moves
        self._last_pos: Position | None = None
        self._saved_obstacle_dir: Direction | None = None
        self._saved_closest_dist: int = INF
        self._saved_min_loc: Position | None = None

    @property
    def is_tracing(self) -> bool:
        """Tracing is active when we have a remembered obstacle direction."""
        return self.last_obstacle_dir is not None

    def navigate(self, ct: Controller, target: Position) -> Direction | None:
        """Return the best direction to move toward target, or None if stuck.

        Pure pathfinding only -- never calls move(), build_road(), or any action.
        """
        # Cache map dimensions on first call
        if self._map_w == 0:
            self._map_w = ct.get_map_width()
            self._map_h = ct.get_map_height()

        my_pos = ct.get_position()

        # Detect if last returned direction was NOT executed (bot didn't move)
        if self._last_pos is not None and my_pos == self._last_pos:
            # Bot didn't move -- restore saved state
            self.last_obstacle_dir = self._saved_obstacle_dir
            self.closest_dist = self._saved_closest_dist
            self.min_location_to_target = self._saved_min_loc

        # Handle target changes
        if target != self.target:
            if self.target is not None and self.target.distance_squared(target) < 4:
                self._soft_reset(my_pos, target)
            else:
                self._hard_reset()
            self.target = target

        current_dist = my_pos.distance_squared(target)

        if current_dist == 0:
            self._last_pos = my_pos
            return None

        # Save state before any modifications
        self._saved_obstacle_dir = self.last_obstacle_dir
        self._saved_closest_dist = self.closest_dist
        self._saved_min_loc = self.min_location_to_target

        # If not currently tracing, try greedy movement
        if not self.is_tracing:
            greedy_dir = self._try_greedy(ct, target)
            if greedy_dir is not None:
                new_pos = my_pos.add(greedy_dir)
                new_dist = new_pos.distance_squared(target)
                if new_dist < self.closest_dist:
                    self.closest_dist = new_dist
                    self.min_location_to_target = new_pos
                self._last_pos = my_pos
                return greedy_dir
            # Greedy failed: start tracing
            blocked_dir = my_pos.direction_to(target)
            self.last_obstacle_dir = blocked_dir
            self.visited_states.clear()
            self.turns_moving_to_obstacle = 0
            self.tracing_turns = 0
            self._pick_rotation(ct, blocked_dir, target)

        # Tracing mode
        if self.is_tracing:
            self.tracing_turns += 1

            # Timeout: reset after too many tracing turns
            if self.tracing_turns > self.MAX_TRACE_TURNS:
                self._hard_reset()
                result = self._try_greedy(ct, target)
                self._last_pos = my_pos
                return result

            # Check for loops
            self._check_state(ct)

            # If reset by _check_state (loop detected), try greedy
            if not self.is_tracing:
                result = self._try_greedy(ct, target)
                self._last_pos = my_pos
                return result

            # Try tracing move
            trace_dir = self._trace_move(ct, target)

            if trace_dir is not None:
                new_pos = my_pos.add(trace_dir)
                new_dist = new_pos.distance_squared(target)

                # Track if we're moving toward the obstacle (passable now)
                if self.last_obstacle_dir is not None:
                    obstacle_pos = my_pos.add(self.last_obstacle_dir)
                    if new_pos == obstacle_pos:
                        self.turns_moving_to_obstacle += 1
                    else:
                        self.turns_moving_to_obstacle = 0

                    # If obstacle has cleared (e.g. unit moved away), reset tracing
                    if self.turns_moving_to_obstacle >= 3:
                        self._hard_reset()
                        self._last_pos = my_pos
                        return trace_dir

                # Check if we can exit tracing (closer than ever before)
                if new_dist < self.closest_dist:
                    self.closest_dist = new_dist
                    self.min_location_to_target = new_pos
                    self.last_obstacle_dir = None  # exit tracing
                    self.visited_states.clear()
                    self.turns_moving_to_obstacle = 0
                    self.tracing_turns = 0

                self._last_pos = my_pos
                return trace_dir

            # No tracing direction found (completely stuck)
            self._last_pos = my_pos
            return None

        self._last_pos = my_pos
        return None

    def _try_greedy(self, ct: Controller, target: Position) -> Direction | None:
        """Try greedy movement toward target. Returns direction or None."""
        my_pos = ct.get_position()
        direct_dir = my_pos.direction_to(target)
        current_dist = my_pos.distance_squared(target)

        # Try direct direction
        if self._can_pass(ct, direct_dir):
            return direct_dir

        # Try one rotation right
        right = direct_dir.rotate_right()
        new_pos = my_pos.add(right)
        if new_pos.distance_squared(target) < current_dist and self._can_pass(
            ct,
            right,
        ):
            return right

        # Try one rotation left
        left = direct_dir.rotate_left()
        new_pos = my_pos.add(left)
        if new_pos.distance_squared(target) < current_dist and self._can_pass(ct, left):
            return left

        return None

    def _can_pass(self, ct: Controller, direction: Direction) -> bool:
        """Check if a direction is passable or could be made passable.

        Returns True if:
        - The tile already has a road/conveyor/core (is_tile_passable), OR
        - The tile is empty (no building, no wall) and could have a road built

        This lets BugNav pathfind through unbuilt areas. MovementManager
        handles the actual road building.
        """
        if direction == Direction.CENTRE:
            return False
        pos = ct.get_position().add(direction)
        # Bounds check
        if not (0 <= pos.x < self._map_w and 0 <= pos.y < self._map_h):
            return False
        if not ct.is_in_vision(pos):
            return False
        # Already passable (road, conveyor, allied core, no other builder)
        if ct.is_tile_passable(pos):
            return True
        # Empty tile = could build a road there (not a wall, no building)
        return bool(ct.is_tile_empty(pos))

    def _pick_rotation(
        self,
        ct: Controller,
        blocked_dir: Direction,
        target: Position,
    ) -> None:
        """Pick whether to trace right or left around the obstacle."""
        my_pos = ct.get_position()

        # Try rotating right from blocked_dir
        best_right_dist = INF
        d = blocked_dir
        for _ in range(8):
            d = d.rotate_right()
            if self._can_pass(ct, d):
                test_pos = my_pos.add(d)
                best_right_dist = test_pos.distance_squared(target)
                break

        # Try rotating left from blocked_dir
        best_left_dist = INF
        d = blocked_dir
        for _ in range(8):
            d = d.rotate_left()
            if self._can_pass(ct, d):
                test_pos = my_pos.add(d)
                best_left_dist = test_pos.distance_squared(target)
                break

        # Pick the rotation that leads closer to target
        self.rotate_right = best_right_dist <= best_left_dist

    def _trace_move(self, ct: Controller, target: Position) -> Direction | None:
        """Follow the obstacle wall. Returns direction or None.

        Uses 16 iterations (up from 8) to handle corner cases at map edges.
        """
        if self.last_obstacle_dir is None:
            return None

        d = self.last_obstacle_dir
        for _ in range(16):
            d = d.rotate_left() if self.rotate_right else d.rotate_right()

            if self._can_pass(ct, d):
                # Update last_obstacle_dir for next iteration
                if self.rotate_right:
                    self.last_obstacle_dir = d.rotate_right().rotate_right()
                else:
                    self.last_obstacle_dir = d.rotate_left().rotate_left()
                return d

            # This direction is blocked -> becomes potential obstacle direction
            self.last_obstacle_dir = d

        return None

    def _check_state(self, ct: Controller) -> None:
        """Detect loops by checking if we've been in this exact state before."""
        if self.last_obstacle_dir is None:
            return
        my_pos = ct.get_position()
        obstacle_ord = DIR_TO_ORD[self.last_obstacle_dir]
        state = (
            (my_pos.x << 17)
            | (my_pos.y << 5)
            | (obstacle_ord << 1)
            | (1 if self.rotate_right else 0)
        )

        if state in self.visited_states:
            self._hard_reset()
        else:
            self.visited_states.add(state)

    def _soft_reset(self, my_pos: Position, new_target: Position) -> None:
        """Reset for nearby target change. Preserves rotation preference."""
        new_dist = my_pos.distance_squared(new_target)
        # Use historical best position if available
        if self.min_location_to_target is not None:
            hist_dist = self.min_location_to_target.distance_squared(new_target)
            self.closest_dist = min(new_dist, hist_dist)
        else:
            self.closest_dist = new_dist
        self.last_obstacle_dir = None
        self.min_location_to_target = None
        self.visited_states.clear()
        self.turns_moving_to_obstacle = 0
        self.tracing_turns = 0
        # rotate_right is preserved

    def _hard_reset(self) -> None:
        """Full reset of all navigation state."""
        self.rotate_right = None
        self.last_obstacle_dir = None
        self.closest_dist = INF
        self.min_location_to_target = None
        self.visited_states.clear()
        self.turns_moving_to_obstacle = 0
        self.tracing_turns = 0


from cambc import Controller, Direction, Position
from nav import BugNav


class LocalBFS:
    """BFS within vision range using only already-passable tiles.

    Returns the best first-step direction toward target through existing
    infrastructure (roads, conveyors, allied core). Does NOT consider
    tiles where roads could be built -- that's BugNav's responsibility.
    """

    def __init__(self) -> None:
        self._cached_dir: Direction | None = None
        self._cached_target: Position | None = None
        self._cached_pos: Position | None = None
        self._cache_round: int = -1

    def get_best_direction(self, ct: Controller, target: Position) -> Direction | None:
        """BFS from current position within visible passable tiles toward target.

        Returns the first-step Direction, or None if target not reachable
        through existing passable tiles within vision.
        Caches result for 2 turns if position and target unchanged.
        """
        my_pos = ct.get_position()
        current_round = ct.get_current_round()

        # Use cached result if position and target unchanged and cache fresh
        if (
            self._cached_target == target
            and self._cached_pos == my_pos
            and current_round - self._cache_round <= 2
        ):
            return self._cached_dir

        result = self._bfs(ct, my_pos, target)

        # Cache the result
        self._cached_dir = result
        self._cached_target = target
        self._cached_pos = my_pos
        self._cache_round = current_round

        return result

    def _bfs(
        self,
        ct: Controller,
        start: Position,
        target: Position,
    ) -> Direction | None:
        """Run bounded BFS within vision range using only passable tiles.

        Builder vision r^2 = 20, so roughly 60 visible tiles.
        We limit BFS to 80 nodes to stay within 2ms CPU budget.
        Only considers already-passable tiles (not empty buildable tiles).
        """
        if start == target:
            return None

        w = ct.get_map_width()
        h = ct.get_map_height()

        # first_step tracks which initial direction led to each position
        first_step: dict[Position, Direction] = {}
        visited: set[Position] = {start}
        queue: deque[Position] = deque()

        # Seed BFS with adjacent passable tiles
        for d in DIRECTIONS:
            neighbor = start.add(d)
            if not (0 <= neighbor.x < w and 0 <= neighbor.y < h):
                continue
            if not ct.is_in_vision(neighbor):
                continue
            if ct.is_tile_passable(neighbor):
                if neighbor == target:
                    return d
                first_step[neighbor] = d
                visited.add(neighbor)
                queue.append(neighbor)

        nodes_visited = 0
        max_nodes = 80  # Safety cap for 2ms CPU limit

        while queue and nodes_visited < max_nodes:
            current = queue.popleft()
            nodes_visited += 1
            step = first_step[current]

            for d in DIRECTIONS:
                neighbor = current.add(d)
                if neighbor in visited:
                    continue
                if not (0 <= neighbor.x < w and 0 <= neighbor.y < h):
                    continue
                if not ct.is_in_vision(neighbor):
                    continue
                if not ct.is_tile_passable(neighbor):
                    continue

                if neighbor == target:
                    return step

                first_step[neighbor] = step
                visited.add(neighbor)
                queue.append(neighbor)

        return None


class Pathfinder:
    """Orchestrates LocalBFS + BugNav.

    Tries LocalBFS first for optimal pathing through existing infrastructure.
    Falls back to BugNav for navigation through unbuilt terrain.
    """

    def __init__(self) -> None:
        self.local_bfs = LocalBFS()
        self.bug_nav = BugNav()

    def get_direction(self, ct: Controller, target: Position) -> Direction | None:
        """Get the best direction to move toward target.

        Returns Direction or None. Never calls any actions.
        """
        my_pos = ct.get_position()
        if my_pos == target:
            return None

        # Try LocalBFS first (optimal within vision, existing paths only)
        bfs_dir = self.local_bfs.get_best_direction(ct, target)
        if bfs_dir is not None:
            # BFS found a path through existing infrastructure.
            # Use it as an override but keep BugNav state intact
            # so it can resume properly if BFS fails next turn.
            return bfs_dir

        # Fall back to BugNav (considers buildable tiles too)
        return self.bug_nav.navigate(ct, target)


from cambc import Controller, Position


class SymmetryDetector:
    """Detects map symmetry by eliminating impossible hypotheses.

    Battlecode maps are always symmetric in one of three ways:
    - HORIZONTAL: mirror across vertical axis -> (W-1-x, y)
    - VERTICAL: mirror across horizontal axis -> (x, H-1-y)
    - ROTATIONAL: 180-degree rotation -> (W-1-x, H-1-y)

    Each turn, visible tiles are checked against each hypothesis.
    If a tile is WALL but its mirror is known passable (or vice versa),
    that hypothesis is eliminated. Once exactly one remains, symmetry
    is confirmed and can be used to mirror ore positions.
    """

    def __init__(self) -> None:
        # Three hypotheses: horizontal, vertical, rotational
        self.possible: list[bool] = [True, True, True]
        # Known tile types for cross-checking
        self.walls: set[tuple[int, int]] = set()
        self.passable: set[tuple[int, int]] = set()
        # Cache map dimensions (set on first update)
        self._map_w: int = 0
        self._map_h: int = 0
        # Track already-processed tiles to avoid redundant work
        self._processed: set[tuple[int, int]] = set()

    def update(self, ct: Controller) -> None:
        """Process newly visible tiles and eliminate impossible symmetries."""
        if self._map_w == 0:
            self._map_w = ct.get_map_width()
            self._map_h = ct.get_map_height()

        # Early exit if already confirmed
        if sum(self.possible) <= 1:
            return

        w = self._map_w
        h = self._map_h

        for pos in ct.get_nearby_tiles():
            key = (pos.x, pos.y)
            if key in self._processed:
                continue
            self._processed.add(key)

            env = ct.get_tile_env(pos)
            is_wall = env == Environment.WALL

            if is_wall:
                self.walls.add(key)
            else:
                self.passable.add(key)

            # Check each still-possible hypothesis
            # 0 = horizontal, 1 = vertical, 2 = rotational
            mirrors = (
                (w - 1 - pos.x, pos.y),  # horizontal
                (pos.x, h - 1 - pos.y),  # vertical
                (w - 1 - pos.x, h - 1 - pos.y),  # rotational
            )

            for i in range(3):
                if not self.possible[i]:
                    continue
                mk = mirrors[i]
                if is_wall:
                    # This tile is wall; if mirror is known passable -> eliminate
                    if mk in self.passable:
                        self.possible[i] = False
                # This tile is passable; if mirror is known wall -> eliminate
                elif mk in self.walls:
                    self.possible[i] = False

    def get_confirmed(self) -> str | None:
        """Return confirmed symmetry type, or None if still ambiguous.

        Returns "horizontal", "vertical", or "rotational".
        """
        if sum(self.possible) != 1:
            return None
        if self.possible[0]:
            return "horizontal"
        if self.possible[1]:
            return "vertical"
        return "rotational"

    def mirror_position(self, pos: Position) -> Position | None:
        """Mirror a position using confirmed symmetry. Returns None if not confirmed."""
        sym = self.get_confirmed()
        if sym is None:
            return None
        w = self._map_w
        h = self._map_h
        if sym == "horizontal":
            return Position(w - 1 - pos.x, pos.y)
        if sym == "vertical":
            return Position(pos.x, h - 1 - pos.y)
        # rotational
        return Position(w - 1 - pos.x, h - 1 - pos.y)

    def mirror_ore_list(self, ores: list[Position]) -> list[Position]:
        """Mirror all ore positions using confirmed symmetry.

        Returns only the mirrored positions (not the originals).
        Returns empty list if symmetry not yet confirmed.
        """
        sym = self.get_confirmed()
        if sym is None:
            return []
        w = self._map_w
        h = self._map_h
        mirrored: list[Position] = []
        for pos in ores:
            if sym == "horizontal":
                mirrored.append(Position(w - 1 - pos.x, pos.y))
            elif sym == "vertical":
                mirrored.append(Position(pos.x, h - 1 - pos.y))
            else:  # rotational
                mirrored.append(Position(w - 1 - pos.x, h - 1 - pos.y))
        return mirrored


"""Turret handlers — each turret type gets its own Player instance.
The engine calls run() every round; we must call fire() explicitly."""

from cambc import Controller, Direction, Position


class GunnerHandler:
    def __init__(self) -> None:
        self._logged = False

    def init_turn(self, ct: Controller) -> None:
        pass

    def play(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        cooldown = ct.get_action_cooldown()
        ammo = ct.get_ammo_amount()
        target = ct.get_gunner_target()

        if rnd % 50 == 0 or (not self._logged and rnd > 260):
            self._logged = True
            can = ct.can_fire(target) if target else False
            print(
                f"[GUNNER R{rnd}] cd={cooldown} ammo={ammo} target={target} can_fire={can}",
            )

        if cooldown > 0:
            return
        if target is not None and ct.can_fire(target):
            ct.fire(target)
            print(f"[GUNNER R{rnd}] FIRED at {target}!")

    def end_turn(self, ct: Controller) -> None:
        pass


class SentinelHandler:
    def init_turn(self, ct: Controller) -> None:
        pass

    def play(self, ct: Controller) -> None:
        if ct.get_action_cooldown() > 0:
            return
        # Sentinel fires along its facing direction at the closest target
        # Use same approach: scan facing direction for non-empty tiles
        my_pos = ct.get_position()
        facing = ct.get_direction()
        target = self._find_target_in_line(ct, my_pos, facing)
        if target is not None and ct.can_fire(target):
            ct.fire(target)

    def end_turn(self, ct: Controller) -> None:
        pass

    def _find_target_in_line(
        self,
        ct: Controller,
        pos: Position,
        facing: Direction,
    ) -> Position | None:
        delta = facing.delta()
        check = pos
        vision_sq = ct.get_vision_radius_sq()
        for _ in range(10):
            check = Position(check.x + delta[0], check.y + delta[1])
            if pos.distance_squared(check) > vision_sq:
                break
            if not ct.is_in_vision(check):
                break
            if not ct.is_tile_empty(check):
                return check
        return None


class BreachHandler:
    def init_turn(self, ct: Controller) -> None:
        pass

    def play(self, ct: Controller) -> None:
        if ct.get_action_cooldown() > 0:
            return
        my_pos = ct.get_position()
        facing = ct.get_direction()
        # Fire at closest non-empty tile in 180° cone
        target = self._find_target_in_cone(ct, my_pos, facing)
        if target is not None and ct.can_fire(target):
            ct.fire(target)

    def end_turn(self, ct: Controller) -> None:
        pass

    def _find_target_in_cone(
        self,
        ct: Controller,
        pos: Position,
        facing: Direction,
    ) -> Position | None:
        delta = facing.delta()
        check = pos
        attack_sq = 5
        for _ in range(5):
            check = Position(check.x + delta[0], check.y + delta[1])
            if pos.distance_squared(check) > attack_sq:
                break
            if not ct.is_in_vision(check):
                break
            if not ct.is_tile_empty(check):
                return check
        return None


class LauncherHandler:
    """Launcher picks up adjacent friendly builders and throws them toward enemy."""

    def init_turn(self, ct: Controller) -> None:
        pass

    def play(self, ct: Controller) -> None:
        # Launchers are passive for now — we'd need coordination with builders
        # to know where to throw. Future: scan for enemy buildings in range,
        # find adjacent friendly builder, throw toward enemy infrastructure.
        pass

    def end_turn(self, ct: Controller) -> None:
        pass


from enum import Enum

from cambc import Controller, Direction, Position

DIRECTIONS: list[Direction] = [d for d in Direction if d != Direction.CENTRE]
CARDINALS: list[Direction] = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
]

# Precomputed direction ordinals for fast lookup (avoids list(Direction).index())
DIR_TO_ORD: dict[Direction, int] = {d: i for i, d in enumerate(Direction)}

# Infinity constant for distance comparisons
INF: int = 999_999

# All spawn directions including CENTRE (cached for core.py)
ALL_SPAWN_DIRS: list[Direction] = [Direction.CENTRE, *DIRECTIONS]

RUSH_MARKER_VALUE: int = 0xDEAD_BEEF


class MapSize(Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


def classify_map(ct: Controller) -> MapSize:
    area = ct.get_map_width() * ct.get_map_height()
    if area < 625:
        return MapSize.SMALL
    if area < 1600:
        return MapSize.MEDIUM
    return MapSize.LARGE


def can_afford(ct: Controller, cost: tuple[int, int]) -> bool:
    ti, ax = ct.get_global_resources()
    return ti >= cost[0] and ax >= cost[1]


def find_core_pos(ct: Controller) -> Position | None:
    for eid in ct.get_nearby_entities():
        if (
            ct.get_entity_type(eid) == EntityType.CORE
            and ct.get_team(eid) == ct.get_team()
        ):
            return ct.get_position(eid)
    return None


def best_cardinal_toward(from_pos: Position, toward_pos: Position) -> Direction:
    """Pick the cardinal direction that best moves from_pos toward toward_pos."""
    dx = toward_pos.x - from_pos.x
    dy = toward_pos.y - from_pos.y
    if dx == 0 and dy == 0:
        return Direction.NORTH
    if abs(dx) >= abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    return Direction.SOUTH if dy > 0 else Direction.NORTH


def direction_between(from_pos: Position, to_pos: Position) -> Direction:
    """Get the Direction that goes from from_pos to to_pos (must be adjacent)."""
    dx = to_pos.x - from_pos.x
    dy = to_pos.y - from_pos.y
    for d in DIRECTIONS:
        delta = d.delta()
        if delta[0] == dx and delta[1] == dy:
            return d
    return best_cardinal_toward(from_pos, to_pos)


GUNNER_RANGE_SQ: int = 13


def estimate_enemy_core(ct: Controller, our_core_pos: Position, symmetry) -> Position:
    w = ct.get_map_width()
    h = ct.get_map_height()
    if symmetry is not None:
        mirrored = symmetry.mirror_position(our_core_pos)
        if mirrored is not None:
            return mirrored
    return Position(w - 1 - our_core_pos.x, h - 1 - our_core_pos.y)
