from cambc import Controller, EntityType, Position
from unit import Unit


class Sentinel(Unit):
    def __init__(self, ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        best_target = None
        best_priority = -1

        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            etype = ct.get_entity_type(bid)
            priority = _target_priority(etype)
            if priority <= best_priority:
                continue
            bp = ct.get_position(bid)
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
            ct.fire(best_target)


def _target_priority(etype: EntityType) -> int:
    match etype:
        case EntityType.GUNNER | EntityType.SENTINEL | EntityType.BREACH:
            return 4
        case (
            EntityType.HARVESTER
            | EntityType.BRIDGE
            | EntityType.CONVEYOR
            | EntityType.SPLITTER
            | EntityType.ARMOURED_CONVEYOR
        ):
            return 3
        case EntityType.BUILDER_BOT:
            return 2
        case EntityType.CORE:
            return 1
        case _:
            return 0
