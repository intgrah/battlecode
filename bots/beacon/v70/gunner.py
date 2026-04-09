"""Gunner fire control. Fires along facing ray, rotates to find targets."""

from __future__ import annotations

from cambc import Controller, Direction, EntityType, Environment, Position
from unit import Unit
from util import DIR8

_IDLE_LIMIT = 15


class Gunner(Unit):
    def __init__(self, ct: Controller) -> None:
        self._idle_rounds = 0
        self._last_target_hp: int = 0  # track target HP to detect healing

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        pos = ct.get_position()
        direction = ct.get_direction()

        # Try to fire along current facing
        target = _scan_ray(ct, pos, direction, my_team)
        if target is not None and ct.can_fire(target):
            # Check if target HP went UP (being healed)
            bid = ct.get_tile_building_id(target)
            hp = ct.get_hp(bid) if bid is not None else 0
            if hp > self._last_target_hp and self._last_target_hp > 0:
                # Target is being healed — stop wasting Ti
                self._idle_rounds = _IDLE_LIMIT
            else:
                ct.fire(target)
                self._last_target_hp = hp - 10  # expected HP after our shot
                self._idle_rounds = 0
                return

        # Try rotating to find a better target
        best_target: Position | None = None
        best_priority = -1
        best_dir: Direction | None = None
        for d in DIR8:
            t = _scan_ray(ct, pos, d, my_team)
            if t is None:
                continue
            bid = ct.get_tile_building_id(t)
            bot_id = ct.get_tile_builder_bot_id(t)
            if bid is not None and ct.get_team(bid) != my_team:
                etype = ct.get_entity_type(bid)
                p = _target_priority(etype)
            elif bot_id is not None and ct.get_team(bot_id) != my_team:
                p = _target_priority(EntityType.BUILDER_BOT)
            else:
                continue
            if p > best_priority:
                best_priority = p
                best_target = t
                best_dir = d

        if best_dir is not None and best_dir != direction and ct.can_rotate(best_dir):
            ct.rotate(best_dir)
            self._idle_rounds = 0
            return

        # If already facing correct direction and can fire, do it
        if best_target is not None and ct.can_fire(best_target):
            ct.fire(best_target)
            self._idle_rounds = 0
            return

        # Count as idle if we haven't fired. Even if targets exist,
        # we might have no ammo/feed and shouldn't wait forever.
        self._idle_rounds += 1

        # After sustained idle, self-destruct if ally builder within Chebyshev 2
        if self._idle_rounds >= _IDLE_LIMIT:
            ally_nearby = False
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) != my_team:
                    continue
                if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                    continue
                upos = ct.get_position(uid)
                if max(abs(pos.x - upos.x), abs(pos.y - upos.y)) <= 2:
                    ally_nearby = True
                    break
            if ally_nearby:
                ct.self_destruct()


def _scan_ray(
    ct: Controller,
    pos: Position,
    direction: Direction,
    my_team: int,
) -> Position | None:
    """Walk ray from pos in direction, return first targetable enemy or None.

    Special case: if a friendly road blocks LoS, peek along the rest of the
    ray for an enemy target. If found, return the road (gunner clears it
    next shot to reach the target). Otherwise the road blocks normally.
    """
    dx, dy = direction.delta()
    x, y = pos.x + dx, pos.y + dy
    w = ct.get_map_width()
    h = ct.get_map_height()
    while 0 <= x < w and 0 <= y < h:
        if (x - pos.x) ** 2 + (y - pos.y) ** 2 > 13:
            break
        p = Position(x, y)
        env = ct.get_tile_env(p)
        if env == Environment.WALL:
            break  # wall blocks, not targetable
        # Check for builder bot FIRST — if friendly bot is on a building,
        # turret damage hits the bot, not the building. Don't friendly-fire.
        bot_id = ct.get_tile_builder_bot_id(p)
        if bot_id is not None and ct.get_team(bot_id) == my_team:
            break  # friendly bot — blocks LoS, don't shoot
        bid = ct.get_tile_building_id(p)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue  # markers don't block
            if ct.get_team(bid) != my_team:
                if etype == EntityType.HARVESTER:
                    break  # don't shoot harvesters — might feed us
                return p  # enemy target (also hits enemy bot if standing on it)
            # Friendly building. Roads are cheap to clear if there's a real
            # target behind them — peek the rest of the ray.
            if etype == EntityType.ROAD and _has_enemy_behind(
                ct, x, y, dx, dy, pos, my_team
            ):
                return p  # shoot the road to clear LoS for next turn
            break  # other friendly building blocks
        # No building, but enemy bot on this tile
        if bot_id is not None:
            return p  # enemy bot — targetable
        x += dx
        y += dy
    return None


def _has_enemy_behind(
    ct: Controller,
    rx: int,
    ry: int,
    dx: int,
    dy: int,
    origin: Position,
    my_team: int,
) -> bool:
    """Walk past (rx,ry) along (dx,dy) and return True if a worthwhile enemy
    target is found before LoS is permanently blocked. Used to decide whether
    a friendly road in front of the gunner is worth clearing."""
    w = ct.get_map_width()
    h = ct.get_map_height()
    x, y = rx + dx, ry + dy
    while 0 <= x < w and 0 <= y < h:
        if (x - origin.x) ** 2 + (y - origin.y) ** 2 > 13:
            break
        p = Position(x, y)
        env = ct.get_tile_env(p)
        if env == Environment.WALL:
            return False
        bot_id = ct.get_tile_builder_bot_id(p)
        if bot_id is not None and ct.get_team(bot_id) == my_team:
            return False  # friendly bot blocks
        bid = ct.get_tile_building_id(p)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue
            if ct.get_team(bid) != my_team:
                # Worth clearing road for any enemy except harvesters
                return etype != EntityType.HARVESTER
            return False  # another friendly building blocks
        if bot_id is not None:
            return True  # enemy bot
        x += dx
        y += dy
    return False


def _target_priority(etype: EntityType) -> int:
    match etype:
        case (
            EntityType.GUNNER
            | EntityType.SENTINEL
            | EntityType.BREACH
            | EntityType.LAUNCHER
        ):
            return 6
        case EntityType.BUILDER_BOT:
            return 5
        case EntityType.HARVESTER:
            return 0  # never shoot — might be feeding us via parasitization
        case (
            EntityType.CONVEYOR
            | EntityType.SPLITTER
            | EntityType.ARMOURED_CONVEYOR
            | EntityType.BRIDGE
        ):
            return 3
        case EntityType.CORE:
            return 2
        case EntityType.ROAD:
            return 2  # cheap to kill (5 HP), often screens better targets
        case EntityType.BARRIER:
            return 1
        case _:
            return 0
