"""Gunner fire control.

Fires at the highest-priority visible enemy target. If no target in the
current facing direction, rotates toward the best visible target.
Rotation costs 10 Ti from global pool.
"""

from cambc import Controller, Direction, EntityType, Position
from unit import Unit

_DIR8 = [d for d in Direction if d != Direction.CENTRE]


class Gunner(Unit):
    def __init__(self, _ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        my_team = ct.get_team()
        best_target: Position | None = None
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
            priority = _target_priority(ct.get_entity_type(uid))
            if priority > best_priority:
                best_priority = priority
                best_target = up

        if best_target is not None:
            ct.fire(best_target)
            return

        # No target in current facing — rotate toward best visible target
        # Only rotate if we have ammo (otherwise pointless Ti drain)
        try:
            if ct.get_stored_resource() is not None:
                _try_rotate(ct, my_team)
        except Exception:
            pass


def _try_rotate(ct: Controller, my_team: object) -> None:
    pos = ct.get_position()
    current = ct.get_direction()

    # Find the direction that feeds us — don't rotate into it
    # (ammo comes from non-facing sides, so our facing IS the non-feed dir)
    # We can rotate to any direction except our current one (no-op)

    best_dir: Direction | None = None
    best_priority = -1

    for d in _DIR8:
        if d == current:
            continue

        # Check enemy buildings
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            bp = ct.get_position(bid)
            etype = ct.get_entity_type(bid)
            if etype == EntityType.CORE:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        tp = Position(bp.x + dx, bp.y + dy)
                        if ct.can_fire_from(pos, d, EntityType.GUNNER, tp):
                            priority = _target_priority(etype)
                            if priority > best_priority:
                                best_priority = priority
                                best_dir = d
            elif ct.can_fire_from(pos, d, EntityType.GUNNER, bp):
                priority = _target_priority(etype)
                if priority > best_priority:
                    best_priority = priority
                    best_dir = d

        # Check enemy units
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up = ct.get_position(uid)
            if ct.can_fire_from(pos, d, EntityType.GUNNER, up):
                priority = _target_priority(ct.get_entity_type(uid))
                if priority > best_priority:
                    best_priority = priority
                    best_dir = d

    if best_dir is not None:
        ti, _ = ct.get_global_resources()
        if ti >= 10 and ct.can_rotate(best_dir):
            ct.rotate(best_dir)


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
