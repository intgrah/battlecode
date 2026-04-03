"""Reactive gunner placement against enemy turrets.

Scans for enemy turrets near friendly infrastructure. If found, picks a
gunner position with line-of-sight to the threat, validates that ammo can
arrive (adjacent harvester or splitter on a non-facing side), and walks
to build. Only places gunners where direct ammo is available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingGunner,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from marker import MarkerTaskClaim, TaskKind
from util import DELTA_TO_DIR, DIR4_DELTA, INF

from .action import Action, PlaceGunner
from .helpers import is_claimed, move_toward_with_road

if TYPE_CHECKING:
    from .state import State

_THREAT_RANGE_SQ = 36


def _find_threat(state: State) -> int | None:
    """Find the nearest enemy turret threatening our infrastructure."""
    pos = state.pos
    w = state.w
    my_infra = state.my_transport | state.my_core_tiles | state.my_harvesters
    if not my_infra:
        return None

    best: int | None = None
    best_dist = INF
    rnd = state.age

    for ti in state.en_turrets:
        if is_claimed(state, ti, TaskKind.DEFEND):
            continue
        tx, ty = ti % w, ti // w
        # Check if this turret is near any of our infrastructure
        near_infra = False
        for ii in my_infra:
            ix, iy = ii % w, ii // w
            if (tx - ix) ** 2 + (ty - iy) ** 2 <= _THREAT_RANGE_SQ:
                near_infra = True
                break
        if not near_infra:
            continue
        dist = (pos.x - tx) ** 2 + (pos.y - ty) ** 2
        if dist < best_dist:
            best_dist = dist
            best = ti
    return best


def _has_friendly_gunner_covering(state: State, threat_idx: int) -> bool:
    """Check if we already have a gunner near this threat."""
    w = state.w
    tx, ty = threat_idx % w, threat_idx // w
    for gi in state.my_turrets:
        bld = state.building[gi]
        match bld:
            case BuildingGunner(team=team) if team == state.my_team:
                gx, gy = gi % w, gi // w
                if (tx - gx) ** 2 + (ty - gy) ** 2 <= 13:
                    return True
    return False


def _find_gunner_placement(
    state: State,
    ct: Controller,
    threat_idx: int,
) -> tuple[Position, Direction] | None:
    """Find a tile + facing for a gunner with LoS and ammo access."""
    w = state.w
    tx, ty = threat_idx % w, threat_idx // w
    threat_pos = Position(tx, ty)
    pos = state.pos

    best: tuple[Position, Direction] | None = None
    best_dist = INF

    for gx in range(max(0, tx - 4), min(w, tx + 5)):
        for gy in range(max(0, ty - 4), min(state.h, ty + 5)):
            gi = gy * w + gx
            dist_sq = (tx - gx) ** 2 + (ty - gy) ** 2
            if dist_sq > 13:
                continue

            # Must be buildable
            env = state.env[gi]
            if env is None or env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                continue
            bld = state.building[gi]
            match bld:
                case None | BuildingRoad() | BuildingMarker():
                    pass
                case _:
                    continue

            # Compute facing toward threat
            dx = tx - gx
            dy = ty - gy
            if dx != 0:
                dx = 1 if dx > 0 else -1
            if dy != 0:
                dy = 1 if dy > 0 else -1
            gun_dir = DELTA_TO_DIR.get((dx, dy))
            if gun_dir is None:
                continue

            gpos = Position(gx, gy)
            if not ct.can_fire_from(gpos, gun_dir, EntityType.GUNNER, threat_pos):
                continue

            # Must have at least one cardinal non-facing neighbor for future ammo feed
            fdx, fdy = gun_dir.delta()
            has_feed_tile = False
            for adx, ady in DIR4_DELTA:
                if (adx, ady) == (fdx, fdy):
                    continue
                ax, ay = gx + adx, gy + ady
                if state.in_bounds(ax, ay):
                    has_feed_tile = True
                    break
            if not has_feed_tile:
                continue

            walk_dist = (pos.x - gx) ** 2 + (pos.y - gy) ** 2
            if walk_dist < best_dist:
                best_dist = walk_dist
                best = (gpos, gun_dir)

    return best


def defend(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    threat_idx = _find_threat(state)
    if threat_idx is None:
        return None
    if _has_friendly_gunner_covering(state, threat_idx):
        return None

    placement = _find_gunner_placement(state, ct, threat_idx)
    if placement is None:
        return None

    gunner_pos, gunner_dir = placement
    pos = state.pos
    rnd = ct.get_current_round()
    state.claim = MarkerTaskClaim(TaskKind.DEFEND, threat_idx, rnd)

    if pos.distance_squared(gunner_pos) <= 2 and pos != gunner_pos:
        g_cost, _ = ct.get_gunner_cost()
        ti, _ = ct.get_global_resources()
        if ti >= g_cost:
            return Direction.CENTRE, PlaceGunner(gunner_pos, gunner_dir)

    result = move_toward_with_road(state, ct, gunner_pos)
    if result is None:
        return None
    move, build = result
    # If we arrive adjacent after moving, place immediately
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(gunner_pos) <= 2 and new_pos != gunner_pos:
            g_cost, _ = ct.get_gunner_cost()
            ti, _ = ct.get_global_resources()
            if ti >= g_cost:
                build = PlaceGunner(gunner_pos, gunner_dir)
    ct.draw_indicator_line(state.pos, gunner_pos, 255, 0, 0)
    return move, build
