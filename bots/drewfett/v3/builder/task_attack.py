"""Attack enemy economy by placing gunners near high-value transport.

Gunners are more Ti-efficient than sentinels (5 dmg/Ti vs 1.8 dmg/Ti),
cheaper to build (10 Ti vs 30 Ti), and can rotate to track targets.
FEED_TURRET handles ammo routing separately.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingGunner,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
)
from cambc import Controller, Direction, Environment, Position
from util import DIR8, INF

from .action import Action, Fire, PlaceGunner
from .helpers import move_toward_with_road, step_off_and_build

if TYPE_CHECKING:
    from .state import State

_ATTACK_RANGE_SQ = 13
_MAX_FEED_DIST_SQ = 36


def _find_attack_target(state: State) -> int | None:
    """Find best attack target: core > harvesters > transport."""
    w = state.w
    pos = state.pos
    eg, es, eb, el = state.en_gunner, state.en_sentinel, state.en_breach, state.en_launcher

    best: int | None = None
    best_priority = -1
    best_score = 0.0

    # Priority 4: Enemy core tiles (if known)
    if state.en_core_pos is not None:
        cx, cy = state.en_core_pos.x, state.en_core_pos.y
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = cx + dx, cy + dy
                if not state.in_bounds(nx, ny):
                    continue
                ni = ny * w + nx
                dist = (pos.x - nx) ** 2 + (pos.y - ny) ** 2
                score = 1.0 / max(1, dist)
                if best_priority < 4 or score > best_score:
                    best_priority = 4
                    best_score = score
                    best = ni

    if best is not None:
        return best

    # Priority 3: Enemy harvesters
    for i in state.en_harvesters:
        ix, iy = i % w, i // w
        dist = (pos.x - ix) ** 2 + (pos.y - iy) ** 2
        score = 1.0 / max(1, dist)
        if best_priority < 3 or score > best_score:
            best_priority = 3
            best_score = score
            best = i

    if best is not None:
        return best

    # Priority 2: Enemy turrets
    for i in state.en_turrets:
        ix, iy = i % w, i // w
        dist = (pos.x - ix) ** 2 + (pos.y - iy) ** 2
        score = 1.0 / max(1, dist)
        if best_priority < 2 or score > best_score:
            best_priority = 2
            best_score = score
            best = i

    if best is not None:
        return best

    # Priority 1: Enemy transport with flow
    f = state.flow
    for i in state.en_transport:
        val = f.en_total[i]
        if val < 0.01:
            continue
        ix, iy = i % w, i // w
        dist = (pos.x - ix) ** 2 + (pos.y - iy) ** 2
        score = val / max(1, dist)
        if score > best_score:
            best_score = score
            best = i

    return best


def _network_dist_sq(state: State, sx: int, sy: int) -> int:
    """Min distance² from (sx, sy) to nearest tile with Ti flow."""
    w = state.w
    f = state.flow
    best = INF
    for i in state.my_transport | state.my_harvesters:
        if f.ti[i] > 0 or i in state.my_harvesters:
            ix, iy = i % w, i // w
            d = (sx - ix) ** 2 + (sy - iy) ** 2
            if d < best:
                best = d
    return best


def _find_gunner_placement(
    state: State,
    target_idx: int,
) -> tuple[Position, Direction] | None:
    """Find gunner position within r²=13 of target, facing toward it."""
    w = state.w
    h = state.h
    tx, ty = target_idx % w, target_idx // w
    pos = state.pos
    eg, es, eb, el = state.en_gunner, state.en_sentinel, state.en_breach, state.en_launcher

    best: tuple[Position, Direction] | None = None
    best_dist = INF

    for dx in range(-3, 4):
        for dy in range(-3, 4):
            dist_sq = dx * dx + dy * dy
            if dist_sq == 0 or dist_sq > _ATTACK_RANGE_SQ:
                continue
            sx, sy = tx + dx, ty + dy
            if not (0 <= sx < w and 0 <= sy < h):
                continue
            si = sy * w + sx

            if eg[si] + es[si] + eb[si] + el[si] > 0:
                continue

            net_dist = _network_dist_sq(state, sx, sy)
            if net_dist > _MAX_FEED_DIST_SQ:
                continue

            env = state.env[si]
            if env in (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            bld = state.building[si]
            match bld:
                case None | BuildingRoad() | BuildingMarker():
                    pass
                case BuildingGunner(team=team) | BuildingSentinel(team=team) if team == state.my_team:
                    continue
                case _:
                    continue

            # Face toward the target — gunner can rotate later if needed
            facing = Position(sx, sy).direction_to(Position(tx, ty))
            if facing == Direction.CENTRE:
                continue

            combined_dist = net_dist * 3 + (pos.x - sx) ** 2 + (pos.y - sy) ** 2
            if combined_dist < best_dist:
                best_dist = combined_dist
                best = (Position(sx, sy), facing)

    return best


def attack(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    target = _find_attack_target(state)
    if target is None:
        return None

    g_cost, _ = ct.get_gunner_cost()
    ti, _ = ct.get_global_resources()
    if ti < g_cost:
        return None

    placement = _find_gunner_placement(state, target)
    if placement is None:
        return None

    gunner_pos, gunner_facing = placement
    pos = state.pos
    w = state.w
    tx, ty = target % w, target // w

    if pos == gunner_pos:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != ct.get_team():
            return Direction.CENTRE, Fire()
        return step_off_and_build(ct, PlaceGunner(gunner_pos, gunner_facing))

    if pos.distance_squared(gunner_pos) <= 2:
        bid = ct.get_tile_building_id(gunner_pos)
        if bid is not None and ct.get_team(bid) != ct.get_team():
            d = pos.direction_to(gunner_pos)
            if ct.can_move(d):
                return d, None
            return None
        return Direction.CENTRE, PlaceGunner(gunner_pos, gunner_facing)

    result = move_toward_with_road(state, ct, gunner_pos)
    if result is None:
        return None
    move, build = result
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(gunner_pos) <= 2 and new_pos != gunner_pos:
            bid = ct.get_tile_building_id(gunner_pos)
            if bid is None or ct.get_team(bid) == ct.get_team():
                build = PlaceGunner(gunner_pos, gunner_facing)
    ct.draw_indicator_line(state.pos, Position(tx, ty), 255, 0, 0)
    return move, build
