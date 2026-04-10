"""Gunner fire control. Fires along facing ray, rotates to find targets."""

from __future__ import annotations

from cambc import Controller, Direction, EntityType, Environment, Position
from unit import Unit
from util import DIR4, DIR8

_IDLE_LIMIT = 25

_TRANSPORT_TYPES = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    }
)


def _compute_feed_chain(ct: Controller, pos: Position, my_team: int) -> set[int]:
    """BFS backward from ALL friendly turrets to find tiles feeding them."""
    w = ct.get_map_width()
    protected: set[int] = set()
    queue: list[tuple[int, int]] = []

    # Pre-build bridge target lookup: target_coord → list of bridge source coords
    bridge_sources: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.BRIDGE:
            continue
        bp = ct.get_position(bid)
        tgt = ct.get_bridge_target(bid)
        bridge_sources.setdefault((tgt.x, tgt.y), []).append((bp.x, bp.y))

    # Start from all nearby friendly turrets (not just ourselves)
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            bp = ct.get_position(bid)
            queue.append((bp.x, bp.y))

    while queue:
        cx, cy = queue.pop()
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < ct.get_map_height()):
                continue
            ni = ny * w + nx
            if ni in protected:
                continue
            np = Position(nx, ny)
            if not ct.is_in_vision(np):
                continue
            bid = ct.get_tile_building_id(np)
            if bid is None:
                continue
            etype = ct.get_entity_type(bid)

            # Check if this building outputs toward (cx, cy)
            outputs_here = False
            if etype == EntityType.HARVESTER:
                outputs_here = True  # harvesters output all 4 cardinal
            elif etype in _TRANSPORT_TYPES:
                if etype == EntityType.BRIDGE:
                    tgt = ct.get_bridge_target(bid)
                    outputs_here = tgt.x == cx and tgt.y == cy
                elif etype == EntityType.SPLITTER:
                    sd = ct.get_direction(bid)
                    sdx, sdy = sd.delta()
                    # Splitter outputs forward + both sides (not back)
                    back_x, back_y = nx - sdx, ny - sdy
                    outputs_here = (cx, cy) != (back_x, back_y) and (
                        abs(cx - nx) + abs(cy - ny) == 1
                    )
                else:
                    # Conveyor/armoured conveyor
                    d = ct.get_direction(bid)
                    ddx, ddy = d.delta()
                    outputs_here = (nx + ddx, ny + ddy) == (cx, cy)

            if outputs_here:
                protected.add(ni)
                queue.append((nx, ny))

        # Also check bridges targeting this tile (non-adjacent feeders)
        for bx, by in bridge_sources.get((cx, cy), []):
            bi = by * w + bx
            if bi not in protected:
                protected.add(bi)
                queue.append((bx, by))

    return protected


class Gunner(Unit):
    def __init__(self, ct: Controller) -> None:
        self._idle_rounds = 0

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        pos = ct.get_position()
        direction = ct.get_direction()
        w = ct.get_map_width()

        # Compute feed chain — don't shoot tiles feeding us
        protected = _compute_feed_chain(ct, pos, my_team)

        # Try to fire along current facing
        target = _scan_ray(ct, pos, direction, my_team, protected, w)
        if target is not None and ct.can_fire(target):
            ct.fire(target)
            self._idle_rounds = 0
            return

        # Try rotating to find a target worth the 10 Ti rotation cost
        # Only rotate for priority >= 3 (transport, turrets, core)
        # Don't rotate for roads (1), barriers (2), or bots (dodge)
        _MIN_ROTATE_PRIORITY = 3
        best_target: Position | None = None
        best_priority = -1
        best_dir: Direction | None = None
        for d in DIR8:
            t = _scan_ray(ct, pos, d, my_team, protected, w)
            if t is None:
                continue
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) == my_team:
                continue  # skip own buildings / bot-only tiles
            etype = ct.get_entity_type(bid)
            p = _target_priority(etype)
            if p <= 0:
                continue  # never shoot (harvesters)
            # Lookahead: if low-priority target (road/barrier), peek behind
            if p <= 2:
                behind = _scan_ray_from(ct, t, d, my_team)
                if behind is not None:
                    bbid = ct.get_tile_building_id(behind)
                    if bbid is not None and ct.get_team(bbid) != my_team:
                        bp = _target_priority(ct.get_entity_type(bbid))
                        if bp > p:
                            p = bp
            if p > best_priority:
                best_priority = p
                best_target = t
                best_dir = d

        # Rotate only for high-value targets
        if (
            best_dir is not None
            and best_priority >= _MIN_ROTATE_PRIORITY
            and best_dir != direction
        ):
            if ct.can_rotate(best_dir):
                ct.rotate(best_dir)
                self._idle_rounds = 0
                return

        # Fire at whatever we're facing if it's worth shooting
        if (
            best_target is not None
            and best_dir == direction
            and ct.can_fire(best_target)
        ):
            ct.fire(best_target)
            self._idle_rounds = 0
            return

        # Count as idle if we haven't fired. Even if targets exist,
        # we might have no ammo/feed and shouldn't wait forever.
        self._idle_rounds += 1

        # Self-destruct: ally builder within Chebyshev 3, no enemy bot within r²≤20
        if self._idle_rounds >= _IDLE_LIMIT:
            ally_nearby = False
            enemy_nearby = False
            for uid in ct.get_nearby_units():
                upos = ct.get_position(uid)
                if ct.get_team(uid) == my_team:
                    if ct.get_entity_type(uid) == EntityType.BUILDER_BOT:
                        if max(abs(pos.x - upos.x), abs(pos.y - upos.y)) <= 3:
                            ally_nearby = True
                else:
                    if pos.distance_squared(upos) <= 20:
                        enemy_nearby = True
            if ally_nearby and not enemy_nearby:
                ct.self_destruct()


def _scan_ray(
    ct: Controller,
    pos: Position,
    direction: Direction,
    my_team: int,
    protected: set[int],
    w: int,
) -> Position | None:
    """Walk ray from pos in direction, return first targetable enemy or None.

    Skips tiles in `protected` (our feed chain) — don't shoot our own supply.
    """
    dx, dy = direction.delta()
    x, y = pos.x + dx, pos.y + dy
    h = ct.get_map_height()
    while 0 <= x < w and 0 <= y < h:
        if (x - pos.x) ** 2 + (y - pos.y) ** 2 > 13:
            break
        p = Position(x, y)
        env = ct.get_tile_env(p)
        if env == Environment.WALL:
            break
        # Check for builder bot FIRST — game hits bot over building
        bot_id = ct.get_tile_builder_bot_id(p)
        if bot_id is not None:
            if ct.get_team(bot_id) != my_team:
                return p
            break  # friendly bot blocks
        bid = ct.get_tile_building_id(p)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue
            if ct.get_team(bid) != my_team:
                if etype == EntityType.HARVESTER:
                    break  # don't shoot harvesters
                # Don't shoot our feed chain
                ti = y * w + x
                if ti in protected:
                    x += dx
                    y += dy
                    continue  # skip, look further
                return p  # enemy target
            # Own roads: targetable (shoot to clear LoS for enemy behind)
            if etype == EntityType.ROAD:
                return p
            break  # other own buildings block
        x += dx
        y += dy
    return None


def _scan_ray_from(
    ct: Controller,
    start: Position,
    direction: Direction,
    my_team: int,
) -> Position | None:
    """Like _scan_ray but starts one tile past 'start'. Used for lookahead."""
    dx, dy = direction.delta()
    # Start from one tile past 'start'
    x, y = start.x + dx, start.y + dy
    w = ct.get_map_width()
    h = ct.get_map_height()
    # Only look a few tiles ahead (don't need full range)
    for _ in range(3):
        if not (0 <= x < w and 0 <= y < h):
            break
        p = Position(x, y)
        if not ct.is_in_vision(p):
            break
        env = ct.get_tile_env(p)
        if env == Environment.WALL:
            break
        bid = ct.get_tile_building_id(p)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue
            if ct.get_team(bid) != my_team:
                return p
            break
        x += dx
        y += dy
    return None


def _target_priority(etype: EntityType) -> int:
    """Priority for what to shoot. Higher = more important.

    For ROTATION decisions (10 Ti cost), only rotate for priority >= 3.
    For FIRING decisions (already facing), shoot anything priority >= 1.
    """
    match etype:
        case EntityType.CORE:
            return 8  # highest — this wins the game
        case (
            EntityType.GUNNER
            | EntityType.SENTINEL
            | EntityType.BREACH
            | EntityType.LAUNCHER
        ):
            return 6  # enemy turrets — high threat
        case (
            EntityType.CONVEYOR
            | EntityType.SPLITTER
            | EntityType.ARMOURED_CONVEYOR
            | EntityType.BRIDGE
        ):
            return 4  # enemy transport — disrupts their economy
        case EntityType.BARRIER:
            return 2  # blocks space but low value
        case EntityType.ROAD:
            return 1  # cheapest — don't rotate for this, but fire if facing
        case EntityType.HARVESTER:
            return 0  # never — might be feeding us
        case _:
            return 0
