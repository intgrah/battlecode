from cambc import Controller, EntityType, Environment
from entity import Entity
from util import DIR8

_DIR_IDX = {d: i for i, d in enumerate(DIR8)}


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
