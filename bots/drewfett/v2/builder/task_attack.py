"""Attack enemy economy by placing sentinels near high-value transport.

Finds highest en_total enemy transport, places a sentinel within attack
range. FEED_TURRET handles ammo routing separately.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
)
from cambc import Controller, Direction, Environment, Position
from util import DIR4_DELTA, DIR8, INF

from .action import Action, Fire, PlaceSentinel
from .helpers import move_toward_with_road, step_off_and_build

if TYPE_CHECKING:
    from .state import State

from .task_defend_core import SENTINEL_ARCS


def _find_attack_target(state: State) -> int | None:
    """Find the highest en_total enemy transport that's safe to approach."""
    f = state.flow
    w = state.w
    pos = state.pos
    best: int | None = None
    best_score = 0.0

    eg, es, eb, el = state.en_gunner, state.en_sentinel, state.en_breach, state.en_launcher

    for i in state.en_transport:
        val = f.en_total[i]
        if val < 0.01:
            continue
        if eg[i] + es[i] + eb[i] + el[i] > 0:
            continue

        ix, iy = i % w, i // w
        dist = (pos.x - ix) ** 2 + (pos.y - iy) ** 2
        score = val / max(1, dist)
        if score > best_score:
            best_score = score
            best = i

    return best


_MAX_FEED_DIST_SQ = 100  # max distance² from sentinel to nearest Ti flow


def _near_our_flow(state: State, sx: int, sy: int) -> bool:
    """Check if there's Ti flow in our network within reasonable distance."""
    w = state.w
    f = state.flow
    for i in state.my_transport | state.my_harvesters:
        if f.ti[i] > 0 or i in state.my_harvesters:
            ix, iy = i % w, i // w
            if (sx - ix) ** 2 + (sy - iy) ** 2 <= _MAX_FEED_DIST_SQ:
                return True
    return False


def _find_sentinel_placement(
    state: State,
    target_idx: int,
) -> tuple[Position, Direction] | None:
    """Find sentinel position + facing that can hit the target."""
    w = state.w
    h = state.h
    tx, ty = target_idx % w, target_idx // w
    pos = state.pos
    eg, es, eb, el = state.en_gunner, state.en_sentinel, state.en_breach, state.en_launcher

    best: tuple[Position, Direction] | None = None
    best_dist = INF

    for dx in range(-6, 7):
        for dy in range(-6, 7):
            if dx * dx + dy * dy > 32:
                continue
            sx, sy = tx + dx, ty + dy
            if not (0 <= sx < w and 0 <= sy < h):
                continue
            si = sy * w + sx

            if eg[si] + es[si] + eb[si] + el[si] > 0:
                continue

            # Must be near our flow network for ammo routing
            if not _near_our_flow(state, sx, sy):
                continue

            env = state.env[si]
            if env in (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            bld = state.building[si]
            match bld:
                case None | BuildingRoad() | BuildingMarker():
                    pass
                case BuildingSentinel(team=team) if team == state.my_team:
                    continue  # already have our sentinel here
                case _:
                    continue

            for facing in DIR8:
                hits_target = False
                for adx, ady in SENTINEL_ARCS[facing]:
                    if (sx + adx, sy + ady) == (tx, ty):
                        hits_target = True
                        break
                if not hits_target:
                    continue

                # Must have at least one cardinal neighbor for future ammo feed
                fdx, fdy = facing.delta()
                has_feed_tile = False
                for cdx, cdy in DIR4_DELTA:
                    if (cdx, cdy) == (fdx, fdy):
                        continue
                    nx, ny = sx + cdx, sy + cdy
                    if 0 <= nx < w and 0 <= ny < h:
                        has_feed_tile = True
                        break
                if not has_feed_tile:
                    continue

                walk_dist = (pos.x - sx) ** 2 + (pos.y - sy) ** 2
                if walk_dist < best_dist:
                    best_dist = walk_dist
                    best = (Position(sx, sy), facing)

    return best


def attack(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    target = _find_attack_target(state)
    if target is None:
        return None

    s_cost, _ = ct.get_sentinel_cost()
    ti, _ = ct.get_global_resources()
    if ti < s_cost:
        return None

    placement = _find_sentinel_placement(state, target)
    if placement is None:
        return None

    sentinel_pos, sentinel_facing = placement
    pos = state.pos
    w = state.w
    tx, ty = target % w, target // w

    if pos == sentinel_pos:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != ct.get_team():
            return Direction.CENTRE, Fire()
        return step_off_and_build(ct, PlaceSentinel(sentinel_pos, sentinel_facing))

    if pos.distance_squared(sentinel_pos) <= 2:
        bid = ct.get_tile_building_id(sentinel_pos)
        if bid is not None and ct.get_team(bid) != ct.get_team():
            d = pos.direction_to(sentinel_pos)
            if ct.can_move(d):
                return d, None
            return None
        return Direction.CENTRE, PlaceSentinel(sentinel_pos, sentinel_facing)

    result = move_toward_with_road(state, ct, sentinel_pos)
    if result is None:
        return None
    move, build = result
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(sentinel_pos) <= 2 and new_pos != sentinel_pos:
            bid = ct.get_tile_building_id(sentinel_pos)
            if bid is None or ct.get_team(bid) == ct.get_team():
                build = PlaceSentinel(sentinel_pos, sentinel_facing)
    ct.draw_indicator_line(state.pos, Position(tx, ty), 255, 0, 0)
    return move, build
