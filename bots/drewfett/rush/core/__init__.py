from cambc import Controller, Direction, EntityType, Environment, GameConstants, Position
from marker import MarkerRole
from unit import Unit

_DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]
_ENV_WALL = Environment.WALL

# Role schedule: ECON=0, RUSH=1, HOME=2, FLEX=3
_ROLE_ECON = 0
_ROLE_RUSH = 1
_ROLE_HOME = 2
_ROLE_SCHEDULE = (_ROLE_ECON, _ROLE_ECON, _ROLE_RUSH, _ROLE_RUSH, _ROLE_HOME, _ROLE_RUSH)
_BUILDER_CAP = 6


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.core_pos: Position = ct.get_position()
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        rnd = ct.get_current_round()
        ti, _ = ct.get_global_resources()
        builder_cost, _ = ct.get_builder_bot_cost()
        alive = ct.get_unit_count() - 1

        if alive >= _BUILDER_CAP:
            return

        # Emergency: enemy bots near core → spawn immediately
        my_team = ct.get_team()
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != my_team:
                if ti >= builder_cost:
                    self._spawn_with_role(ct, rnd)
                return

        # Aggressive: first 3 with zero reserve, rest with small reserve
        h_cost, _ = ct.get_harvester_cost()
        c_cost, _ = ct.get_conveyor_cost()
        reserve = 0 if alive < 3 else h_cost + c_cost * 3

        if ti < builder_cost + reserve:
            return

        self._spawn_with_role(ct, rnd)

    def _spawn_with_role(self, ct: Controller, rnd: int) -> None:
        sp = _best_spawn_pos(ct, self.core_pos, self.spawned)
        if sp is None:
            return

        ct.spawn_builder(sp)

        # Determine role from schedule
        idx = min(self.spawned, len(_ROLE_SCHEDULE) - 1)
        role = _ROLE_SCHEDULE[idx]
        if self.spawned >= len(_ROLE_SCHEDULE):
            role = _ROLE_RUSH

        # Place MarkerRole on a core tile (not the spawn tile)
        marker = MarkerRole(
            role=role,
            birthday=rnd % 2048,
            turn=rnd,
        )
        encoded = marker.encode()
        # Place marker on any available tile near core
        for t in ct.get_nearby_tiles(GameConstants.CORE_ACTION_RADIUS_SQ):
            if t == sp:
                continue
            if ct.can_place_marker(t):
                ct.place_marker(t, encoded)
                break

        self.spawned += 1


def _best_spawn_pos(ct: Controller, pos: Position, spawned: int = 0) -> Position | None:
    n = len(_DIRECTIONS)
    # Rotate starting direction so each builder gets a different tile
    # But skip tiles where the builder would be trapped (no walkable neighbor)
    for i in range(n):
        d = _DIRECTIONS[(spawned + i) % n]
        sp = pos.add(d)
        if not ct.can_spawn(sp):
            continue
        # Check tile isn't boxed in by walls
        w, h = ct.get_map_width(), ct.get_map_height()
        walls = 0
        for d2 in _DIRECTIONS:
            adj = sp.add(d2)
            if not (0 <= adj.x < w and 0 <= adj.y < h):
                walls += 1
                continue
            if not ct.is_in_vision(adj):
                continue  # can't tell, assume passable
            if ct.get_tile_env(adj) == _ENV_WALL:
                walls += 1
        if walls < 6:
            return sp
    # Fallback: any spawnable tile
    for d in _DIRECTIONS:
        sp = pos.add(d)
        if ct.can_spawn(sp):
            return sp
    return None
