from cambc import Controller, Direction, EntityType
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

        # Fire at any enemy entity in range and within facing cone
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my_team:
                continue
            ep = ct.get_position(eid)
            if pos.distance_squared(ep) > 32:
                continue
            direction = _DIR_IDX[pos.direction_to(ep)]
            if (direction - facing + 8) % 8 > 1:
                continue
            if ct.can_fire(ep):
                ct.fire(ep)
                return

        # Also fire at enemy buildings
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            bp = ct.get_position(bid)
            if pos.distance_squared(bp) > 32:
                continue
            direction = _DIR_IDX[pos.direction_to(bp)]
            if (direction - facing + 8) % 8 > 1:
                continue
            if ct.can_fire(bp):
                ct.fire(bp)
                return

        # Stay alive — no self-destruct
