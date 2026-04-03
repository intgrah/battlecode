"""Gunner fire control.

Fires along facing ray. Shoots enemy buildings and own roads (to clear path).
Won't shoot own non-road buildings. Rotates toward highest-priority enemy
visible in any direction, avoiding feed direction.
"""

import sys

from cambc import Controller, Direction, EntityType, Position
from unit import Unit


def _glog(msg: str) -> None:
    print(msg)
    print(msg, file=sys.stderr)

_DIR8 = [d for d in Direction if d != Direction.CENTRE]

# Priority: higher = more valuable target
_PRIORITY: dict[EntityType, int] = {
    EntityType.GUNNER: 5,
    EntityType.SENTINEL: 5,
    EntityType.BREACH: 5,
    EntityType.LAUNCHER: 5,
    EntityType.BARRIER: 4,
    EntityType.CORE: 3,
    EntityType.CONVEYOR: 2,
    EntityType.SPLITTER: 2,
    EntityType.BRIDGE: 2,
    EntityType.ARMOURED_CONVEYOR: 2,
    EntityType.ROAD: 1,
}

# Our buildings we must NOT shoot through
_OWN_DONT_SHOOT = frozenset({
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
})


_CARDINAL = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
_OUR_ADJACENT = frozenset({
    EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR, EntityType.SPLITTER,
    EntityType.BRIDGE, EntityType.GUNNER, EntityType.SENTINEL,
    EntityType.BREACH, EntityType.LAUNCHER,
})


def _harvester_is_feeding_us(ct: Controller, hp: Position, my_team: object) -> bool:
    """Is this enemy harvester feeding any of our conveyors/turrets on cardinal sides?"""
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in _CARDINAL:
        adj = hp.add(d)
        if not (0 <= adj.x < w and 0 <= adj.y < h):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is None:
            continue
        if ct.get_team(bid) != my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype in (
            EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER, EntityType.GUNNER, EntityType.SENTINEL,
        ):
            return True
    return False


class Gunner(Unit):
    def __init__(self, _ct: Controller) -> None:
        pass

    def run(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        my_team = ct.get_team()
        pos = ct.get_position()
        current = ct.get_direction()

        _glog(f"[GUN] ({pos.x},{pos.y}) facing={current.name}")

        # Scan current facing — should we fire?
        fire_target, cur_priority = _scan_ray_for_fire(ct, pos, current, my_team)
        _glog(f"[GUN] ray: target={fire_target} pri={cur_priority}")

        # Also check enemy units (bots) — firing damages the bot, not the tile
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up = ct.get_position(uid)
            if ct.can_fire(up):
                if cur_priority < 2:
                    _glog(f"[GUN] enemy bot at ({up.x},{up.y}), upgrading target")
                    fire_target = up
                    cur_priority = 2

        # Check if we have ammo for rotation decisions
        has_ammo = ct.get_ammo_amount() > 0
        _glog(f"[GUN] ammo={has_ammo}")

        if fire_target is not None:
            # We have something to shoot — but is there a better direction?
            if has_ammo and cur_priority < 5:
                best_dir, best_pri = _best_rotation(ct, pos, current, my_team)
                _glog(f"[GUN] cur_pri={cur_priority} best_rot={best_dir.name} rot_pri={best_pri}")
                if best_pri > cur_priority:
                    ti, _ = ct.get_global_resources()
                    if ti >= 10 and ct.can_rotate(best_dir):
                        _glog(f"[GUN] ROTATING to {best_dir.name} (pri {best_pri} > {cur_priority})")
                        ct.rotate(best_dir)
                        return
                    _glog(f"[GUN] want to rotate but ti={ti} or can't")
            _glog(f"[GUN] FIRE at ({fire_target.x},{fire_target.y}) pri={cur_priority}")
            ct.fire(fire_target)
            return

        # Nothing to fire at — rotate toward a target or away from feed
        feed_dir = _detect_feed_direction(ct, pos, my_team)
        facing_feed = feed_dir is not None and current == feed_dir

        if has_ammo or facing_feed:
            best_dir, best_pri = _best_rotation(ct, pos, current, my_team)
            reason = "facing feed" if facing_feed and not has_ammo else "has ammo"
            _glog(f"[GUN] no target, {reason}, best_rot={best_dir.name} rot_pri={best_pri}")
            if best_pri > 0 or facing_feed:
                if facing_feed and best_dir == current:
                    # Must rotate away from feed — pick any other direction
                    for d in _DIR8:
                        if d != current and d != feed_dir:
                            best_dir = d
                            break
                ti, _ = ct.get_global_resources()
                if ti >= 10 and ct.can_rotate(best_dir):
                    _glog(f"[GUN] ROTATING to {best_dir.name} ({reason})")
                    ct.rotate(best_dir)
                    return
                _glog(f"[GUN] want to rotate but ti={ti} or can't")
        else:
            _glog("[GUN] no target, no ammo")


def _scan_ray_for_fire(
    ct: Controller,
    pos: Position,
    facing: Direction,
    my_team: object,
) -> tuple[Position | None, int]:
    """Scan the facing ray for a target we should fire at.

    Returns (target_pos, strategic_priority) or (None, 0).
    The target is the first hittable thing, but the priority reflects
    the best enemy BEHIND it (so we don't rotate away from a road
    that's blocking our path to the core).
    """
    from cambc import Environment

    dx, dy = facing.delta()
    x, y = pos.x + dx, pos.y + dy
    w = ct.get_map_width()
    h = ct.get_map_height()

    first_target: Position | None = None
    best_strategic_pri = 0

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
            etype = ct.get_entity_type(bid)

            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue

            if team != my_team:
                if etype == EntityType.HARVESTER:
                    if _harvester_is_feeding_us(ct, tp, my_team):
                        x += dx
                        y += dy
                        continue  # our parasitised harvester — skip
                    # Unprotected enemy harvester — targetable
                    pri = 2
                    if pri > best_strategic_pri:
                        best_strategic_pri = pri
                    if first_target is None and ct.can_fire(tp):
                        first_target = tp
                    x += dx
                    y += dy
                    continue
                pri = _PRIORITY.get(etype, 1)
                if pri > best_strategic_pri:
                    best_strategic_pri = pri
                if first_target is None and ct.can_fire(tp):
                    first_target = tp
                # Enemy buildings block LoS but keep scanning for priority
                x += dx
                y += dy
                continue

            # Our building
            if etype == EntityType.ROAD:
                # Don't shoot if our builder is on this tile (would hit the bot)
                has_friendly_bot = False
                for uid in ct.get_nearby_units():
                    if ct.get_team(uid) == my_team and ct.get_position(uid) == tp:
                        has_friendly_bot = True
                        break
                if not has_friendly_bot:
                    if first_target is None and ct.can_fire(tp):
                        first_target = tp
                # Keep scanning — we'll shoot through the road
                x += dx
                y += dy
                continue

            # Our non-road building — blocked
            break

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

    Scans all 8 directions for the highest-priority enemy anywhere along
    the ray (looking through everything). Avoids rotating into feed direction.
    """
    feed_dir = _detect_feed_direction(ct, pos, my_team)
    _glog(f"[GUN] feed_dir={feed_dir.name if feed_dir else 'None'}")
    best_dir = current
    best_pri = 0

    for d in _DIR8:
        if d == current:
            continue
        if d == feed_dir:
            continue

        pri = _scan_ray_strategic(ct, pos, d, my_team)
        if pri > 0:
            _glog(f"[GUN] scan {d.name}: pri={pri}")
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
    Returns the priority of the best enemy reachable without shooting
    through our own valuable infrastructure.
    """
    dx, dy = facing.delta()
    x, y = pos.x + dx, pos.y + dy
    w = ct.get_map_width()
    h = ct.get_map_height()
    best_pri = 0

    while 0 <= x < w and 0 <= y < h:
        if (x - pos.x) ** 2 + (y - pos.y) ** 2 > 13:
            break
        tp = Position(x, y)

        # Wall blocks ray
        env = ct.get_tile_env(tp)
        from cambc import Environment
        if env == Environment.WALL:
            break

        bid = ct.get_tile_building_id(tp)
        if bid is not None:
            team = ct.get_team(bid)
            etype = ct.get_entity_type(bid)

            if etype == EntityType.MARKER:
                # Markers don't block
                x += dx
                y += dy
                continue

            if team != my_team:
                if etype == EntityType.HARVESTER:
                    if _harvester_is_feeding_us(ct, tp, my_team):
                        break  # our parasitised harvester — block ray
                    # Unprotected — targetable, doesn't block
                    if 3 > best_pri:
                        best_pri = 2
                    x += dx
                    y += dy
                    continue
                # Enemy — record priority
                pri = _PRIORITY.get(etype, 1)
                if pri > best_pri:
                    best_pri = pri
                # Enemy buildings block but we still want to see what's behind
                x += dx
                y += dy
                continue

            # Our building
            if etype == EntityType.ROAD:
                # Our road — we can shoot through it, keep scanning
                x += dx
                y += dy
                continue

            # Our non-road building — blocked, stop scanning
            break

        x += dx
        y += dy

    return best_pri


def _detect_feed_direction(
    ct: Controller,
    pos: Position,
    my_team: object,
) -> Direction | None:
    """Detect which direction ammo comes from by checking adjacent tiles.

    Checks for allied conveyors/splitters AND any harvester (enemy too,
    since we parasitise them).
    """
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in _DIR8:
        adj = pos.add(d)
        if not (0 <= adj.x < w and 0 <= adj.y < h):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is None:
            continue
        etype = ct.get_entity_type(bid)
        # Any harvester (ours or enemy) is a potential feed source
        if etype == EntityType.HARVESTER:
            return d
        # Allied transport feeding us
        if ct.get_team(bid) != my_team:
            continue
        match etype:
            case EntityType.CONVEYOR | EntityType.ARMOURED_CONVEYOR:
                return d
            case EntityType.SPLITTER:
                return d
    return None
