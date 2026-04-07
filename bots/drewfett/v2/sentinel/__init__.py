from collections import deque

from cambc import Controller, Direction, EntityType, Position
from unit import Unit

_IDLE_LIMIT = 50
_CARDINAL = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
_DIR4_DELTA = ((0, -1), (1, 0), (0, 1), (-1, 0))
_DELTA_TO_DIR: dict[tuple[int, int], Direction] = {
    (0, -1): Direction.NORTH,
    (1, 0): Direction.EAST,
    (0, 1): Direction.SOUTH,
    (-1, 0): Direction.WEST,
}
_TRANSPORT = frozenset({
    EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR,
    EntityType.SPLITTER, EntityType.BRIDGE,
})


def _find_protected_buildings(ct: Controller, my_team: int) -> set[int]:
    """BFS backward from friendly turrets through transport graph.
    Returns set of building IDs that feed our turrets — don't shoot these."""
    protected: set[int] = set()
    queue: deque[int] = deque()
    w = ct.get_map_width()
    h = ct.get_map_height()

    # Seed: all friendly turrets + harvesters adjacent to them
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            protected.add(bid)
            # BFS backward: which tiles feed into this turret?
            tp = ct.get_position(bid)
            queue.append(bid)

    # BFS: for each protected building, find what feeds into it
    visited_tiles: set[tuple[int, int]] = set()
    while queue:
        bid = queue.popleft()
        bp = ct.get_position(bid)
        btype = ct.get_entity_type(bid)

        if (bp.x, bp.y) in visited_tiles:
            continue
        visited_tiles.add((bp.x, bp.y))

        # Check all 4 cardinal neighbors for buildings that output toward this tile
        for dx, dy in _DIR4_DELTA:
            nx, ny = bp.x + dx, bp.y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            npos = Position(nx, ny)
            if not ct.is_in_vision(npos):
                continue
            nbid = ct.get_tile_building_id(npos)
            if nbid is None or nbid in protected:
                continue
            ntype = ct.get_entity_type(nbid)

            delivers = False
            if ntype == EntityType.HARVESTER:
                delivers = True  # harvesters output to all cardinal
            elif ntype in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                nd = ct.get_direction(nbid)
                ddx, ddy = nd.delta()
                if (nx + ddx, ny + ddy) == (bp.x, bp.y):
                    delivers = True
            elif ntype == EntityType.SPLITTER:
                nd = ct.get_direction(nbid)
                sdx, sdy = nd.delta()
                for odx, ody in [(sdx, sdy), (-sdy, sdx), (sdy, -sdx)]:
                    if (nx + odx, ny + ody) == (bp.x, bp.y):
                        delivers = True
                        break

            if delivers:
                protected.add(nbid)
                queue.append(nbid)

    return protected


class Sentinel(Unit):
    def __init__(self, ct: Controller) -> None:
        self._idle_rounds = 0

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        best_target: Position | None = None
        best_priority = -1

        # Find all buildings feeding our turrets — don't shoot these
        protected = _find_protected_buildings(ct, my_team)

        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            # Don't shoot buildings that feed our turrets
            if bid in protected:
                continue
            etype = ct.get_entity_type(bid)
            bp = ct.get_position(bid)

            priority = _target_priority(etype)
            if priority <= best_priority:
                continue
            if etype == EntityType.CORE:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        tp = Position(bp.x + dx, bp.y + dy)
                        if ct.can_fire(tp):
                            best_priority = priority
                            best_target = tp
            elif ct.can_fire(bp):
                best_priority = priority
                best_target = bp

        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up = ct.get_position(uid)
            if not ct.can_fire(up):
                continue
            etype = ct.get_entity_type(uid)
            priority = _target_priority(etype)
            if priority > best_priority:
                best_priority = priority
                best_target = up

        if best_target is not None:
            self._idle_rounds = 0
            ct.fire(best_target)
            return

        self._idle_rounds += 1
        if self._idle_rounds >= _IDLE_LIMIT:
            has_ally_builder = False
            has_enemy = False
            for uid in ct.get_nearby_units():
                team = ct.get_team(uid)
                if (
                    team == my_team
                    and ct.get_entity_type(uid) == EntityType.BUILDER_BOT
                ):
                    has_ally_builder = True
                elif team != my_team:
                    has_enemy = True
            if has_ally_builder and not has_enemy:
                ct.self_destruct()
                return



def _target_priority(etype: EntityType) -> int:
    match etype:
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH | EntityType.LAUNCHER:
            return 5  # enemy turrets — biggest threat
        case EntityType.CORE:
            return 4  # win condition
        case EntityType.HARVESTER:
            return 3  # economic damage
        case (
            EntityType.CONVEYOR
            | EntityType.SPLITTER
            | EntityType.ARMOURED_CONVEYOR
            | EntityType.BRIDGE
        ):
            return 2  # disrupt transport
        case EntityType.BUILDER_BOT:
            return 2  # kill builders
        case EntityType.BARRIER:
            return 1  # clear obstacles
        case _:
            return 0
