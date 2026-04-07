"""Gunner fire control. Fires along facing ray, rotates to find targets."""

from __future__ import annotations

from cambc import Controller, Direction, EntityType, Environment, Position
from unit import Unit
from util import DIR8

_IDLE_LIMIT = 50


class Gunner(Unit):
    def __init__(self, ct: Controller) -> None:
        self._idle_rounds = 0

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        pos = ct.get_position()
        direction = ct.get_direction()

        # Try to fire along current facing
        target = _scan_ray(ct, pos, direction, my_team)
        if target is not None and ct.can_fire(target):
            ct.fire(target)
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
                p = _target_priority(ct.get_entity_type(bid))
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

        self._idle_rounds += 1
        # Self-destruct after prolonged idle if ally builder nearby and no enemies
        if self._idle_rounds >= _IDLE_LIMIT:
            has_ally_builder = False
            has_enemy = False
            for uid in ct.get_nearby_units():
                team = ct.get_team(uid)
                if (
                    team == my_team
                    and ct.get_entity_type(uid) == EntityType.BUILDER_BOT
                ):
                    has_ally_builder = True
                elif team != my_team:
                    has_enemy = True
            if has_ally_builder and not has_enemy:
                ct.self_destruct()


def _scan_ray(
    ct: Controller,
    pos: Position,
    direction: Direction,
    my_team: int,
) -> Position | None:
    """Walk ray from pos in direction, return first targetable enemy or None."""
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
        bid = ct.get_tile_building_id(p)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            if etype == EntityType.MARKER:
                x += dx
                y += dy
                continue  # markers don't block
            if ct.get_team(bid) != my_team:
                return p  # enemy target
            break  # own building blocks
        # Check for enemy bot on this tile
        bot_id = ct.get_tile_builder_bot_id(p)
        if bot_id is not None and ct.get_team(bot_id) != my_team:
            return p
        x += dx
        y += dy
    return None


def _target_priority(etype: EntityType) -> int:
    match etype:
        case (
            EntityType.GUNNER
            | EntityType.SENTINEL
            | EntityType.BREACH
            | EntityType.LAUNCHER
        ):
            return 5
        case EntityType.CORE:
            return 4
        case EntityType.HARVESTER:
            return 3
        case (
            EntityType.CONVEYOR
            | EntityType.SPLITTER
            | EntityType.ARMOURED_CONVEYOR
            | EntityType.BRIDGE
        ):
            return 2
        case EntityType.BUILDER_BOT:
            return 2
        case EntityType.BARRIER:
            return 1
        case _:
            return 0
