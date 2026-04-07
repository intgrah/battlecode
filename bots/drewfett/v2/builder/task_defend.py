"""Reactive defense: counter enemy turrets threatening our infrastructure.

Scans for enemy turrets near our harvesters/transport/core. Finds a
gunner position with LoS to the threat AND adjacent conveyor delivering
ammo (must point toward gunner tile, not on facing side).

Scores gunner positions by distance to CORE (deterministic), not builder.
Skips tiles with enemy buildings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, Environment, Position
from util import DELTA_TO_DIR, DIR4_DELTA, DIR8_DELTA

from action import Action, Fire, PlaceGunner
from .helpers import move_toward_with_road, step_off_and_build

if TYPE_CHECKING:
    from .state import State

_THREAT_RANGE_SQ = 36
_GUNNER_RANGE_SQ = 13


def defend(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    w = state.w
    pos = state.pos
    my_team = state.my_team

    my_infra = state.my_harvesters | state.my_transport | state.my_core_tiles
    if not my_infra or not state.en_turrets:
        return None

    # Find uncovered enemy turret threatening our infra, closest to us
    best_threat: int | None = None
    best_dist = 1_000_000

    for ti in state.en_turrets:
        tx, ty = ti % w, ti // w
        # Near our infra?
        near_us = any(
            (tx - ii % w) ** 2 + (ty - ii // w) ** 2 <= _THREAT_RANGE_SQ
            for ii in my_infra
        )
        if not near_us:
            continue

        # Already covered by our gunner?
        covered = False
        for gi in state.my_turrets:
            bld = state.building[gi]
            if not isinstance(bld, BuildingGunner) or bld.team != my_team:
                continue
            gx, gy = gi % w, gi // w
            if (gx - tx) ** 2 + (gy - ty) ** 2 <= _GUNNER_RANGE_SQ:
                covered = True
                break
        if covered:
            continue

        # Am I closest builder?
        my_dist = (pos.x - tx) ** 2 + (pos.y - ty) ** 2
        ally_closer = False
        for uid in ct.get_nearby_units():
            if uid == ct.get_id():
                continue
            if ct.get_team(uid) != my_team:
                continue
            ap = ct.get_position(uid)
            if (ap.x - tx) ** 2 + (ap.y - ty) ** 2 < my_dist:
                ally_closer = True
                break
        if ally_closer:
            continue

        if my_dist < best_dist:
            best_dist = my_dist
            best_threat = ti

    if best_threat is None:
        return None

    tx, ty = best_threat % w, best_threat // w

    # Find gunner position: LoS to threat + adjacent ammo source
    best_gpos: Position | None = None
    best_facing: Direction | None = None
    best_score = 1_000_000

    for dx, dy in DIR8_DELTA:
        for r in range(1, 4):
            gx, gy = tx + dx * r, ty + dy * r
            if not state.in_bounds(gx, gy):
                break
            if (gx - tx) ** 2 + (gy - ty) ** 2 > _GUNNER_RANGE_SQ:
                break
            gi = gy * w + gx
            env = state.env[gi]
            if env is None:
                break
            if env == Environment.WALL:
                break
            bld = state.building[gi]
            if bld is not None:
                if bld.team != my_team:
                    break  # enemy building -- skip
                if not isinstance(bld, (BuildingRoad, BuildingMarker)):
                    break  # our non-trivial building -- skip

            # Facing direction toward threat
            fdx = -dx if dx != 0 else 0
            fdy = -dy if dy != 0 else 0
            facing = DELTA_TO_DIR.get((fdx, fdy))
            if facing is None:
                continue

            # Verify LoS: walk from gunner toward threat
            rx, ry = gx + fdx, gy + fdy
            los_ok = True
            while (rx, ry) != (tx, ty):
                if not state.in_bounds(rx, ry):
                    los_ok = False
                    break
                ri = ry * w + rx
                renv = state.env[ri]
                if renv == Environment.WALL:
                    los_ok = False
                    break
                rbld = state.building[ri]
                if rbld is not None and not isinstance(rbld, BuildingMarker):
                    los_ok = False
                    break
                rx += fdx
                ry += fdy
            if not los_ok:
                continue

            # Check ammo: adjacent building must deliver toward gunner
            has_ammo = _check_ammo_delivery(state, gx, gy, fdx, fdy)
            if not has_ammo:
                continue

            # Score by distance from core (deterministic)
            walk = (state.my_core.x - gx) ** 2 + (state.my_core.y - gy) ** 2
            if walk < best_score:
                best_score = walk
                best_gpos = Position(gx, gy)
                best_facing = facing

    if best_gpos is None or best_facing is None:
        return None

    # Place the gunner
    g_cost, _ = ct.get_gunner_cost()
    ti_res, _ = ct.get_global_resources()

    ni = best_gpos.y * w + best_gpos.x
    bld = state.building[ni]

    # On the gunner spot
    if pos == best_gpos:
        if bld is not None and bld.team != my_team:
            if ct.can_fire(best_gpos):
                return Direction.CENTRE, Fire()
            return Direction.CENTRE, None
        if ti_res < g_cost:
            return Direction.CENTRE, None
        return step_off_and_build(ct, PlaceGunner(best_gpos, best_facing))

    # Adjacent to gunner spot
    if pos.distance_squared(best_gpos) <= 2:
        if bld is not None and bld.team != my_team:
            d = pos.direction_to(best_gpos)
            if ct.can_move(d):
                return d, None
        if bld is not None and bld.team == my_team and ct.can_destroy(best_gpos):
            ct.destroy(best_gpos)
        if ti_res >= g_cost and ct.can_build_gunner(best_gpos, best_facing):
            return Direction.CENTRE, PlaceGunner(best_gpos, best_facing)

    return move_toward_with_road(state, ct, best_gpos)


def _check_ammo_delivery(
    state: State,
    gx: int,
    gy: int,
    fdx: int,
    fdy: int,
) -> bool:
    """Check if any cardinal neighbor delivers flow toward gunner tile.

    Conveyor: must point toward gunner tile (not on facing side).
    Harvester: always produces (adjacent = always has flow).
    Splitter: check side outputs point toward gunner.
    """
    w = state.w
    my_team = state.my_team
    for adx, ady in DIR4_DELTA:
        if adx == fdx and ady == fdy:
            continue  # gunner can't accept from facing side
        ax, ay = gx + adx, gy + ady
        if not state.in_bounds(ax, ay):
            continue
        ai = ay * w + ax
        abld = state.building[ai]
        if abld is None or abld.team != my_team:
            continue
        if isinstance(abld, BuildingHarvester):
            return True
        if isinstance(abld, (BuildingConveyor, BuildingArmouredConveyor)):
            ddx, ddy = abld.direction.delta()
            if (ax + ddx, ay + ddy) == (gx, gy):
                return True
        if isinstance(abld, BuildingSplitter):
            sdx, sdy = abld.direction.delta()
            for odx, ody in [(sdx, sdy), (-sdy, sdx), (sdy, -sdx)]:
                if (ax + odx, ay + ody) == (gx, gy):
                    return True
    return False
