"""Reactive defense: counter enemy turrets threatening our infrastructure.

Scans for enemy turrets near our harvesters/transport/core. Finds a
gunner position with LoS to the threat AND adjacent flow (ammo source).
Uses our flow model to check ammo availability.

Only responds if this builder is the closest to the threat and no
friendly gunner already covers it.
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
from cambc import Controller, Direction, Position
from util import DIR4_DELTA, DIR8_DELTA

from .action import Action, PlaceGunner
from .helpers import move_toward_with_road, step_off_and_build

if TYPE_CHECKING:
    from .state import State

_THREAT_RANGE_SQ = 36  # threat within d²=36 of our infra
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
            from cambc import Environment

            if env == Environment.WALL:
                break
            bld = state.building[gi]
            if bld is not None and not isinstance(bld, (BuildingRoad, BuildingMarker)):
                break

            # Check LoS back to threat (nothing blocking in between)
            los_ok = True
            _cx, _cy = gx + dx * (-1), gy + dy * (-1)  # one step toward threat
            # Actually just check: facing direction
            fdx = -dx if dx != 0 else 0
            fdy = -dy if dy != 0 else 0
            from util import DELTA_TO_DIR

            facing = DELTA_TO_DIR.get((fdx, fdy))
            if facing is None:
                continue

            # Verify LoS
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

            # Check ammo: adjacent harvester or transport with flow (not facing side)
            has_ammo = False
            for adx, ady in DIR4_DELTA:
                if adx == fdx and ady == fdy:
                    continue  # gunner can't accept from facing side
                ax, ay = gx + adx, gy + ady
                if not state.in_bounds(ax, ay):
                    continue
                ai = ay * w + ax
                abld = state.building[ai]
                if isinstance(abld, BuildingHarvester):
                    has_ammo = True
                    break
                if isinstance(
                    abld, (BuildingConveyor, BuildingArmouredConveyor, BuildingSplitter)
                ) and abld.team == my_team and state.flow.ti[ai] > 0.05:
                    has_ammo = True
                    break
            if not has_ammo:
                continue

            walk = (pos.x - gx) ** 2 + (pos.y - gy) ** 2
            if walk < best_score:
                best_score = walk
                best_gpos = Position(gx, gy)
                best_facing = facing

    if best_gpos is None or best_facing is None:
        return None

    # Place the gunner
    g_cost, _ = ct.get_gunner_cost()
    ti_res, _ = ct.get_global_resources()
    if ti_res < g_cost:
        return None

    ni = best_gpos.y * w + best_gpos.x
    if pos == best_gpos:
        return step_off_and_build(ct, PlaceGunner(best_gpos, best_facing))
    if pos.distance_squared(best_gpos) <= 2:
        bld = state.building[ni]
        if bld is not None and bld.team == my_team and ct.can_destroy(best_gpos):
            ct.destroy(best_gpos)
        if ct.can_build_gunner(best_gpos, best_facing):
            return Direction.CENTRE, PlaceGunner(best_gpos, best_facing)
    return move_toward_with_road(state, ct, best_gpos)
