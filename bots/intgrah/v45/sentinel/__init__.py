from cambc import Controller, Direction, EntityType, Environment
from entity import Entity

_ALL_DIRS = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
_DIR_IDX = {d: i for i, d in enumerate(_ALL_DIRS)}


class Sentinel(Entity):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()
        facing = _DIR_IDX[ct.get_direction()]

        for bid in ct.get_nearby_buildings():
            if ct.get_entity_type(bid) != EntityType.HARVESTER:
                continue
            if ct.get_team(bid) == my_team:
                continue
            hp = ct.get_position(bid)
            if pos.distance_squared(hp) > 1:
                continue
            if ct.get_tile_env(hp) != Environment.ORE_TITANIUM:
                continue
            direction = _DIR_IDX[pos.direction_to(hp)]
            if (direction - facing + 8) % 8 > 1:
                continue
            if ct.can_fire(hp):
                ct.fire(hp)
                return
