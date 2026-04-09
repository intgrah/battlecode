"""Attack role: flow-gap chain extension + turret placement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from builder_econ import _task_explore_enemy, _task_harvest
from builder_helpers import (
    _UNBUILDABLE_ENV,
    _GUNNER_OFFSETS,
    _SENTINEL_OFFSETS,
    _can_place_gunner,
    _clear_tile,
    _has_friendly_gunner_covering,
    _has_los,
    _log,
    _task_destroy_enemy_infra,
    _tile_has_correct_transport,
)
from building import (
    MINOR_DESTROYABLE,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from chain_astar import AttackAstar
from util import DELTA_TO_DIR, DIR4_DELTA

if TYPE_CHECKING:
    from builder import Builder
    from nav import NavBfs
    from state import State


# -- Attack class (flow-gap model) --


class Attack:
    """Flow-gap attack: extend transport with Ti, drop turrets when useful/blocked."""

    def __init__(self) -> None:
        self.target: int | None = None
        self.gunner: int | None = None  # active turret tile
        self._committed_gap: int | None = None  # sticky gap tile index

    def run(self, ct: Controller, nav: NavBfs, s: State) -> tuple[str, bool]:
        w = s.w
        pos = ct.get_position()

        # Check if our turret is still alive -- don't wait by it
        if self.gunner is not None:
            result = self._recycle(ct, s)
            if result is not None:
                return result
            # Turret is active -- continue with other tasks, don't wait

        if ct.get_action_cooldown() != 0:
            return "atk:cooldown", False

        # Scan nearby tiles for flow gaps -- our transport with Ti
        # outputting to empty/enemy space
        best_gap = self._find_best_gap(ct, s, pos)

        # Sticky gap: if we committed last turn, check it's still valid
        if self._committed_gap is not None and best_gap is not None:
            cg = self._committed_gap
            # Still a valid gap?
            still_valid = any(gy * w + gx == cg for gx, gy in self._last_gaps)
            if still_valid and best_gap[1] != cg:
                # Override with committed gap (find its source from best_gap list)
                cox, coy = cg % w, cg // w
                for src_ti_c, out_ti_c, ox_c, oy_c in [best_gap]:
                    pass  # default
                # Scan gaps for the committed one
                for bid_c in ct.get_nearby_buildings():
                    bpos_c = ct.get_position(bid_c)
                    si_c = bpos_c.y * w + bpos_c.x
                    if _tile_has_correct_transport(s, si_c, cg, w):
                        best_gap = (si_c, cg, cox, coy)
                        break

        if best_gap is not None:
            self._committed_gap = best_gap[1]  # commit to this gap
            src_ti, out_ti, out_x, out_y = best_gap
            out_pos = Position(out_x, out_y)
            out_bld = s.building[out_ti]
            sx, sy = src_ti % w, src_ti // w
            src_bld = s.building[src_ti]
            src_name = type(src_bld).__name__[8:] if src_bld else "?"
            out_name = type(out_bld).__name__[8:] if out_bld else "empty"
            out_env = s.env[out_ti]
            env_name = out_env.name if out_env else "unseen"
            _log(
                f"  gap: src=({sx},{sy})={src_name} -> out=({out_x},{out_y})={out_name} env={env_name}",
                ct.get_id(),
            )

            # Check if a turret HERE would hit something valuable
            # (check before fire-at-enemy — turret is more valuable than
            # spending 3 turns firing at a road)
            result = self._try_turret_for_value(ct, nav, s, out_ti)
            if result is not None:
                return result

            # Enemy building at output -> walk on it and fire
            is_enemy = False
            if (
                out_bld is not None
                and out_bld.team != s.my_team
                and not isinstance(out_bld, BuildingMarker)
            ):
                is_enemy = True
            elif ct.is_in_vision(out_pos):
                obid = ct.get_tile_building_id(out_pos)
                if obid is not None and ct.get_team(obid) != s.my_team:
                    if ct.get_entity_type(obid) != EntityType.MARKER:
                        is_enemy = True

            if is_enemy:
                # Walk onto enemy building and fire at it
                if pos == out_pos:
                    if ct.get_action_cooldown() == 0 and ct.can_fire(out_pos):
                        ct.fire(out_pos)
                        return "atk:fire_enemy", True
                    return "atk:fire_cd", False
                nav.set_goal(out_pos)
                moved = nav.step(ct)
                return f"atk:walk_fire({out_x},{out_y})", moved

            # In enemy turret danger zone? Skip — gap scanner should have
            # filtered this, but recheck in case state changed.
            if out_ti in s.danger_zones:
                return "atk:danger_zone", False

            # Empty and buildable -> use A* to find next tile toward target
            out_env = s.env[out_ti]
            if out_env is None or out_env not in _UNBUILDABLE_ENV:
                if pos.distance_squared(out_pos) > 2:
                    nav.set_goal(out_pos)
                    moved = nav.step(ct)
                    return f"atk:walk({out_x},{out_y})", moved

                # A* from gap tile toward target
                tx, ty = self._target_xy(s, w)
                goals: set[int] = set()
                for gdx in range(-3, 4):
                    for gdy in range(-3, 4):
                        gx, gy = tx + gdx, ty + gdy
                        if s.in_bounds(gx, gy):
                            goals.add(gy * w + gx)

                search = AttackAstar(s, out_ti, goals)
                path = search.compute(
                    within_budget=lambda: ct.get_cpu_time_elapsed() < 1500
                )
                if path is None or len(path) < 2:
                    _log(f"  A* no_path from ({out_x},{out_y}) -> target ({tx},{ty})")
                    return "atk:no_path", False

                # First step of the path -- must NOT go back to source or
                # into existing transport (creates loops)
                ni = path[1]
                if ni == src_ti or ni in s.my_transport:
                    nx2, ny2 = ni % w, ni // w
                    _log(
                        f"  A* loop: ({out_x},{out_y}) -> ({nx2},{ny2}) in my_transport"
                    )
                    return "atk:no_path", False
                nx, ny = ni % w, ni // w
                path_preview = [(pi % w, pi // w) for pi in path[:6]]
                _log(f"  A* path: {path_preview} (len={len(path)}) target=({tx},{ty})")
                dx, dy = nx - out_x, ny - out_y
                conv_dir = DELTA_TO_DIR.get((dx, dy))
                if conv_dir is None:
                    # Bridge hop needed
                    b_cost, _ = ct.get_bridge_cost()
                    ti_res, _ = ct.get_global_resources()
                    if ti_res < b_cost:
                        return "atk:wait_ti", False
                    tgt_pos = Position(nx, ny)
                    _log(f"  bridge ({out_x},{out_y})->({nx},{ny})")
                    _clear_tile(ct, s, out_ti, out_pos)
                    if ct.can_build_bridge(out_pos, tgt_pos):
                        ct.build_bridge(out_pos, tgt_pos)
                        s.building[out_ti] = BuildingBridge(s.my_team, tgt_pos)
                        s.my_transport.add(out_ti)
                        return f"atk:bridge({out_x},{out_y})->({nx},{ny})", True
                    return "atk:build_fail", False

                c_cost, _ = ct.get_conveyor_cost()
                ti_res, _ = ct.get_global_resources()
                if ti_res < c_cost:
                    return "atk:wait_ti", False
                _clear_tile(ct, s, out_ti, out_pos)
                if ct.can_build_conveyor(out_pos, conv_dir):
                    ct.build_conveyor(out_pos, conv_dir)
                    s.building[out_ti] = BuildingConveyor(s.my_team, conv_dir)
                    s.my_transport.add(out_ti)
                    return f"atk:conv({out_x},{out_y})->{conv_dir.name}", True
                return "atk:build_fail", False

        self._committed_gap = None
        return "atk:no_gap", False

    def _find_best_gap(
        self, ct: Controller, s: State, pos: Position
    ) -> tuple[int, int, int, int] | None:
        """Find nearest transport tile with Ti outputting to empty/enemy space."""
        w = s.w
        my_team = s.my_team
        best: tuple[int, int, int, int] | None = None
        best_dist = 1_000_000
        self._last_gaps: list[tuple[int, int]] = []

        from building import (
            BuildingArmouredConveyor,
            BuildingSplitter,
        )

        n_transport = 0
        n_with_res = 0
        n_skip_econ = 0
        # Check nearby buildings for transport with resources (ours OR enemy)
        for bid in ct.get_nearby_buildings():
            etype = ct.get_entity_type(bid)
            if etype not in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
                EntityType.BRIDGE,
                EntityType.HARVESTER,
            ):
                continue
            n_transport += 1
            # Skip harvesters that already have our transport adjacent (econ's)
            if etype == EntityType.HARVESTER and ct.get_team(bid) == my_team:
                hpos = ct.get_position(bid)
                own_transport_count = 0
                for ddx, ddy in DIR4_DELTA:
                    ax, ay = hpos.x + ddx, hpos.y + ddy
                    if s.in_bounds(ax, ay):
                        abld = s.building[ay * w + ax]
                        if abld is not None and abld.team == my_team:
                            # Count transport + Ti-consuming turrets (not launchers/roads/markers/barriers)
                            if not isinstance(
                                abld,
                                (
                                    BuildingRoad,
                                    BuildingMarker,
                                    BuildingBarrier,
                                    BuildingLauncher,
                                ),
                            ):
                                own_transport_count += 1
                # On enemy half (or within 3 tiles of midpoint): attack can use
                # On our half: skip if any own building adjacent (econ's territory)
                cx, cy = s.core_pos.x, s.core_pos.y
                if s.en_core_pos is not None:
                    ex, ey = s.en_core_pos.x, s.en_core_pos.y
                else:
                    ex, ey = s.w - 1 - cx, s.h - 1 - cy
                _mid_x, _mid_y = (cx + ex) // 2, (cy + ey) // 2
                # Distance from harvester to midpoint toward enemy
                to_enemy = abs(hpos.x - ex) + abs(hpos.y - ey)
                to_core = abs(hpos.x - cx) + abs(hpos.y - cy)
                on_enemy_half = to_enemy <= to_core + 3
                threshold = 3 if on_enemy_half else 1
                if own_transport_count >= threshold:
                    n_skip_econ += 1
                    continue
            if etype in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
                EntityType.BRIDGE,
            ):
                if ct.get_stored_resource(bid) is None:
                    continue
            elif etype != EntityType.HARVESTER:
                continue

            bpos = ct.get_position(bid)
            si = bpos.y * w + bpos.x
            bld = s.building[si]
            if bld is None:
                continue

            # Find output tiles
            out_tiles: list[tuple[int, int]] = []
            match bld:
                case (
                    BuildingConveyor(direction=d)
                    | BuildingArmouredConveyor(direction=d)
                ):
                    ddx, ddy = d.delta()
                    out_tiles.append((bpos.x + ddx, bpos.y + ddy))
                case BuildingSplitter(direction=d):
                    ddx, ddy = d.delta()
                    for odx, ody in [(ddx, ddy), (-ddy, ddx), (ddy, -ddx)]:
                        out_tiles.append((bpos.x + odx, bpos.y + ody))
                case BuildingBridge(target=tgt):
                    out_tiles.append((tgt.x, tgt.y))
                case BuildingHarvester():
                    for ddx, ddy in DIR4_DELTA:
                        out_tiles.append((bpos.x + ddx, bpos.y + ddy))

            bx, by = bpos.x, bpos.y
            for ox, oy in out_tiles:
                if not s.in_bounds(ox, oy):
                    continue
                oi = oy * w + ox
                out_bld = s.building[oi]
                # Own road/marker/barrier = gap (destroyable). Anything else own = skip.
                if out_bld is not None and out_bld.team == my_team:
                    if not isinstance(
                        out_bld, (BuildingRoad, BuildingMarker, BuildingBarrier)
                    ):
                        _log(
                            f"    reject ({ox},{oy}): own {type(out_bld).__name__[8:]}",
                            ct.get_id(),
                        )
                        continue
                # Skip useless gaps
                if oi in s.danger_zones:
                    _log(f"    reject ({ox},{oy}): danger zone", ct.get_id())
                    continue
                out_env = s.env[oi]
                if out_env is not None and out_env in _UNBUILDABLE_ENV:
                    _log(f"    reject ({ox},{oy}): {out_env.name}", ct.get_id())
                    continue
                # Skip enemy buildings we can't easily remove
                if (
                    out_bld is not None
                    and out_bld.team != my_team
                    and not isinstance(out_bld, MINOR_DESTROYABLE)
                ):
                    _log(
                        f"    reject ({ox},{oy}): enemy {type(out_bld).__name__[8:]}",
                        ct.get_id(),
                    )
                    continue
                self._last_gaps.append((ox, oy))
                # Score: walk distance + distance to target (prefer gaps toward enemy)
                tx, ty = self._target_xy(s, w)
                walk_d = abs(pos.x - ox) + abs(pos.y - oy)
                target_d = abs(ox - tx) + abs(oy - ty)
                d = walk_d + target_d * 2
                if d < best_dist:
                    best_dist = d
                    best = (si, oi, ox, oy)

        if best is None and n_transport > 0:
            _log(
                f"  no_gap: {n_transport} transport, {n_skip_econ} skipped(econ), {len(self._last_gaps)} valid_gaps",
                ct.get_id(),
            )
        return best

    def _place_turret_near(
        self,
        ct: Controller,
        nav: NavBfs,
        s: State,
        enemy_ti: int,
        feed_ti: int,
    ) -> tuple[str, bool] | None:
        """Place turret near enemy_ti, fed from feed_ti direction."""
        w = s.w
        ex, ey = enemy_ti % w, enemy_ti // w
        fx, fy = feed_ti % w, feed_ti // w

        # Try tiles adjacent to the enemy that are placeable and not the feed
        candidates = [enemy_ti]
        for ddx, ddy in DIR4_DELTA:
            nx, ny = ex + ddx, ey + ddy
            if s.in_bounds(nx, ny):
                candidates.append(ny * w + nx)

        for gi in candidates:
            if gi == feed_ti:
                continue  # don't destroy our feed
            if not _can_place_gunner(s, gi):
                continue
            gx, gy = gi % w, gi // w
            # Face toward the enemy
            fdx = 0 if ex == gx else (1 if ex > gx else -1)
            fdy = 0 if ey == gy else (1 if ey > gy else -1)
            if fdx == 0 and fdy == 0:
                # We're ON the enemy tile -- face away from feed
                fdx = 0 if fx == gx else (1 if gx > fx else -1)
                fdy = 0 if fy == gy else (1 if gy > fy else -1)
            if fdx == 0 and fdy == 0:
                continue
            # Check feed direction doesn't equal facing
            chain_dx, chain_dy = fx - gx, fy - gy
            if (chain_dx, chain_dy) == (fdx, fdy):
                continue
            result = self._place_turret(ct, nav, s, gi, enemy_ti)
            if result[1] or "walk" in result[0]:
                return result
            # Placement failed — try next candidate

        return None

    def _try_turret_for_value(
        self, ct: Controller, nav: NavBfs, s: State, ti: int
    ) -> tuple[str, bool] | None:
        """If placing a turret at ti can hit a high-value enemy target, do it."""
        w = s.w
        tx, ty = ti % w, ti // w
        # Don't place turrets in danger zones
        if ti in s.danger_zones:
            return None
        en_hvt = s.en_core_tiles | s.en_turrets | s.en_harvesters

        for eti in en_hvt:
            ex, ey = eti % w, eti // w
            delta = (ex - tx, ey - ty)
            if delta in _GUNNER_OFFSETS:
                _log(f"  turret_value: gunner at ({tx},{ty}) -> enemy ({ex},{ey})")
                result = self._place_turret(ct, nav, s, ti, eti)
                # Only return if turret placed or walking to place — not failures
                if result[1] or "walk" in result[0]:
                    return result
                # Placement failed (no_los, no_feed, etc.) — try next target

        return None

    def _place_turret(
        self,
        ct: Controller,
        nav: NavBfs,
        s: State,
        gi: int,
        enemy_ti: int,
        *,
        sentinel: bool = False,
    ) -> tuple[str, bool]:
        """Place gunner or sentinel at gi facing enemy_ti."""
        w = s.w
        pos = ct.get_position()
        gx, gy = gi % w, gi // w
        ex, ey = enemy_ti % w, enemy_ti // w

        if not _can_place_gunner(s, gi):
            return f"atk:cant_place({gx},{gy})", False

        # Verify target is actually hittable from this tile
        delta = (ex - gx, ey - gy)
        if not sentinel and delta not in _GUNNER_OFFSETS:
            return f"atk:out_of_range({gx},{gy})", False
        if sentinel and delta not in _SENTINEL_OFFSETS:
            return f"atk:out_of_range({gx},{gy})", False

        fdx = 0 if ex == gx else (1 if ex > gx else -1)
        fdy = 0 if ey == gy else (1 if ey > gy else -1)
        if fdx == 0 and fdy == 0:
            return f"atk:no_face({gx},{gy})", False

        # Verify LoS — ray must reach enemy (not blocked by walls/friendlies)
        if not sentinel and _has_los(s, gx, gy, fdx, fdy) is None:
            return f"atk:no_los({gx},{gy})", False

        # Check adjacent non-facing tiles for valid ammo sources.
        # Must output toward turret AND have actual flow (connected or recent Ti).
        has_valid_feed = False
        for adx, ady in DIR4_DELTA:
            if (adx, ady) == (fdx, fdy):
                continue  # facing side -- turret can't receive from here
            ax, ay = gx + adx, gy + ady
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            abld = s.building[ai]
            if abld is None:
                continue
            if isinstance(abld, BuildingHarvester) and abld.team == s.my_team:
                has_valid_feed = True  # harvesters output all directions
                break
            if (
                abld.team == s.my_team
                and _tile_has_correct_transport(s, ai, gi, w)
                and (ai in s.connected_transport or ai in s.tiles_with_flow)
            ):
                has_valid_feed = True  # transport with actual flow
                break
        if not has_valid_feed:
            return f"atk:no_feed({gx},{gy})", False

        facing = DELTA_TO_DIR.get((fdx, fdy))
        if facing is None:
            return f"atk:no_face({gx},{gy})", False

        gpos = Position(gx, gy)

        if pos == gpos:
            for d in Direction:
                if d != Direction.CENTRE and ct.can_move(d):
                    ct.move(d)
                    return f"atk:stepoff({gx},{gy})", True
            return f"atk:trapped({gx},{gy})", False

        if pos.distance_squared(gpos) > 2:
            nav.set_goal(gpos)
            moved = nav.step(ct)
            return f"atk:turret_walk({gx},{gy})", moved

        _clear_tile(ct, s, gi, gpos)

        # Try to destroy own building if still blocking
        if sentinel:
            cost, _ = ct.get_sentinel_cost()
        else:
            cost, _ = ct.get_gunner_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < cost:
            return "atk:wait_ti", False

        if not sentinel and ct.can_build_gunner(gpos, facing):
            ct.build_gunner(gpos, facing)
            from building import BuildingGunner

            s.building[gi] = BuildingGunner(s.my_team, facing)
            self.gunner = gi
            return f"atk:gunner({gx},{gy})", True
        if sentinel and ct.can_build_sentinel(gpos, facing):
            ct.build_sentinel(gpos, facing)
            from building import BuildingSentinel

            s.building[gi] = BuildingSentinel(s.my_team, facing)
            self.gunner = gi
            return f"atk:sentinel({gx},{gy})", True

        return f"atk:turret_fail({gx},{gy})", False

    def _target_xy(self, s: State, w: int) -> tuple[int, int]:
        """Get target coords for conveyor direction."""
        if self.target is not None:
            return self.target % w, self.target // w
        if s.en_core_pos is not None:
            return s.en_core_pos.x, s.en_core_pos.y
        return w - 1 - s.core_pos.x, s.h - 1 - s.core_pos.y

    def _recycle(self, ct: Controller, s: State) -> tuple[str, bool] | None:
        """Check if turret is dead (self-destructed or destroyed). Clear tracking."""
        gti = self.gunner
        if gti is None:
            return None

        bld = s.building[gti]
        if bld is None or bld.team != s.my_team:
            self.gunner = None
            return "atk:turret_gone", False

        return None


_RAY_DIRS_8: tuple[tuple[int, int], ...] = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)


def _ray_clear_to_target(
    s: State, gx: int, gy: int, fdx: int, fdy: int, tx: int, ty: int
) -> bool:
    """Walk a gunner ray and check we reach (tx,ty) without friendly blockage."""
    w, h = s.w, s.h
    my_team = s.my_team
    x, y = gx + fdx, gy + fdy
    while 0 <= x < w and 0 <= y < h:
        if (x - gx) ** 2 + (y - gy) ** 2 > 13:
            break
        if x == tx and y == ty:
            return True
        ni = y * w + x
        env = s.env[ni]
        if env == Environment.WALL:
            return False
        bld = s.building[ni]
        if bld is not None and not isinstance(bld, BuildingMarker):
            if bld.team == my_team:
                return False  # own building blocks
            # Enemy building blocks the ray here — target must be exactly here
            return False
        x += fdx
        y += fdy
    return False


def _task_raid_harvester(builder: Builder, ct: Controller) -> tuple[str, bool] | None:
    """Place a gunner adjacent to a visible enemy harvester to kill it.

    Only triggers when we already see an enemy harvester AND can find a
    valid gunner placement (LoS + ammo feed). Otherwise returns None and
    the builder falls through to the existing flow-gap attack logic.

    Ammo feed accepts any transport on a non-facing side — friendly OR
    enemy (parasitizing enemy flow as ammo).
    """
    s = builder.state
    w = s.w
    pos = ct.get_position()
    my_team = s.my_team

    if ct.get_action_cooldown() != 0:
        return None

    if not s.en_harvesters:
        return None

    g_cost, _ = ct.get_gunner_cost()
    ti_res, _ = ct.get_global_resources()
    if ti_res < g_cost:
        return None

    # Search all visible enemy harvesters for one with a valid placement
    feeder_tiles_friendly: set[int] = s.my_transport | s.my_harvesters
    enemy_transport: set[int] = s.en_transport | s.en_harvesters

    best_gpos: Position | None = None
    best_facing: Direction | None = None
    best_walk = 1_000_000
    best_target_hi: int | None = None

    for hi in s.en_harvesters:
        hx, hy = hi % w, hi // w
        # Already covered by a friendly gunner? Skip.
        if _has_friendly_gunner_covering(s, hi):
            continue
        # Need to be within reasonable walk distance — don't trek across map
        if abs(pos.x - hx) + abs(pos.y - hy) > 10:
            continue
        for rdx, rdy in _RAY_DIRS_8:
            for dist in range(1, 4):
                gx, gy = hx + rdx * dist, hy + rdy * dist
                if not s.in_bounds(gx, gy):
                    break
                if (gx - hx) ** 2 + (gy - hy) ** 2 > 13:
                    break
                gi = gy * w + gx
                if not _can_place_gunner(s, gi):
                    continue
                fdx, fdy = -rdx, -rdy
                facing = DELTA_TO_DIR.get((fdx, fdy))
                if facing is None:
                    continue
                has_feed = False
                for adx, ady in DIR4_DELTA:
                    if (adx, ady) == (fdx, fdy):
                        continue
                    fax, fay = gx + adx, gy + ady
                    if not s.in_bounds(fax, fay):
                        continue
                    fai = fay * w + fax
                    fbld = s.building[fai]
                    if fbld is None:
                        continue
                    if isinstance(fbld, BuildingHarvester) and fbld.team == my_team:
                        has_feed = True
                        break
                    if fai in feeder_tiles_friendly and _tile_has_correct_transport(
                        s, fai, gi, w
                    ):
                        has_feed = True
                        break
                    if fai in enemy_transport:
                        if isinstance(fbld, BuildingHarvester):
                            has_feed = True
                            break
                        if _tile_has_correct_transport(s, fai, gi, w):
                            has_feed = True
                            break
                if not has_feed:
                    continue
                if not _ray_clear_to_target(s, gx, gy, fdx, fdy, hx, hy):
                    continue
                walk = abs(pos.x - gx) + abs(pos.y - gy)
                if walk < best_walk:
                    best_walk = walk
                    best_gpos = Position(gx, gy)
                    best_facing = facing
                    best_target_hi = hi

    if best_gpos is None or best_facing is None or best_target_hi is None:
        return None

    gi = best_gpos.y * w + best_gpos.x

    if pos.distance_squared(best_gpos) > 2:
        builder.nav.set_goal(best_gpos)
        moved = builder.nav.step(ct)
        return f"atk:raid_walk_g({best_gpos.x},{best_gpos.y})", moved

    if pos == best_gpos:
        for d in Direction:
            if d != Direction.CENTRE and ct.can_move(d):
                ct.move(d)
                return "atk:raid_stepoff", True
        return None

    _clear_tile(ct, s, gi, best_gpos)

    if ct.can_build_gunner(best_gpos, best_facing):
        ct.build_gunner(best_gpos, best_facing)
        s.building[gi] = BuildingGunner(s.my_team, best_facing)
        s.my_turrets.add(gi)
        return f"atk:raid_gunner({best_gpos.x},{best_gpos.y})", True

    return None


def _run_attack(builder: Builder, ct: Controller) -> tuple[str, bool]:
    a = builder._attack
    s = builder.state
    pos = ct.get_position()

    # Raid disabled — too unreliable, pulls attack builders off flow-gap
    # extension which produces better results. Code kept for iteration.
    # raid = _task_raid_harvester(builder, ct)
    # if raid is not None:
    #     return raid

    # Fire at enemy transport we're standing on (not random roads)
    if ct.get_action_cooldown() == 0:
        bid = ct.get_tile_building_id(pos)
        if bid is not None and ct.get_team(bid) != s.my_team:
            etype = ct.get_entity_type(bid)
            if etype in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
                EntityType.BRIDGE,
                EntityType.HARVESTER,
                EntityType.BARRIER,
            ) and ct.can_fire(pos):
                ct.fire(pos)
                return "atk:fire_infra", True

    # Find target if needed
    if a.target is None:
        en = s.en_core_tiles | s.en_harvesters | s.en_transport | s.en_turrets
        if s.en_core_pos is not None and not en:
            a.target = s.en_core_pos.y * s.w + s.en_core_pos.x
        elif en:
            pos = ct.get_position()
            best_ti: int | None = None
            best_score = 1_000_000
            for ei in en:
                ex, ey = ei % s.w, ei // s.w
                sc = abs(pos.x - ex) + abs(pos.y - ey)
                if ei in s.en_core_tiles:
                    sc -= 100
                if sc < best_score:
                    best_score = sc
                    best_ti = ei
            if best_ti is not None:
                a.target = best_ti

    # Delegate to Attack class
    result = a.run(ct, builder.nav, s)

    # No gaps to extend -- place harvesters, destroy enemy, or explore
    if result[0] in ("atk:no_target", "atk:no_source", "atk:no_gap"):
        tgt_str = f"({a.target % s.w},{a.target // s.w})" if a.target else "none"
        _log(f"  {result[0]} target={tgt_str}", ct.get_id())
        # Attack: place harvesters near the enemy target
        tgt_pos = None
        if a.target is not None:
            tgt_pos = Position(a.target % s.w, a.target // s.w)
        elif s.en_core_pos is not None:
            tgt_pos = s.en_core_pos
        # Only harvest when we have a target to attack toward
        if tgt_pos is not None:
            harvest = _task_harvest(builder, ct, target_pos=tgt_pos)
            if harvest is not None:
                return harvest
        infra = _task_destroy_enemy_infra(builder.state, builder.nav, ct)
        if infra is not None:
            return infra
        return _task_explore_enemy(builder, ct)

    return result
