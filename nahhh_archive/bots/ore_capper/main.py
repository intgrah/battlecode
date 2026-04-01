from cambc import Controller, Direction, EntityType, Environment, Position

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
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


class Player:
    def __init__(self) -> None:
        self.num_spawned = 0
        self.core_pos: Position | None = None
        self.heading: Direction | None = None

    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() == EntityType.CORE:
            self._run_core(ct)
        elif ct.get_entity_type() == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    def _run_core(self, ct: Controller) -> None:
        self.core_pos = ct.get_position()
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
        if self.heading is None:
            self.heading = self._initial_heading(ct.get_position())

        barrier_target = self._best_barrier_target(ct)
        if barrier_target is not None:
            ct.build_barrier(barrier_target)
            return

        target = self._nearest_visible_titanium(ct)
        if target is None:
            target = self._outward_goal(ct.get_position())
        self._step_toward(ct, target)

    def _ensure_core_pos(self, ct: Controller) -> None:
        if self.core_pos is not None:
            return
        for eid in ct.get_nearby_entities():
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) == ct.get_team():
                self.core_pos = ct.get_position(eid)
                return

    def _initial_heading(self, pos: Position) -> Direction:
        if self.core_pos is None:
            return Direction.EAST
        dx = 0 if pos.x == self.core_pos.x else (1 if pos.x > self.core_pos.x else -1)
        dy = 0 if pos.y == self.core_pos.y else (1 if pos.y > self.core_pos.y else -1)
        return DELTA_TO_DIR.get((dx, dy), Direction.EAST)

    def _best_barrier_target(self, ct: Controller) -> Position | None:
        here = ct.get_position()
        best = None
        best_key = None
        for pos in ct.get_nearby_tiles(2):
            if ct.get_tile_env(pos) != Environment.ORE_TITANIUM:
                continue
            if not ct.can_build_barrier(pos):
                continue
            key = (here.distance_squared(pos), pos.x, pos.y)
            if best_key is None or key < best_key:
                best = pos
                best_key = key
        return best

    def _nearest_visible_titanium(self, ct: Controller) -> Position | None:
        here = ct.get_position()
        best = None
        best_key = None
        for pos in ct.get_nearby_tiles():
            if ct.get_tile_env(pos) != Environment.ORE_TITANIUM:
                continue
            building_id = ct.get_tile_building_id(pos)
            if building_id is not None:
                etype = ct.get_entity_type(building_id)
                team = ct.get_team(building_id)
                if etype in {EntityType.HARVESTER, EntityType.BARRIER} and team == ct.get_team():
                    continue
            key = (here.distance_squared(pos), pos.x, pos.y)
            if best_key is None or key < best_key:
                best = pos
                best_key = key
        return best

    def _outward_goal(self, pos: Position) -> Position:
        if self.heading is None:
            return pos
        dx, dy = DIR_TO_DELTA[self.heading]
        stride = 6
        return Position(pos.x + dx * stride, pos.y + dy * stride)

    def _step_toward(self, ct: Controller, target: Position) -> None:
        here = ct.get_position()
        candidates = []
        for direction in DIRECTIONS:
            nxt = here.add(direction)
            key = (nxt.distance_squared(target), nxt.x, nxt.y)
            candidates.append((key, direction, nxt))
        candidates.sort(key=lambda item: item[0])
        for _key, direction, nxt in candidates:
            if ct.can_move(direction):
                ct.move(direction)
                return
            if ct.can_build_road(nxt):
                ct.build_road(nxt)
                if ct.can_move(direction):
                    ct.move(direction)
                return
