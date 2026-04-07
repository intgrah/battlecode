"""Gunner fire control. Fires along facing ray, rotates to find targets."""

from __future__ import annotations

from cambc import Controller, Direction, EntityType, Environment, Position
from marker import MarkerIdleGunner
from unit import Unit
from util import DIR4, DIR8

_IDLE_LIMIT = 15


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
        # Lookahead: if first hit is a road, peek behind for higher-value targets
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
                # If it's a road, peek behind for better targets
                if etype == EntityType.ROAD:
                    behind = _scan_ray_from(ct, t, d, my_team)
                    if behind is not None:
                        bbid = ct.get_tile_building_id(behind)
                        if bbid is not None and ct.get_team(bbid) != my_team:
                            bp = _target_priority(ct.get_entity_type(bbid))
                            if bp > p:
                                p = bp  # boost this direction's priority
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

        # Only count as idle when genuinely NO targets in any direction.
        # If targets exist but we can't fire (no ammo/Ti), wait for supply.
        if best_target is not None:
            self._idle_rounds = 0  # targets exist, just waiting for ammo
            return

        self._idle_rounds += 1

        # After sustained idle, signal via marker for builder to recycle us
        if self._idle_rounds >= _IDLE_LIMIT:
            w = ct.get_map_width()
            gunner_ti = pos.y * w + pos.x
            marker_val = MarkerIdleGunner(gunner_ti).encode()
            # Try all 8 directions, and destroy own markers to make space
            placed = False
            for d in DIR8:
                mp = pos.add(d)
                if ct.can_place_marker(mp):
                    ct.place_marker(mp, marker_val)
                    placed = True
                    break
            if not placed:
                # All tiles occupied — try destroying a friendly marker first
                for d in DIR8:
                    mp = pos.add(d)
                    bid = ct.get_tile_building_id(mp)
                    if (
                        bid is not None
                        and ct.get_entity_type(bid) == EntityType.MARKER
                        and ct.get_team(bid) == my_team
                    ):
                        ct.destroy(mp)
                        # Marker placed next turn (one marker per round)
                        break


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
        # Check for builder bot on this tile (bots block LoS)
        bot_id = ct.get_tile_builder_bot_id(p)
        if bot_id is not None:
            if ct.get_team(bot_id) != my_team:
                return p  # enemy bot — targetable
            break  # friendly bot — blocks LoS
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
            return 4
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
