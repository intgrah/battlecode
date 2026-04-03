"""Gunner fire control and rotation.

Fires along facing ray. Shoots enemy buildings and own roads (to clear path).
Won't shoot own non-road buildings. Rotates toward highest-priority enemy
visible in any direction, avoiding feed direction.

Port of ``bots/drewfett/rush/gunner/__init__.py``.
"""

from __future__ import annotations

from cambc import Controller, Direction, EntityType, Environment, Position
from unit import Unit

_DIR8: tuple[Direction, ...] = tuple(d for d in Direction if d != Direction.CENTRE)

# Priority: higher = more valuable target.
_PRIORITY: dict[EntityType, int] = {
    EntityType.GUNNER: 5,
    EntityType.SENTINEL: 5,
    EntityType.BREACH: 5,
    EntityType.LAUNCHER: 5,
    EntityType.CORE: 4,
    EntityType.BARRIER: 3,
    EntityType.CONVEYOR: 2,
    EntityType.SPLITTER: 2,
    EntityType.BRIDGE: 2,
    EntityType.ARMOURED_CONVEYOR: 2,
    EntityType.ROAD: 1,
}

# Our buildings we must NOT shoot through.
_OWN_DONT_SHOOT: frozenset[EntityType] = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.HARVESTER,
        EntityType.GUNNER,
        EntityType.SENTINEL,
        EntityType.BREACH,
        EntityType.LAUNCHER,
        EntityType.FOUNDRY,
        EntityType.BARRIER,
        EntityType.CORE,
    }
)

_CARDINAL: tuple[Direction, ...] = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)


class Gunner(Unit):
    """Gunner fire control and rotation logic."""

    def __init__(self, _ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        my_team = ct.get_team()
        pos: Position = ct.get_position()
        current: Direction = ct.get_direction()

        # -- Scan current facing ray for fire target + strategic priority --
        fire_target, cur_priority = _scan_ray_for_fire(ct, pos, current, my_team)

        # -- Also check nearby enemy units (damages bot, not building) --
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up: Position = ct.get_position(uid)
            if ct.can_fire(up) and cur_priority < 2:
                fire_target = up
                cur_priority = 2

        has_ammo: bool = ct.get_ammo_amount() > 0

        if fire_target is not None:
            # We have something to shoot -- but is there a better direction?
            if has_ammo and cur_priority < 5:
                best_dir, best_pri = _best_rotation(ct, pos, current, my_team)
                if best_pri > cur_priority:
                    ti, _ = ct.get_global_resources()
                    if ti >= 10 and ct.can_rotate(best_dir):
                        ct.rotate(best_dir)
                        return
            ct.fire(fire_target)
            return

        # -- Nothing to fire at -- rotate toward a target or away from feed --
        feed_dir: Direction | None = _detect_feed_direction(ct, pos, my_team)
        facing_feed: bool = feed_dir is not None and current == feed_dir

        if has_ammo or facing_feed:
            best_dir, best_pri = _best_rotation(ct, pos, current, my_team)
            if best_pri > 0 or facing_feed:
                if facing_feed and best_dir == current:
                    # Must rotate away from feed -- pick any other direction.
                    for d in _DIR8:
                        if d not in (current, feed_dir):
                            best_dir = d
                            break
                ti, _ = ct.get_global_resources()
                if ti >= 10 and ct.can_rotate(best_dir):
                    ct.rotate(best_dir)
                    return


def _scan_ray_for_fire(
    ct: Controller,
    pos: Position,
    facing: Direction,
    my_team: object,
) -> tuple[Position | None, int]:
    """Scan the facing ray for a target we should fire at.

    Returns ``(target_pos, strategic_priority)`` or ``(None, 0)``.
    The target is the first hittable thing, but the priority reflects the best
    enemy *behind* it (so we don't rotate away from a road that's blocking our
    path to the core).
    """
    dx, dy = facing.delta()
    x: int = pos.x + dx
    y: int = pos.y + dy
    w: int = ct.get_map_width()
    h: int = ct.get_map_height()

    first_target: Position | None = None
    best_strategic_pri: int = 0

    while 0 <= x < w and 0 <= y < h:
        if (x - pos.x) ** 2 + (y - pos.y) ** 2 > 13:
            break
        tp = Position(x, y)

        env = ct.get_tile_env(tp)
        if env == Environment.WALL:
            break

        bid = ct.get_tile_building_id(tp)
        if bid is not None:
            team = ct.get_team(bid)
            etype: EntityType = ct.get_entity_type(bid)

            # Markers don't block.
            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue

            if team != my_team:
                # Enemy building.
                if etype == EntityType.HARVESTER:
                    if _harvester_is_feeding_us(ct, tp, my_team):
                        # Our parasitised harvester -- skip it.
                        x += dx
                        y += dy
                        continue
                    # Unprotected enemy harvester -- targetable.
                    pri = 2
                else:
                    pri = _PRIORITY.get(etype, 1)

                best_strategic_pri = max(best_strategic_pri, pri)
                if first_target is None and ct.can_fire(tp):
                    first_target = tp
                # Enemy buildings block LoS but keep scanning for priority.
                x += dx
                y += dy
                continue

            # Our building.
            if etype == EntityType.ROAD:
                # Don't shoot if a friendly builder is on this tile.
                has_friendly_bot = False
                for uid in ct.get_nearby_units():
                    if ct.get_team(uid) == my_team and ct.get_position(uid) == tp:
                        has_friendly_bot = True
                        break
                if not has_friendly_bot and first_target is None and ct.can_fire(tp):
                    first_target = tp
                # Keep scanning -- we shoot through our roads.
                x += dx
                y += dy
                continue

            # Our non-road building -- blocked.
            break

        # Empty tile -- keep scanning.
        x += dx
        y += dy

    if first_target is not None:
        return first_target, max(best_strategic_pri, 1)
    return None, 0


def _best_rotation(
    ct: Controller,
    pos: Position,
    current: Direction,
    my_team: object,
) -> tuple[Direction, int]:
    """Find the best direction to rotate to.

    Scans all 8 directions (including *current*) for the highest-priority enemy
    anywhere along the ray (looking through everything). Avoids rotating into
    the feed direction.

    Including *current* in the scan prevents oscillation when a friendly builder
    temporarily blocks the shot.
    """
    feed_dir: Direction | None = _detect_feed_direction(ct, pos, my_team)
    best_dir: Direction = current
    best_pri: int = 0

    for d in _DIR8:
        if d == feed_dir:
            continue

        pri: int = _scan_ray_strategic(ct, pos, d, my_team)
        if pri > best_pri:
            best_pri = pri
            best_dir = d

    return best_dir, best_pri


def _scan_ray_strategic(
    ct: Controller,
    pos: Position,
    facing: Direction,
    my_team: object,
) -> int:
    """Scan a ray for the highest-priority enemy we can reach.

    Looks through: empty tiles, markers, own roads, enemy buildings.
    Blocked by: own non-road buildings, walls.
    Returns the priority of the best enemy reachable without shooting through
    our own valuable infrastructure.
    """
    dx, dy = facing.delta()
    x: int = pos.x + dx
    y: int = pos.y + dy
    w: int = ct.get_map_width()
    h: int = ct.get_map_height()
    best_pri: int = 0

    while 0 <= x < w and 0 <= y < h:
        if (x - pos.x) ** 2 + (y - pos.y) ** 2 > 13:
            break
        tp = Position(x, y)

        env = ct.get_tile_env(tp)
        if env == Environment.WALL:
            break

        bid = ct.get_tile_building_id(tp)
        if bid is not None:
            team = ct.get_team(bid)
            etype: EntityType = ct.get_entity_type(bid)

            # Markers don't block.
            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue

            if team != my_team:
                if etype == EntityType.HARVESTER:
                    if _harvester_is_feeding_us(ct, tp, my_team):
                        break  # Our parasitised harvester -- block ray.
                    # Unprotected -- targetable, doesn't block.
                    best_pri = max(best_pri, 2)
                    x += dx
                    y += dy
                    continue
                # Enemy -- record priority.
                pri: int = _PRIORITY.get(etype, 1)
                best_pri = max(best_pri, pri)
                # Enemy buildings block but we still want to see what's behind.
                x += dx
                y += dy
                continue

            # Our building.
            if etype == EntityType.ROAD:
                # Our road -- we can shoot through it, keep scanning.
                x += dx
                y += dy
                continue

            # Our non-road building -- blocked, stop scanning.
            break

        # Empty tile -- keep scanning.
        x += dx
        y += dy

    return best_pri


def _detect_feed_direction(
    ct: Controller,
    pos: Position,
    my_team: object,
) -> Direction | None:
    """Detect which direction ammo comes from by checking adjacent tiles.

    Checks for allied conveyors/splitters AND any harvester (enemy too, since
    we parasitise them).
    """
    w: int = ct.get_map_width()
    h: int = ct.get_map_height()
    for d in _DIR8:
        adj: Position = pos.add(d)
        if not (0 <= adj.x < w and 0 <= adj.y < h):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is None:
            continue
        etype: EntityType = ct.get_entity_type(bid)
        # Any harvester (ours or enemy) is a potential feed source.
        if etype == EntityType.HARVESTER:
            return d
        # Allied transport feeding us.
        if ct.get_team(bid) != my_team:
            continue
        match etype:
            case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR:
                return d
            case EntityType.SPLITTER:
                return d
    return None


def _harvester_is_feeding_us(
    ct: Controller,
    hp: Position,
    my_team: object,
) -> bool:
    """Check if an enemy harvester is adjacent to our conveyors/turrets on cardinal sides."""
    w: int = ct.get_map_width()
    h: int = ct.get_map_height()
    for d in _CARDINAL:
        adj: Position = hp.add(d)
        if not (0 <= adj.x < w and 0 <= adj.y < h):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is None:
            continue
        if ct.get_team(bid) != my_team:
            continue
        etype: EntityType = ct.get_entity_type(bid)
        if etype in (
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
            EntityType.GUNNER,
            EntityType.SENTINEL,
        ):
            return True
    return False
