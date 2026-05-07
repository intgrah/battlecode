"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/helpers.py`.

Shared helpers for the offense task family. Hosts target-selection
predicates (`vulnerable_harvesters`, `pick_harvester_target`,
`pick_attack_destination`, `pick_conveyor_target`), gating predicates
(`should_attack`, `enemy_healer_near`, etc.), turret-facing math
(`gunner_chain_facing`), the `scout_toward_enemy` movement helper, and
`begin_turn_offense` — the once-per-turn state-decay prelude that runs
before any offense task fires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType, Environment, GameConstants

if TYPE_CHECKING:
    from cambc import Position
from util.directions import DIR4, DIR8
from util.metrics import chebyshev, closest

from builder.explore import explore
from builder.helpers import can_afford, make_move, try_move_dir


def open_tiles(self_, positions):
    return [
        p
        for p in positions
        if self_.cost_grid[self_.idx(p)] != 1000000 and p not in self_.all_bots
    ]


def is_allied_transport(self_, position):
    return (
        (self_.building_kind[self_.idx(position)] is not None)
        and (
            self_.building_kind[self_.idx(position)] == EntityType.CONVEYOR
            or self_.building_kind[self_.idx(position)] == EntityType.ARMOURED_CONVEYOR
            or self_.building_kind[self_.idx(position)] == EntityType.SPLITTER
            or self_.building_kind[self_.idx(position)] == EntityType.BRIDGE
        )
    ) and self_.building_team[self_.idx(position)] == self_.my_team


def without_allied_transport(self_, positions):
    return [p for p in positions if not is_allied_transport(self_, p)]


def buildable(self_, positions):
    return [p for p in positions if is_cheap_overbuild(self_, p)]


def is_cheap_overbuild(self_, pos):
    if not self_.in_bounds(pos):
        return False
    if self_.env[self_.idx(pos)] == Environment.WALL:
        return False
    kind = self_.building_kind[self_.idx(pos)]
    if kind is None:
        return True
    if kind == EntityType.MARKER:
        return True
    return (
        kind == EntityType.ROAD and self_.building_team[self_.idx(pos)] == self_.my_team
    )


def nearest_enemy_bot(self_):
    if not self_.enemy_bots:
        return None
    return closest(self_.my_pos, self_.enemy_bots)


def should_attack(self_, pos):
    enemy_builder = nearest_enemy_bot(self_)
    i = self_.idx(pos)
    return (
        (enemy_builder is None)
        or chebyshev(self_.my_pos, enemy_builder) > 2
        or self_.hp[i] <= self_.max_hp[i] - 4
        or self_.hp[i] <= 4
        or can_afford(self_, EntityType.HARVESTER)
    )


def enemy_healer_near(self_, pos):
    return any(p.distance_squared(pos) <= 2 for p in self_.enemy_bots)


def friendly_bot_adjacent(self_, pos):
    return any(p.distance_squared(pos) <= 1 for p in self_.friendly_bots)


def min_friendly_chebyshev(ct, pos):
    """
    Chebyshev distance from `pos` to the nearest OTHER friendly
    builder bot.
    """
    my_team = ct.get_team(None)
    my_id = ct.get_id()
    best = 999
    for uid in ct.get_nearby_units(None):
        if uid == my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue
        d = chebyshev(pos, ct.get_position(uid))
        best = min(best, d)
    return best


def pick_conveyor_target(self_, ct, enemy_core, my_pos):
    """
    Pick an enemy conveyor/bridge/splitter tile to attack, falling
    back when no harvester is vulnerable.
    """
    best: Position | None = None
    best_score: tuple[int, int, int] | None = None
    for pos in self_.nearby_buildings:
        __opt_tuple = self_.get_building(pos)
        if __opt_tuple is None:
            continue
        kind, team = __opt_tuple
        if team == self_.my_team:
            continue
        if kind not in (
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.SPLITTER,
            EntityType.BRIDGE,
        ):
            continue
        if self_.cost_grid[self_.idx(pos)] == 1000000:
            continue
        if pos in self_.attack_tile_blacklist:
            continue
        if pos in self_.friendly_turret_ray_tiles:
            continue
        uid = self_.all_bots.get(pos)
        if uid is not None and (uid != self_.my_id):
            continue
        if enemy_healer_near(self_, pos):
            continue
        near_core = pos.distance_squared(enemy_core) <= 25
        has_flow = False
        bid = ct.get_tile_building_id(pos)
        if (
            (ct.is_in_vision(pos))
            and bid is not None
            and (ct.get_stored_resource(bid) is not None)
        ):
            has_flow = True
        if near_core:
            tier = 0
        elif has_flow:
            tier = 1
        else:
            continue
        spacing = min_friendly_chebyshev(ct, pos)
        my_dist = my_pos.distance_squared(pos)
        score = (tier, -min(spacing, 3), my_dist)
        match best_score:
            case prev if prev is not None and (score >= prev):
                pass
            case _:
                best = pos
                best_score = score
    return best


def pick_attack_destination(self_, target, avoid_healers):
    """
    Pick a cardinal neighbour of `target` (an enemy harvester) for
    us to stand on and attack.
    """
    candidates: list[tuple[int, int, int, Position]] = []
    for d in DIR4:
        pos = target.add(d)
        if not self_.in_bounds(pos):
            continue
        if self_.cost_grid[self_.idx(pos)] == 1000000:
            continue
        if is_allied_transport(self_, pos):
            continue
        uid = self_.all_bots.get(pos)
        if uid is not None and (uid != self_.my_id):
            continue
        if pos in self_.attack_tile_blacklist:
            continue
        if pos in self_.friendly_turret_ray_tiles:
            continue
        kind = self_.building_kind[self_.idx(pos)]
        team = self_.building_team[self_.idx(pos)]
        match kind:
            case None:
                cost = 0
            case _ if team == self_.my_team:
                cost = 0
            case EntityType.CONVEYOR | EntityType.SPLITTER | EntityType.BRIDGE:
                cost = 20
            case _:
                cost = 5
        if avoid_healers and enemy_healer_near(self_, pos):
            continue
        in_ray: int = int(pos in self_.enemy_turret_ray_tiles)
        dist = self_.my_pos.distance_squared(pos)
        candidates.append((in_ray, cost, dist, pos))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def gunner_chain_facing(self_, pos):
    """
    Return a direction (any of DIR8) such that a gunner placed at
    `pos` facing that way has an enemy conveyor/splitter/bridge as
    the first building in its forward ray.
    """
    for d in DIR8:
        current = pos
        for _ in range(4):
            current = current.add(d)
            if not self_.in_bounds(current):
                break
            if pos.distance_squared(current) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                break
            if self_.env[self_.idx(current)] == Environment.WALL:
                break
            __opt_tuple = self_.get_building(current)
            if __opt_tuple is None:
                continue
            kind, team = __opt_tuple
            if team == self_.my_team:
                break
            if kind in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
                EntityType.BRIDGE,
            ):
                return d
            break
    return None


def has_open_side(self_, position) -> bool:
    """
    True iff `position` has at least one passable, unoccupied,
    non-allied-transport cardinal neighbour.
    """
    for direction in DIR4:
        new_position = position.add(direction)
        if not self_.in_bounds(new_position):
            continue
        match self_.all_bots.get(new_position):
            case uid if uid is not None and (uid != self_.my_id):
                occupied = True
            case _:
                occupied = False
        if (
            self_.cost_grid[self_.idx(new_position)] != 1000000
            and not occupied
            and not is_allied_transport(self_, new_position)
        ):
            return True
    return False


def vulnerable_harvesters(self_):
    """
    Enemy harvesters with at least one passable, unoccupied,
    non-allied-transport cardinal.
    """
    result: list[Position] = []
    for p in self_.nearby_buildings:
        __opt_tuple = self_.get_building(p)
        if __opt_tuple is None:
            continue
        kind, team = __opt_tuple
        if team == self_.my_team:
            continue
        if kind != EntityType.HARVESTER:
            continue
        if has_open_side(self_, p):
            result.append(p)
    return result


def pick_harvester_target(self_, vulnerable):
    """3-tier preference over vulnerable harvesters."""
    my_pos = self_.my_pos
    sorted: list[Position] = list(vulnerable)
    sorted.sort(key=my_pos.distance_squared)
    for h in sorted:
        if not enemy_healer_near(self_, h) and not friendly_bot_adjacent(self_, h):
            return h
    for h in sorted:
        if not enemy_healer_near(self_, h):
            return h
    return closest(my_pos, vulnerable)


def scout_toward_enemy(self_, ct) -> None:
    en_core = self_.en_core_guess
    if en_core in self_.nearby_tiles:
        self_.en_core_seen = True
    if not self_.en_core_seen:
        make_move(self_, ct, en_core)
    elif (en_core in self_.nearby_tiles) or self_.ti >= int(
        float(GameConstants.HARVESTER_BASE_COST[0] + 50) * (1.0 + self_.scale)
    ):
        explore(self_, ct)
    else:
        dir8 = list(DIR8)
        self_.rng.shuffle(dir8)
        for d in dir8:
            if try_move_dir(ct, d):
                break


def begin_turn_offense(self_, ct) -> None:
    """Per-turn offense bookkeeping."""
    if self_.attack_tile_blacklist:
        new_blacklist: dict[Position, int] = dict(
            __v
            for t in self_.attack_tile_blacklist.items()
            if (__v := (t[0], t[1] - 1) if t[1] > 1 else None) is not None
        )
        self_.attack_tile_blacklist = new_blacklist
    last = self_.last_fire
    if last is not None and (self_.my_pos != last[0]):
        self_.last_fire = None
    invalidate_target = False
    if self_.offense_turns > 25:
        invalidate_target = True
    else:
        tgt = self_.offense_target
        if tgt is not None and (ct.is_in_vision(tgt)):
            match self_.all_bots.get(tgt):
                case uid if uid is not None and (uid != self_.my_id):
                    occupied = True
                case _:
                    occupied = False
            invalidate_target = (
                not self_.is_enemy_building(tgt)
                or self_.cost_grid[self_.idx(tgt)] == 1000000
                or occupied
            )
    if invalidate_target:
        self_.offense_target = None
        self_.offense_launcher = None
        self_.offense_turns = 0
    else:
        self_.offense_turns += 1
