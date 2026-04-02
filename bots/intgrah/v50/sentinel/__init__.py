from cambc import Controller, EntityType, Position
from unit import Unit


class Sentinel(Unit):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        targets: list[tuple[int, Position]] = []

        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            etype = ct.get_entity_type(bid)
            bp = ct.get_position(bid)
            if etype == EntityType.CORE:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        tp = Position(bp.x + dx, bp.y + dy)
                        if ct.can_fire(tp):
                            targets.append((_target_priority(etype), tp))
            elif ct.can_fire(bp):
                targets.append((_target_priority(etype), bp))

        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up = ct.get_position(uid)
            if ct.can_fire(up):
                targets.append((_target_priority(ct.get_entity_type(uid)), up))

        if targets:
            ct.fire(max(targets)[1])


_PRIORITY: dict[EntityType, int] = {
    EntityType.BREACH: 10,
    EntityType.SENTINEL: 9,
    EntityType.GUNNER: 8,
    EntityType.SPLITTER: 7,
    EntityType.HARVESTER: 6,
    EntityType.BRIDGE: 5,
    EntityType.CONVEYOR: 4,
    EntityType.ARMOURED_CONVEYOR: 3,
    EntityType.CORE: 2,
    EntityType.BUILDER_BOT: 1,
}


def _target_priority(etype: EntityType) -> int:
    return _PRIORITY.get(etype, 0)
