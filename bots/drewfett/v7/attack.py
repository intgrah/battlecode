"""Attack chain builder — frontier-tracking model.

Builds a conveyor chain from a Ti source toward an enemy target.
Drops gunners when enemy buildings are encountered.
Tracks a frontier tile (furthest built transport) that only advances.

Usage from builder.py:
    self._attack = Attack(state)
    ...
    result = self._attack.run(ct, nav, state)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingBarrier,
    BuildingGunner,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from chain_astar import AttackAstar
from marker import MarkerIdleGunner
from marker import decode as _decode_marker
from util import DELTA_TO_DIR, DIR4_DELTA

if TYPE_CHECKING:
    from nav import NavBfs
    from state import State

# Tiles we can build conveyors/bridges on (after destroying what's there)
_BUILDABLE_ENV = frozenset(
    {Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE}
)


class Attack:
    """Manages one attack chain from source to target."""

    def __init__(self) -> None:
        self.target: int | None = None  # enemy tile to push toward
        self.source: int | None = None  # Ti source (harvester free side)
        self.frontier: int | None = None  # furthest tile with our transport
        self.gunner: int | None = None  # active gunner tile
        self._stuck: int = 0

    def run(self, ct: Controller, nav: NavBfs, s: State) -> tuple[str, bool]:
        """Main entry point — called once per turn by the attack builder."""
        w = s.w
        pos = ct.get_position()

        self._invalidate(s)

        # 1. Gunner active → wait for idle → recycle
        if self.gunner is not None:
            result = self._recycle(ct, s)
            if result is not None:
                return result
            gx, gy = self.gunner % w, self.gunner // w
            gpos = Position(gx, gy)
            if pos.distance_squared(gpos) > 2:
                nav.set_goal(gpos)
                moved = nav.step(ct)
                return f"atk:wait_gunner({gx},{gy})", moved
            return "atk:gunner_active", False

        # 2. Frontier exists → advance
        if self.frontier is not None:
            return self._advance(ct, nav, s)

        # 3. Target but no chain → find source, set frontier
        if self.target is not None:
            return self._init_chain(ct, s)

        # 4. No target
        return "atk:no_target", False

    # -- Invalidation --

    def _invalidate(self, s: State) -> None:
        w = s.w

        # Target gone
        if self.target is not None:
            env = s.env[self.target]
            if env is not None and env == Environment.WALL:
                self.target = None
                self.frontier = None
                self.source = None

        # Source harvester destroyed
        if self.source is not None:
            found = False
            for dx, dy in DIR4_DELTA:
                nx, ny = self.source % w + dx, self.source // w + dy
                if s.in_bounds(nx, ny) and isinstance(
                    s.building[ny * w + nx], BuildingHarvester
                ):
                    found = True
                    break
            if not found:
                self.source = None
                # Keep frontier — chain may still be fed by another harvester

        # Frontier tile taken by enemy
        if self.frontier is not None and self.frontier != self.source:
            bld = s.building[self.frontier]
            # Only retreat if enemy built on our frontier (not if we cleared it)
            if (
                bld is not None
                and bld.team != s.my_team
                and not isinstance(bld, BuildingMarker)
            ):
                self.frontier = self.source

        # Gunner destroyed
        if self.gunner is not None:
            bld = s.building[self.gunner]
            if not isinstance(bld, BuildingGunner) or bld.team != s.my_team:
                self.gunner = None

    # -- Init chain --

    def _init_chain(self, ct: Controller, s: State) -> tuple[str, bool]:
        w = s.w
        target = self.target
        if target is None:
            return "atk:no_target", False

        tx, ty = target % w, target // w
        source = _find_source(s, tx, ty)
        if source is None:
            return "atk:no_source", False

        self.source = source
        self.frontier = source
        self._stuck = 0
        return f"atk:init src=({source % w},{source // w})", False

    # -- Advance frontier --

    def _advance(self, ct: Controller, nav: NavBfs, s: State) -> tuple[str, bool]:
        w = s.w
        pos = ct.get_position()
        frontier = self.frontier
        target = self.target

        if frontier is None or target is None:
            return "atk:no_state", False

        fx, fy = frontier % w, frontier // w
        tx, ty = target % w, target // w
        dist = abs(fx - tx) + abs(fy - ty)

        # Close to target — place gunner
        if dist <= 4:
            result = self._place_gunner(ct, nav, s)
            if result is not None:
                return result
            # Can't place gunner — keep extending

        # Short A* from frontier toward target
        goals: set[int] = set()
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                gx, gy = tx + dx, ty + dy
                if s.in_bounds(gx, gy):
                    goals.add(gy * w + gx)

        search = AttackAstar(s, frontier, goals)
        path = search.compute(within_budget=lambda: ct.get_cpu_time_elapsed() < 1500)
        if path is None or len(path) < 2:
            self._stuck += 1
            if self._stuck >= 10:
                self.target = None
                self.frontier = None
                self.source = None
                self._stuck = 0
            return "atk:no_path", False

        self._stuck = 0

        # Walk the path, find first gap
        for k in range(len(path) - 1):
            ci, ni = path[k], path[k + 1]

            # Already built correctly — advance frontier
            if _tile_has_transport(s, ci, ni, w):
                self.frontier = ci
                continue

            cx, cy = ci % w, ci // w
            nx, ny = ni % w, ni // w

            # Enemy building on this or next tile → drop gunner
            for check_ti in (ci, ni):
                bld = s.building[check_ti]
                if (
                    bld is not None
                    and bld.team != s.my_team
                    and not isinstance(bld, BuildingMarker)
                ):
                    return self._place_gunner_at(ct, nav, s, ci, check_ti)

            # Terrain block
            env = s.env[ci]
            if env is not None and env in _BUILDABLE_ENV:
                return f"atk:terrain({cx},{cy})", False

            # Walk to gap if not adjacent
            build_pos = Position(cx, cy)
            if pos.distance_squared(build_pos) > 2:
                nav.set_goal(build_pos)
                moved = nav.step(ct)
                return f"atk:walk({cx},{cy})", moved

            # Build conveyor or bridge
            return self._build(ct, s, ci, ni, cx, cy, nx, ny, build_pos)

        # All gaps filled — place gunner at end
        self.frontier = path[-1]
        result = self._place_gunner(ct, nav, s)
        if result is not None:
            return result
        return "atk:chain_complete", False

    # -- Build one tile --

    def _build(
        self,
        ct: Controller,
        s: State,
        ci: int,
        ni: int,
        cx: int,
        cy: int,
        nx: int,
        ny: int,
        build_pos: Position,
    ) -> tuple[str, bool]:
        dx, dy = nx - cx, ny - cy
        conv_dir = DELTA_TO_DIR.get((dx, dy))

        if conv_dir is not None:
            # Cardinal conveyor
            c_cost, _ = ct.get_conveyor_cost()
            ti, _ = ct.get_global_resources()
            if ti < c_cost:
                return "atk:wait_ti", False
            _clear_tile(ct, s, ci, build_pos)
            if ct.can_build_conveyor(build_pos, conv_dir):
                ct.build_conveyor(build_pos, conv_dir)
                from building import BuildingConveyor

                s.building[ci] = BuildingConveyor(s.my_team, conv_dir)
                s.my_transport.add(ci)
                self.frontier = ci
                return f"atk:conv({cx},{cy})->{conv_dir.name}", True
            # Build failed — only destroy road/marker/barrier (not transport)
            _clear_tile(ct, s, ci, build_pos)
            bid = ct.get_tile_building_id(build_pos)
            if bid is None:
                return f"atk:cleared({cx},{cy})", False  # cleared, retry
            return f"atk:conv_fail({cx},{cy})", False

        # Bridge
        target_pos = Position(nx, ny)
        # Verify target tile
        target_env = s.env[ni]
        if target_env is not None and target_env in _BUILDABLE_ENV:
            return f"atk:bridge_blocked({nx},{ny})", False
        target_bld = s.building[ni]
        if (
            target_bld is not None
            and target_bld.team != s.my_team
            and not isinstance(target_bld, BuildingMarker)
        ):
            return f"atk:bridge_enemy({nx},{ny})", False
        if ni in s.danger_zones:
            return f"atk:bridge_danger({nx},{ny})", False
        # Check landing tile or an adjacent tile is BFS-reachable
        if s.nav is not None:
            reachable = s.nav.is_passable(Position(nx, ny))
            if not reachable:
                for ddx, ddy in DIR4_DELTA:
                    ax, ay = nx + ddx, ny + ddy
                    if s.in_bounds(ax, ay) and s.nav.is_passable(Position(ax, ay)):
                        reachable = True
                        break
            if not reachable:
                return f"atk:bridge_unreachable({nx},{ny})", False

        b_cost, _ = ct.get_bridge_cost()
        ti, _ = ct.get_global_resources()
        if ti < b_cost:
            return "atk:wait_ti", False
        _clear_tile(ct, s, ci, build_pos)
        if ct.can_build_bridge(build_pos, target_pos):
            ct.build_bridge(build_pos, target_pos)
            from building import BuildingBridge

            s.building[ci] = BuildingBridge(s.my_team, target_pos)
            s.my_transport.add(ci)
            self.frontier = ci
            return f"atk:bridge({cx},{cy})->({nx},{ny})", True
        # Build failed — destroy any own building and retry
        bid = ct.get_tile_building_id(build_pos)
        if bid is not None and ct.get_team(bid) == ct.get_team():
            if ct.can_destroy(build_pos):
                ct.destroy(build_pos)
                s.building[ci] = None
                s.my_transport.discard(ci)
                return f"atk:cleared({cx},{cy})", False
        return f"atk:bridge_fail({cx},{cy})", False

    # -- Place gunner facing enemy --

    def _place_gunner_at(
        self,
        ct: Controller,
        nav: NavBfs,
        s: State,
        gi: int,
        enemy_ti: int,
    ) -> tuple[str, bool]:
        w = s.w
        pos = ct.get_position()
        gx, gy = gi % w, gi // w
        ex, ey = enemy_ti % w, enemy_ti // w

        if not _can_place_gunner(s, gi):
            return f"atk:cant_gunner({gx},{gy})", False

        fdx = 0 if ex == gx else (1 if ex > gx else -1)
        fdy = 0 if ey == gy else (1 if ey > gy else -1)
        if fdx == 0 and fdy == 0:
            return f"atk:no_face({gx},{gy})", False
        facing = DELTA_TO_DIR.get((fdx, fdy))
        if facing is None:
            return f"atk:no_face({gx},{gy})", False

        g_cost, _ = ct.get_gunner_cost()
        ti, _ = ct.get_global_resources()
        if ti < g_cost:
            return "atk:gunner_wait_ti", False

        gpos = Position(gx, gy)

        # Step off if we're standing on the tile
        if pos == gpos:
            for d in Direction:
                if d != Direction.CENTRE and ct.can_move(d):
                    ct.move(d)
                    return f"atk:stepoff({gx},{gy})", True
            return f"atk:trapped({gx},{gy})", False

        if pos.distance_squared(gpos) > 2:
            nav.set_goal(gpos)
            moved = nav.step(ct)
            return f"atk:gunner_walk({gx},{gy})", moved

        # Clear the tile for gunner placement — destroy any own building
        # (this is the frontier tile, we're replacing it with a gunner)
        _clear_tile(ct, s, gi, gpos)
        if not ct.can_build_gunner(gpos, facing):
            # Still blocked — force destroy own building (e.g. our conveyor)
            bid = ct.get_tile_building_id(gpos)
            if bid is not None and ct.get_team(bid) == ct.get_team():
                if ct.can_destroy(gpos):
                    ct.destroy(gpos)
                    s.building[gi] = None
                    s.my_transport.discard(gi)

        if ct.can_build_gunner(gpos, facing):
            ct.build_gunner(gpos, facing)
            from building import BuildingGunner

            s.building[gi] = BuildingGunner(s.my_team, facing)
            self.gunner = gi
            return f"atk:gunner({gx},{gy})", True

        return f"atk:gunner_fail({gx},{gy})", False

    # -- Place gunner near frontier facing target --

    def _place_gunner(
        self, ct: Controller, nav: NavBfs, s: State
    ) -> tuple[str, bool] | None:
        w = s.w
        frontier = self.frontier
        target = self.target
        if frontier is None or target is None:
            return None

        fx, fy = frontier % w, frontier // w
        # Try frontier + cardinal neighbors
        candidates = [frontier]
        for dx, dy in DIR4_DELTA:
            nx, ny = fx + dx, fy + dy
            if s.in_bounds(nx, ny):
                candidates.append(ny * w + nx)

        for gi in candidates:
            if not _can_place_gunner(s, gi):
                continue
            return self._place_gunner_at(ct, nav, s, gi, target)

        return None

    # -- Recycle idle gunner --

    def _recycle(self, ct: Controller, s: State) -> tuple[str, bool] | None:
        w = s.w
        gunner_ti = self.gunner
        if gunner_ti is None:
            return None

        # Gunner gone?
        bld = s.building[gunner_ti]
        if not (isinstance(bld, BuildingGunner) and bld.team == s.my_team):
            self.gunner = None
            return "atk:gunner_gone", False

        # Check for idle marker
        for tile in ct.get_nearby_tiles():
            ti = tile.y * w + tile.x
            mbld = s.building[ti]
            if not isinstance(mbld, BuildingMarker) or mbld.team != s.my_team:
                continue
            msg = _decode_marker(mbld.value)
            if isinstance(msg, MarkerIdleGunner) and msg.gunner_tile_index == gunner_ti:
                gx, gy = gunner_ti % w, gunner_ti // w
                gpos = Position(gx, gy)
                pos = ct.get_position()
                if pos.distance_squared(gpos) <= 2 and ct.can_destroy(gpos):
                    ct.destroy(gpos)
                    s.building[gunner_ti] = None
                    self.gunner = None
                    # Clean up marker
                    mpos = Position(tile.x, tile.y)
                    if ct.can_destroy(mpos):
                        ct.destroy(mpos)
                        s.building[ti] = None
                    return "atk:recycled", True
                return f"atk:recycle_walk({gx},{gy})", False

        return None  # still fighting


# -- Module-level helpers --


def _find_source(s: State, tx: int, ty: int) -> int | None:
    """Find best Ti source (harvester free side) closest to target."""
    w = s.w
    best: int | None = None
    best_dist = 1_000_000

    for hi in s.my_harvesters:
        hx, hy = hi % w, hi // w
        for dx, dy in DIR4_DELTA:
            fx, fy = hx + dx, hy + dy
            if not s.in_bounds(fx, fy):
                continue
            fi = fy * w + fx
            env = s.env[fi]
            if env is not None and env in _BUILDABLE_ENV:
                continue
            bld = s.building[fi]
            if bld is not None and not isinstance(
                bld, (BuildingRoad, BuildingMarker, BuildingBarrier)
            ):
                continue
            dist = abs(fx - tx) + abs(fy - ty)
            if dist < best_dist:
                best_dist = dist
                best = fi

    # Also check enemy harvesters (parasitize)
    for hi in s.en_harvesters:
        hx, hy = hi % w, hi // w
        for dx, dy in DIR4_DELTA:
            fx, fy = hx + dx, hy + dy
            if not s.in_bounds(fx, fy):
                continue
            fi = fy * w + fx
            env = s.env[fi]
            if env is not None and env in _BUILDABLE_ENV:
                continue
            bld = s.building[fi]
            if bld is not None and not isinstance(bld, (BuildingRoad, BuildingMarker)):
                continue
            dist = abs(fx - tx) + abs(fy - ty)
            if dist < best_dist:
                best_dist = dist
                best = fi

    return best


def _tile_has_transport(s: State, ci: int, ni: int, w: int) -> bool:
    """Check if tile ci has our transport outputting toward ni."""
    if ci in s.core_tiles:
        return True
    bld = s.building[ci]
    if isinstance(bld, BuildingHarvester):
        return True
    if bld is None or bld.team != s.my_team:
        return False

    from building import (
        BuildingArmouredConveyor,
        BuildingBridge,
        BuildingConveyor,
        BuildingFoundry,
        BuildingSplitter,
    )

    cx, cy = ci % w, ci // w
    nx, ny = ni % w, ni // w
    match bld:
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            ddx, ddy = d.delta()
            return (cx + ddx, cy + ddy) == (nx, ny)
        case BuildingSplitter(direction=d):
            ddx, ddy = d.delta()
            for odx, ody in [(ddx, ddy), (-ddy, ddx), (ddy, -ddx)]:
                if (cx + odx, cy + ody) == (nx, ny):
                    return True
            return False
        case BuildingBridge(target=tgt):
            return (tgt.x, tgt.y) == (nx, ny)
        case BuildingFoundry():
            return True
    return False


def _can_place_gunner(s: State, gi: int) -> bool:
    """Check if tile is valid for gunner placement."""
    env = s.env[gi]
    if env is not None and env in _BUILDABLE_ENV:
        return False
    if gi in s.danger_zones:
        return False
    bld = s.building[gi]
    if bld is not None:
        if isinstance(bld, BuildingMarker):
            return True
        if bld.team == s.my_team:
            return True  # can destroy own building
        return False
    return True


def _clear_tile(ct: Controller, s: State, ti: int, pos: Position) -> None:
    """Destroy own road/marker/barrier at tile to make room for building."""
    # Don't destroy econ transport
    if ti in s.connected_transport:
        return
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    etype = ct.get_entity_type(bid)
    if etype in (EntityType.ROAD, EntityType.MARKER, EntityType.BARRIER):
        if ct.can_destroy(pos):
            ct.destroy(pos)
            s.building[ti] = None
