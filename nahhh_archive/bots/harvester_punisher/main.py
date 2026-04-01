from cambc import Controller, Direction, EntityType, Position

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
SPAWN_ORDER = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
]
DIR_TO_DELTA = {
    Direction.NORTH: (0, -1),
    Direction.NORTHEAST: (1, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTHEAST: (1, 1),
    Direction.SOUTH: (0, 1),
    Direction.SOUTHWEST: (-1, 1),
    Direction.WEST: (-1, 0),
    Direction.NORTHWEST: (-1, -1),
}
DELTA_TO_DIR = {delta: direction for direction, delta in DIR_TO_DELTA.items()}
WALKABLE_BUILDINGS = {
    EntityType.ROAD,
    EntityType.CONVEYOR,
    EntityType.SPLITTER,
    EntityType.BRIDGE,
    EntityType.ARMOURED_CONVEYOR,
}
SCOUT_STUCK_TURNS = 6


class Player:
    def __init__(self) -> None:
        self.num_spawned = 0
        self.core_pos: Position | None = None
        self.map_w: int | None = None
        self.map_h: int | None = None
        self.lane_offset: int | None = None
        self.scout_stage = 0
        self.stuck_turns = 0
        self.last_goal_dist: int | None = None
        self.prev_pos: Position | None = None
        self.goal: Position | None = None
        self.goal_mode: str | None = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)
        elif etype == EntityType.SENTINEL:
            self._run_sentinel(ct)

    def _run_core(self, ct: Controller) -> None:
        self.core_pos = ct.get_position()
        self.map_w = ct.get_map_width()
        self.map_h = ct.get_map_height()
        if self.num_spawned >= 4:
            return
        for direction in SPAWN_ORDER:
            spawn_pos = self.core_pos.add(direction)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1
                return

    def _run_builder(self, ct: Controller) -> None:
        self._ensure_core_pos(ct)

        target = self._nearest_enemy_harvester(ct)
        if target is None:
            goal = self._current_goal(ct, "outward", self._outward_goal(ct.get_position()))
            self._step_toward(ct, goal)
            return

        if self._has_friendly_sentinel_adjacent(ct, target):
            chip_tile = self._best_enemy_walkable_adjacent_to(ct, target)
            if chip_tile is not None:
                if chip_tile == ct.get_position():
                    if ct.can_fire(chip_tile):
                        ct.fire(chip_tile)
                    return
                goal = self._current_goal(ct, "chip", chip_tile)
                self._step_toward(ct, goal)
                return
            goal = self._current_goal(ct, "harvester", target)
            self._step_toward(ct, goal)
            return

        if self._try_build_adjacent_sentinel(ct, target):
            return

        chip_tile = self._best_enemy_walkable_adjacent_to(ct, target)
        if chip_tile is not None:
            if chip_tile == ct.get_position():
                if ct.can_fire(chip_tile):
                    ct.fire(chip_tile)
                return
            goal = self._current_goal(ct, "chip", chip_tile)
            self._step_toward(ct, goal)
            return

        goal = self._current_goal(ct, "harvester", target)
        self._step_toward(ct, goal)

    def _run_sentinel(self, ct: Controller) -> None:
        best = None
        best_key = None
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == ct.get_team():
                continue
            pos = ct.get_position(eid)
            etype = ct.get_entity_type(eid)
            if not ct.can_fire(pos):
                continue
            priority = 2
            if etype == EntityType.HARVESTER:
                priority = 0
            elif etype == EntityType.BUILDER_BOT:
                priority = 1
            key = (priority, ct.get_position().distance_squared(pos), pos.x, pos.y)
            if best_key is None or key < best_key:
                best = pos
                best_key = key
        if best is not None:
            ct.fire(best)

    def _ensure_core_pos(self, ct: Controller) -> None:
        if self.map_w is None:
            self.map_w = ct.get_map_width()
        if self.map_h is None:
            self.map_h = ct.get_map_height()
        if self.core_pos is not None:
            return
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == ct.get_team():
                self.core_pos = ct.get_position(eid)
                return

    def _current_goal(self, ct: Controller, mode: str, target: Position) -> Position:
        here = ct.get_position()
        if self.goal_mode != mode or self.goal is None:
            self.goal_mode = mode
            self.goal = target
            return self.goal
        if mode == "outward":
            self.goal = target
            return self.goal
        if mode in {"harvester", "chip"} and here.distance_squared(target) < here.distance_squared(self.goal):
            self.goal = target
        return self.goal

    def _nearest_enemy_harvester(self, ct: Controller) -> Position | None:
        here = ct.get_position()
        best = None
        best_key = None
        for eid in ct.get_nearby_buildings():
            if ct.get_team(eid) == ct.get_team():
                continue
            if ct.get_entity_type(eid) != EntityType.HARVESTER:
                continue
            pos = ct.get_position(eid)
            key = (here.distance_squared(pos), pos.x, pos.y)
            if best_key is None or key < best_key:
                best = pos
                best_key = key
        return best

    def _try_build_adjacent_sentinel(self, ct: Controller, target: Position) -> bool:
        here = ct.get_position()
        best = None
        best_key = None
        clear_road = None
        clear_key = None
        for direction in CARDINALS:
            stand = target.add(direction)
            if not ct.is_in_vision(stand):
                continue
            building_id = ct.get_tile_building_id(stand)
            if building_id is not None:
                if ct.get_team(building_id) == ct.get_team() and ct.get_entity_type(building_id) == EntityType.ROAD and ct.can_destroy(stand):
                    key = (here.distance_squared(stand), stand.x, stand.y)
                    if clear_key is None or key < clear_key:
                        clear_road = stand
                        clear_key = key
            for facing in self._feedable_sentinel_facings(target, stand):
                if not ct.can_build_sentinel(stand, facing):
                    continue
                key = (here.distance_squared(stand), stand.x, stand.y)
                if best_key is None or key < best_key:
                    best = (stand, facing)
                    best_key = key
        if best is None:
            if clear_road is not None:
                ct.destroy(clear_road)
                return True
            return False
        stand, facing = best
        ct.build_sentinel(stand, facing)
        return True

    def _feedable_sentinel_facings(self, target: Position, stand: Position) -> list[Direction]:
        dx = target.x - stand.x
        dy = target.y - stand.y
        if dx == 0 and dy == 1:
            return [Direction.SOUTHEAST, Direction.SOUTHWEST, Direction.EAST, Direction.WEST]
        if dx == 0 and dy == -1:
            return [Direction.NORTHEAST, Direction.NORTHWEST, Direction.EAST, Direction.WEST]
        if dx == 1 and dy == 0:
            return [Direction.NORTHEAST, Direction.SOUTHEAST, Direction.NORTH, Direction.SOUTH]
        if dx == -1 and dy == 0:
            return [Direction.NORTHWEST, Direction.SOUTHWEST, Direction.NORTH, Direction.SOUTH]
        return []

    def _has_friendly_sentinel_adjacent(self, ct: Controller, target: Position) -> bool:
        for eid in ct.get_nearby_buildings():
            if ct.get_team(eid) != ct.get_team():
                continue
            if ct.get_entity_type(eid) != EntityType.SENTINEL:
                continue
            pos = ct.get_position(eid)
            if pos.distance_squared(target) == 1:
                return True
        return False

    def _best_enemy_walkable_adjacent_to(self, ct: Controller, target: Position) -> Position | None:
        here = ct.get_position()
        best = None
        best_key = None
        for direction in DIRECTIONS:
            pos = target.add(direction)
            if not ct.is_in_vision(pos):
                continue
            building_id = ct.get_tile_building_id(pos)
            if building_id is None:
                continue
            if ct.get_team(building_id) == ct.get_team():
                continue
            if ct.get_entity_type(building_id) not in WALKABLE_BUILDINGS:
                continue
            key = (here.distance_squared(pos), pos.x, pos.y)
            if best_key is None or key < best_key:
                best = pos
                best_key = key
        return best

    def _outward_goal(self, pos: Position) -> Position:
        if self.core_pos is None or self.map_w is None or self.map_h is None:
            return self.core_pos if self.core_pos is not None else Position(0, 0)
        enemy_core = Position(self.map_w - 1 - self.core_pos.x, self.map_h - 1 - self.core_pos.y)
        horizontal = abs(enemy_core.x - self.core_pos.x) >= abs(enemy_core.y - self.core_pos.y)
        if self.lane_offset is None:
            self.lane_offset = self._initial_lane_offset(pos, horizontal)
        goals = self._scout_waypoints(enemy_core, horizontal)
        goal = goals[self.scout_stage]
        dist = pos.distance_squared(goal)
        if dist <= 4:
            self.scout_stage = (self.scout_stage + 1) % len(goals)
            self.stuck_turns = 0
            goal = goals[self.scout_stage]
            dist = pos.distance_squared(goal)
        if self.last_goal_dist is not None and dist >= self.last_goal_dist:
            self.stuck_turns += 1
            if self.stuck_turns >= SCOUT_STUCK_TURNS:
                self.scout_stage = (self.scout_stage + 1) % len(goals)
                self.stuck_turns = 0
                goal = goals[self.scout_stage]
                dist = pos.distance_squared(goal)
        else:
            self.stuck_turns = 0
        self.last_goal_dist = dist
        return goal

    def _initial_lane_offset(self, pos: Position, horizontal: bool) -> int:
        if self.core_pos is None or self.map_w is None or self.map_h is None:
            return 0
        secondary_span = self.map_h if horizontal else self.map_w
        lane_span = max(2, secondary_span // 6)
        half_lane = max(1, lane_span // 2)
        secondary_delta = (pos.y - self.core_pos.y) if horizontal else (pos.x - self.core_pos.x)
        if secondary_delta < 0:
            return -lane_span
        if secondary_delta > 0:
            return lane_span
        primary_delta = (pos.x - self.core_pos.x) if horizontal else (pos.y - self.core_pos.y)
        if primary_delta < 0:
            return -half_lane
        if primary_delta > 0:
            return half_lane
        return 0

    def _scout_waypoints(self, enemy_core: Position, horizontal: bool) -> list[Position]:
        assert self.core_pos is not None
        assert self.map_w is not None
        assert self.map_h is not None
        lane = self.lane_offset or 0
        if lane == 0:
            alternate_lane = max(2, (self.map_h if horizontal else self.map_w) // 8)
        else:
            alternate_lane = -lane
        if horizontal:
            mid_x = self._clamp((self.core_pos.x + enemy_core.x) // 2, 0, self.map_w - 1)
            lane_y = self._clamp(enemy_core.y + lane, 0, self.map_h - 1)
            alt_y = self._clamp(enemy_core.y + alternate_lane, 0, self.map_h - 1)
            return [
                Position(mid_x, lane_y),
                Position(enemy_core.x, lane_y),
                Position(enemy_core.x, alt_y),
                enemy_core,
            ]
        mid_y = self._clamp((self.core_pos.y + enemy_core.y) // 2, 0, self.map_h - 1)
        lane_x = self._clamp(enemy_core.x + lane, 0, self.map_w - 1)
        alt_x = self._clamp(enemy_core.x + alternate_lane, 0, self.map_w - 1)
        return [
            Position(lane_x, mid_y),
            Position(lane_x, enemy_core.y),
            Position(alt_x, enemy_core.y),
            enemy_core,
        ]

    def _clamp(self, value: int, low: int, high: int) -> int:
        return min(max(value, low), high)

    def _step_toward(self, ct: Controller, target: Position) -> None:
        here = ct.get_position()
        candidates = []
        for direction in DIRECTIONS:
            nxt = here.add(direction)
            backtrack_penalty = 1 if self.prev_pos is not None and nxt == self.prev_pos else 0
            key = (backtrack_penalty, nxt.distance_squared(target), nxt.x, nxt.y)
            candidates.append((key, direction, nxt))
        candidates.sort(key=lambda item: item[0])
        usable_no_reverse = [
            (direction, nxt)
            for _key, direction, nxt in candidates
            if nxt != self.prev_pos and (ct.can_move(direction) or ct.can_build_road(nxt))
        ]
        if usable_no_reverse:
            ordered = usable_no_reverse
        else:
            ordered = [(direction, nxt) for _key, direction, nxt in candidates]
        for direction, nxt in ordered:
            if ct.can_move(direction):
                self.prev_pos = here
                ct.move(direction)
                return
            if ct.can_build_road(nxt):
                ct.build_road(nxt)
                if ct.can_move(direction):
                    self.prev_pos = here
                    ct.move(direction)
                return
