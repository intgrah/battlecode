"""Attack role: flow-forward chain extension with opportunistic turret placement.

Find a flow source (harvester/transport output tile) → extend chain toward enemy
via A* → at each gap, check if a turret placed there has LoS to an enemy HVT →
place turret (gunner preferred, sentinel fallback) or build conveyor and continue.

The chain grows greedily from flow toward enemy. No pre-selected gunner position.
Turrets are placed as soon as LoS exists. Never routes through connected_transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from builder_econ import _build_at_gap, _task_explore_enemy, _task_harvest
from builder_helpers import (
    _clear_tile,
    DEBUG,
    _log,
    _task_destroy_enemy_infra,
    _tile_has_correct_transport,
    try_place_turret_at,
)
from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
    TRANSPORT,
    TURRETS,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from chain_astar import AttackAstar
from util import DELTA_TO_DIR, DIR4_DELTA, DIR8_DELTA

if TYPE_CHECKING:
    from builder import Builder
    from nav import NavBfs
    from state import State

# Tiles treated as "free" for flow source output checks
_FREE_TYPES = (BuildingRoad, BuildingMarker)
_TRANSPORT_OR_TURRETS = TRANSPORT + TURRETS

# Enemy buildings worth shooting (turret targets). NOT barrier/road/marker.
_HVT_TYPES = (
    BuildingConveyor,
    BuildingArmouredConveyor,
    BuildingSplitter,
    BuildingBridge,
    BuildingHarvester,
    BuildingGunner,
    BuildingSentinel,
)
# Core/Foundry/Breach/Launcher also count but are checked via en_core_tiles/en_turrets


# ── Attack state ───────────────────────────────────────────


class Attack:
    def __init__(self) -> None:
        self.flow_source_ti: int | None = None
        self.source_type: str | None = None  # "harvester_output"|"enemy_output"|"new_harvest"
        self.harvest_ore_ti: int | None = None
        self._walk_turret_ti: int | None = None  # tile we're walking to for turret
        self._walk_turret_turns: int = 0
        self.target_dir: int | None = None  # persists for explore fallback
        self._blocked_ore: dict[int, int] = {}

    def run(
        self, builder: Builder, ct: Controller, nav: NavBfs, s: State
    ) -> tuple[str, bool]:
        w = s.w
        rnd = s.age + s.birthday

        # Expire blocked ore (50-turn TTL)
        self._blocked_ore = {k: v for k, v in self._blocked_ore.items() if rnd - v < 50}

        # Step 1: If harvesting ore, continue that
        if self.source_type == "new_harvest" and self.harvest_ore_ti is not None:
            return self._execute_harvest(builder, ct, nav, s)

        # Step 2: Validate existing flow source
        if self.flow_source_ti is not None and not self._validate_source(s):
            self.flow_source_ti = None
            self.source_type = None

        # Step 3: Find flow source if none
        if self.flow_source_ti is None:
            self._find_flow_source(s, ct.get_position())
            if self.flow_source_ti is None:
                return "atk:no_source", False

        if DEBUG:
            from vis import Tiles, emit
            emit(atk_source=Tiles(data=[(self.flow_source_ti % w, self.flow_source_ti // w)]))

        # Step 4: Compute A* from flow source toward enemy buildings
        goals = _enemy_building_goals(s)
        if not goals:
            return "atk:no_targets", False

        # If source IS already a goal tile, try turret directly — no chain needed
        if self.flow_source_ti in goals:
            feeder = self._find_feeder(s, self.flow_source_ti)
            turret = try_place_turret_at(s, ct, nav, self.flow_source_ti, feeder, ct.get_position())
            if turret is not None:
                self.flow_source_ti = None
                self.source_type = None
                return turret
            # No turret works here — continue extending
            # Remove this tile from goals so A* routes further
            goals = goals - {self.flow_source_ti}
            if not goals:
                self.flow_source_ti = None
                self.source_type = None
                return "atk:no_targets", False

        if ct.get_cpu_time_elapsed() > 1300:
            return "atk:cpu", False

        chain = AttackAstar(s, self.flow_source_ti, goals).compute(
            within_budget=lambda: ct.get_cpu_time_elapsed() < 1500
        )
        if chain is None or len(chain) < 2:
            self.flow_source_ti = None
            self.source_type = None
            return "atk:no_chain", False

        # Log chain path + goal
        path_str = "->".join(f"({c % w},{c // w})" for c in chain[:6])
        if len(chain) > 6:
            path_str += f"...({len(chain)} tiles)"
        goal_ti = chain[-1]
        goal_bld = s.building[goal_ti]
        goal_name = type(goal_bld).__name__[8:] if goal_bld else "?"
        _log(f"  chain: {path_str} goal=({goal_ti % w},{goal_ti // w})={goal_name}", ct.get_id())

        # Vis overlay
        if DEBUG:
            _emit_attack_vis(s, chain, self.flow_source_ti, goals)

        # Step 5: Walk chain, find first gap, handle it
        return self._extend_chain(builder, ct, nav, s, chain)

    # ── Flow source finding ────────────────────────────────

    def _find_flow_source(self, s: State, pos: Position) -> None:
        """Find the best flow source and set self.flow_source_ti/source_type."""
        w = s.w
        reach = s.reachable

        # Score = distance from output tile to nearest enemy building
        en_buildings = s.en_core_tiles | s.en_turrets | s.en_harvesters | s.en_transport
        if not en_buildings:
            # No known enemy — can't score, fallback will explore
            return

        # Score by distance to enemy core + distance to builder
        # So each builder picks a source it can reach AND is toward the fight
        if s.en_core_pos is not None:
            ecx, ecy = s.en_core_pos.x, s.en_core_pos.y
        else:
            ecx, ecy = w - 1 - s.core_pos.x, s.h - 1 - s.core_pos.y

        def _dist_to_enemy_core(ti: int) -> int:
            tx, ty = ti % w, ti // w
            to_enemy = abs(tx - ecx) + abs(ty - ecy)
            to_builder = abs(tx - pos.x) + abs(ty - pos.y)
            return to_enemy + to_builder

        # (tier, distance, output_ti, source_type, ore_ti_or_None)
        # Tier 0: existing transport with flow (ours non-econ + enemy)
        # Tier 1: existing harvester outputs (reliable)
        # Tier 2: new harvest (needs to build harvester first)
        candidates: list[tuple[int, int, int, str, int | None]] = []

        # --- Tier 0a: Our non-econ transport with flow (extend existing attack chains) ---
        for ti in s.tiles_with_flow:
            if ti not in s.my_transport:
                continue
            if ti in s.connected_transport:
                continue  # econ, not attack
            out_ti = _get_transport_output_ti(s, ti)
            if out_ti is None:
                continue
            # Output tile must be free (not our transport already)
            out_bld = s.building[out_ti]
            if out_bld is not None and out_bld.team == s.my_team and isinstance(out_bld, _TRANSPORT_OR_TURRETS):
                continue
            if reach is not None and not reach.is_reachable_idx(out_ti):
                continue
            d = _dist_to_enemy_core(out_ti)
            candidates.append((0, d, out_ti, "harvester_output", None))

        # --- Tier 0b: Enemy transport with flow ---
        for eti in s.en_transport:
            if eti not in s.tiles_with_flow:
                continue
            if eti in s.danger_zones:
                continue
            out_ti = _get_transport_output_ti(s, eti)
            if out_ti is None:
                continue
            if out_ti in s.danger_zones:
                continue
            if reach is not None and not reach.is_reachable_idx(out_ti):
                continue
            d = _dist_to_enemy_core(out_ti)
            candidates.append((0, d, out_ti, "enemy_output", None))

        # --- Tier 1: Existing harvester outputs (ours and enemy) ---
        for hi in s.my_harvesters:
            self._add_harvester_outputs(s, hi, w, reach, _dist_to_enemy_core, candidates, tier=1)
        for hi in s.en_harvesters:
            if hi in s.danger_zones:
                continue
            self._add_harvester_outputs(s, hi, w, reach, _dist_to_enemy_core, candidates, tier=1)

        # --- Tier 2: New harvest (ore) ---
        unit_tiles = {p.y * w + p.x for p in s.unit_tiles}
        for oi in s.ore_ti:
            if oi in s.my_harvesters or oi in s.en_harvesters:
                continue
            if oi in unit_tiles or oi in self._blocked_ore:
                continue
            bld = s.building[oi]
            if bld is not None and not isinstance(bld, _FREE_TYPES):
                continue  # includes our barriers — don't undo defensive barriering
            if reach is not None and not reach.is_reachable_idx(oi):
                continue
            best_adj = self._best_free_adjacent(s, oi, w)
            if best_adj is None:
                continue
            d = _dist_to_enemy_core(best_adj)
            candidates.append((2, d, best_adj, "new_harvest", oi))

        if not candidates:
            return

        candidates.sort()
        _tier, _dist, out_ti, stype, ore_ti = candidates[0]
        self.flow_source_ti = out_ti
        self.source_type = stype
        self.harvest_ore_ti = ore_ti
        _log(
            f"  source: ({out_ti % w},{out_ti // w}) type={stype}",
            0,
        )

    def _add_harvester_outputs(
        self,
        s: State,
        hi: int,
        w: int,
        reach: object,
        dist_fn: object,
        candidates: list[tuple[int, int, int, str, int | None]],
        *,
        tier: int = 1,
    ) -> None:
        """Add valid output tiles of a harvester to candidates."""
        hx, hy = hi % w, hi // w

        # Count existing attack taps (our non-econ conveyors/turrets adjacent)
        taps = 0
        for dx, dy in DIR4_DELTA:
            ax, ay = hx + dx, hy + dy
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            if ai in s.connected_transport:
                continue
            abld = s.building[ai]
            if abld is not None and abld.team == s.my_team:
                if isinstance(abld, (_TRANSPORT_OR_TURRETS)):
                    taps += 1
        if taps >= 2:
            return  # already tapped enough

        for dx, dy in DIR4_DELTA:
            ax, ay = hx + dx, hy + dy
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            if s.env[ai] == Environment.WALL:
                continue
            if ai in s.danger_zones:
                continue
            if reach is not None and not reach.is_reachable_idx(ai):
                continue
            # Check tile is "free"
            abld = s.building[ai]
            if abld is not None:
                if isinstance(abld, BuildingMarker):
                    pass  # free
                elif isinstance(abld, BuildingRoad):
                    pass  # free (ours or enemy)
                elif abld.team != s.my_team and isinstance(abld, TRANSPORT):
                    pass  # enemy transport — we can parasitize/build over
                elif abld.team == s.my_team and isinstance(abld, TRANSPORT):
                    continue  # already our transport
                elif isinstance(abld, TURRETS):
                    continue  # turret already here
                else:
                    continue  # harvester, barrier, core, etc.
            d = dist_fn(ai)
            candidates.append((tier, d, ai, "harvester_output", None))

    def _best_free_adjacent(self, s: State, ti: int, w: int) -> int | None:
        """Find best free cardinal neighbor of a tile (for new harvest chain start)."""
        tx, ty = ti % w, ti // w
        for dx, dy in DIR4_DELTA:
            ax, ay = tx + dx, ty + dy
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            env = s.env[ai]
            if env == Environment.WALL:
                continue
            bld = s.building[ai]
            if bld is not None and not isinstance(bld, _FREE_TYPES):
                continue
            return ai
        return None

    # ── Source validation ──────────────────────────────────

    def _validate_source(self, s: State) -> bool:
        ti = self.flow_source_ti
        if ti is None:
            return False
        # Don't reject danger zones here — turrets can be placed there.
        # The gap handler decides whether to build conveyors vs turrets.

        w = s.w

        if self.source_type == "harvester_output":
            # Source is valid if fed by: adjacent harvester OR our transport pointing at it
            tx, ty = ti % w, ti // w
            for dx, dy in DIR4_DELTA:
                ax, ay = tx + dx, ty + dy
                if not s.in_bounds(ax, ay):
                    continue
                ai = ay * w + ax
                # Adjacent harvester feeds this tile
                if ai in s.my_harvesters or ai in s.en_harvesters:
                    return True
                # Our transport pointing at this tile (chain behind us)
                if _tile_has_correct_transport(s, ai, ti, w):
                    return True
            return False

        if self.source_type == "enemy_output":
            # An enemy transport must still feed this tile
            for eti in s.en_transport:
                if eti not in s.tiles_with_flow:
                    continue
                out = _get_transport_output_ti(s, eti)
                if out == ti:
                    return True
            return False

        return True  # new_harvest validated separately

    # ── Harvest ore ────────────────────────────────────────

    def _execute_harvest(
        self, builder: Builder, ct: Controller, nav: NavBfs, s: State
    ) -> tuple[str, bool]:
        w = s.w
        oi = self.harvest_ore_ti
        if oi is None:
            self.flow_source_ti = None
            self.source_type = None
            return "atk:harvest_err", False

        # Already placed?
        if oi in s.my_harvesters:
            self.source_type = "harvester_output"
            self.harvest_ore_ti = None
            # Find output tile closest to enemy
            return "atk:harvest_done", False

        ox, oy = oi % w, oi // w
        ore_pos = Position(ox, oy)
        pos = ct.get_position()

        # Check ore still viable
        ore_bld = s.building[oi]
        if ore_bld is not None and ore_bld.team != s.my_team and not isinstance(ore_bld, BuildingMarker):
            self._blocked_ore[oi] = s.age + s.birthday
            self.flow_source_ti = None
            self.source_type = None
            self.harvest_ore_ti = None
            return "atk:ore_enemy", False

        # Bot on ore — wait
        if ore_pos in s.unit_tiles:
            return "atk:ore_wait", False

        # Adjacent? Place harvester
        if pos.distance_squared(ore_pos) <= 2 and pos != ore_pos:
            h_cost, _ = ct.get_harvester_cost()
            ti_res, _ = ct.get_global_resources()
            if ti_res < h_cost:
                return "atk:wait_ti", False
            from builder_helpers import _destroy_friendly
            _destroy_friendly(ct, ore_pos, allow_barrier=True)
            if ct.can_build_harvester(ore_pos):
                ct.build_harvester(ore_pos)
                builder._my_harvesters.add(oi)
                self.source_type = "harvester_output"
                self.harvest_ore_ti = None
                _log(f"  atk harvest({ox},{oy})", ct.get_id())
                return f"atk:harvest({ox},{oy})", True
            self._blocked_ore[oi] = s.age + s.birthday
            self.flow_source_ti = None
            self.source_type = None
            self.harvest_ore_ti = None
            return "atk:harvest_fail", False

        # Walk toward ore (to adjacent tile, not on it)
        # Find walkable neighbor of ore
        best_adj: Position | None = None
        best_d = 1_000_000
        for dx, dy in DIR4_DELTA:
            ax, ay = ox + dx, oy + dy
            if s.in_bounds(ax, ay) and s.env[ay * w + ax] != Environment.WALL:
                d = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
                if d < best_d:
                    best_d = d
                    best_adj = Position(ax, ay)
        if best_adj is not None:
            nav.set_goal(best_adj)
            moved = nav.step(ct)
            return f"atk:walk_ore({ox},{oy})", moved
        return "atk:ore_stuck", False

    # ── Chain extension ────────────────────────────────────

    def _extend_chain(
        self, builder: Builder, ct: Controller, nav: NavBfs, s: State, chain: list[int]
    ) -> tuple[str, bool]:
        w = s.w
        pos = ct.get_position()

        # Start at k=0 — the flow source output tile also needs a conveyor/turret.
        # Ti from the harvester arrives at chain[0] but won't move without transport.
        for k in range(len(chain)):
            ci = chain[k]
            ni = chain[k + 1] if k + 1 < len(chain) else None

            # Compute prev_ti for feed direction
            if k > 0:
                prev_ti = chain[k - 1]
            else:
                # k=0: feed comes from adjacent harvester
                prev_ti = self._find_feeder(s, ci)

            # Already has correct transport → skip
            if ni is not None and _tile_has_correct_transport(s, ci, ni, w):
                continue

            # ── Handle gap at ci ──
            if ci in s.connected_transport:
                self.flow_source_ti = None
                self.source_type = None
                return "atk:econ_hit", False

            ci_bld = s.building[ci]
            cx, cy = ci % w, ci // w
            build_pos = Position(cx, cy)

            # Our transport or turret — NEVER destroy, find new route
            if (
                ci_bld is not None
                and ci_bld.team == s.my_team
                and isinstance(ci_bld, _TRANSPORT_OR_TURRETS)
            ):
                self.flow_source_ti = None
                self.source_type = None
                return f"atk:redir({cx},{cy})", False

            # Don't build conveyor feeding into our own transport/turrets
            if ni is not None:
                ni_bld = s.building[ni]
                if (
                    ni_bld is not None
                    and ni_bld.team == s.my_team
                    and isinstance(ni_bld, _TRANSPORT_OR_TURRETS)
                ):
                    self.flow_source_ti = None
                    self.source_type = None
                    return f"atk:redir_ni({cx},{cy})", False

            # Enemy building at gap
            if ci_bld is not None and ci_bld.team != s.my_team:
                if isinstance(ci_bld, BuildingMarker):
                    pass  # build over
                elif isinstance(ci_bld, BuildingRoad):
                    # Roads: 5 HP, fire inline (3 shots). Check for 2+ → turret.
                    road_count = 1
                    for j in range(k + 1, len(chain)):
                        jbld = s.building[chain[j]]
                        if jbld is not None and jbld.team != s.my_team and isinstance(jbld, BuildingRoad):
                            road_count += 1
                        else:
                            break
                    if road_count >= 2 and prev_ti is not None:
                        turret = try_place_turret_at(s, ct, nav, prev_ti, chain[k - 2] if k >= 2 else self._find_feeder(s, prev_ti), pos)
                        if turret is not None:
                            self.flow_source_ti = None
                            self.source_type = None
                            return turret
                    return self._fire_at(ct, nav, s, ci)
                else:
                    # Non-road enemy building (conveyor, barrier, turret, etc.)
                    # Try placing turret at prev tile to clear. If can't, abandon.
                    if prev_ti is not None:
                        turret = try_place_turret_at(s, ct, nav, prev_ti, chain[k - 2] if k >= 2 else self._find_feeder(s, prev_ti), pos)
                        if turret is not None:
                            self.flow_source_ti = None
                            self.source_type = None
                            return turret
                    self.flow_source_ti = None
                    self.source_type = None
                    return f"atk:blocked({cx},{cy})", False

            # ── Gunner check (high priority — place immediately) ──
            ci_name = type(ci_bld).__name__[8:] if ci_bld else "empty"
            ni_name = type(s.building[ni]).__name__[8:] if ni and s.building[ni] else "empty"
            _log(
                f"  gap k={k} ({cx},{cy})={ci_name} -> {f'({ni % w},{ni // w})={ni_name}' if ni else 'END'}",
                ct.get_id(),
            )
            gunner = try_place_turret_at(s, ct, nav, ci, prev_ti, pos, gunner_only=True)
            if gunner is not None:
                self.flow_source_ti = None
                self.source_type = None
                return gunner

            # ── Build conveyor (prefer extending over sentinel) ──
            if ni is not None and ci not in s.danger_zones:
                # Walk to gap if not adjacent
                if pos.distance_squared(build_pos) > 2:
                    nav.set_goal(build_pos)
                    return f"atk:walk_gap({cx},{cy})", nav.step(ct)

                nx, ny = ni % w, ni // w
                result = _build_at_gap(
                    builder, ct, cx, cy, nx, ny, build_pos,
                    "atk:chain", path=chain, gap_idx=k, destroy_barriers=True,
                )
                if "recompute" in result[0] or "blocked" in result[0]:
                    self.flow_source_ti = None
                    self.source_type = None
                elif "conv" in result[0] or "bridge" in result[0]:
                    if ni not in s.danger_zones:
                        self.flow_source_ti = ni
                return result

            # ── Sentinel fallback (can't extend further) ──
            sentinel = try_place_turret_at(s, ct, nav, ci, prev_ti, pos, sentinel_only=True)
            if sentinel is not None:
                self.flow_source_ti = None
                self.source_type = None
                return sentinel

            # Can't extend or place sentinel
            if ci in s.danger_zones:
                self.flow_source_ti = None
                self.source_type = None
                return f"atk:danger({cx},{cy})", False
            return "atk:chain_end", False

        # All tiles built, no gap — chain complete but no turret placed
        return "atk:chain_done", False

    def _find_feeder(self, s: State, ti: int) -> int | None:
        """Find what feeds this tile: adjacent harvester OR our transport pointing at it."""
        w = s.w
        tx, ty = ti % w, ti // w
        for dx, dy in DIR4_DELTA:
            ax, ay = tx + dx, ty + dy
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            # Harvester adjacent = feed
            if ai in s.my_harvesters or ai in s.en_harvesters:
                return ai
            # Our transport pointing at this tile = feed
            if _tile_has_correct_transport(s, ai, ti, w):
                return ai
        return None

    # ── Turret placement ───────────────────────────────────

    def _try_place_turret(
        self, ct: Controller, nav: NavBfs, s: State, ci: int, prev_ti: int | None,
        *, gunner_only: bool = False, sentinel_only: bool = False,
    ) -> tuple[str, bool] | None:
        """Check if turret at ci can hit enemy HVT. Returns action or None."""
        w = s.w
        cx, cy = ci % w, ci // w

        # Turrets are OK in danger zones (they're static), so check_danger=False
        if not _can_place_gunner(s, ci, check_danger=False):
            return None

        # Don't place turrets on OUR transport (econ or attack chain)
        if ci in s.my_transport:
            return None

        # Must be walkable by the builder (BFS can route there)
        if not nav.is_passable(Position(cx, cy)):
            return None

        # Feed direction: turret can't face TOWARD the feed source
        # (it receives on non-facing sides). The feed side is the direction
        # FROM current tile TO prev tile (where the chain comes from).
        # Exception: bridge hops bypass directional restrictions.
        if prev_ti is None:
            # No feed source found — can't guarantee turret gets fed
            return None
        px, py = prev_ti % w, prev_ti // w
        # Direction from current to prev = the feed side (can't face this way)
        dx_raw, dy_raw = px - cx, py - cy
        # Bridge hop (not cardinally adjacent) → turret can face any direction
        is_bridge_hop = abs(dx_raw) > 1 or abs(dy_raw) > 1 or (dx_raw != 0 and dy_raw != 0)
        if is_bridge_hop:
            feed_dx, feed_dy = 99, 99  # won't match any DIR8_DELTA
        else:
            feed_dx = 1 if dx_raw > 0 else (-1 if dx_raw < 0 else 0)
            feed_dy = 1 if dy_raw > 0 else (-1 if dy_raw < 0 else 0)

        # Enemy HVTs (things worth shooting — NOT harvesters, gunner won't fire at them)
        en_hvt = s.en_core_tiles | s.en_turrets

        if sentinel_only:
            return self._try_sentinel(ct, nav, s, ci, w, cx, cy, feed_dx, feed_dy, en_hvt)

        # --- Gunner: check 8 directions for LoS ---
        gunner_blocked_reasons: list[str] = []
        for fdx, fdy in DIR8_DELTA:
            if (fdx, fdy) == (feed_dx, feed_dy):
                continue
            hit = _has_los(s, cx, cy, fdx, fdy)
            if hit is None:
                continue
            hit_bld = s.building[hit]
            hx, hy = hit % w, hit // w
            if hit_bld is None or hit_bld.team == s.my_team:
                bname = type(hit_bld).__name__[8:] if hit_bld else "?"
                gunner_blocked_reasons.append(f"({hx},{hy})={bname}:own")
                continue
            if isinstance(hit_bld, (BuildingRoad, BuildingMarker, BuildingHarvester)):
                bname = type(hit_bld).__name__[8:]
                gunner_blocked_reasons.append(f"({hx},{hy})={bname}:skip")
                continue
            # Valid HVT target
            facing = DELTA_TO_DIR.get((fdx, fdy))
            if facing is None:
                continue
            _log(
                f"  turret({cx},{cy}): gunner face={facing.name} -> ({hx},{hy})",
                ct.get_id(),
            )
            return self._do_place_turret(ct, nav, s, ci, facing, sentinel=False)

        if gunner_blocked_reasons:
            _log(f"  turret({cx},{cy}): no_gunner [{','.join(gunner_blocked_reasons[:3])}] feed=({feed_dx},{feed_dy})", ct.get_id())
        else:
            _log(f"  turret({cx},{cy}): no_los feed=({feed_dx},{feed_dy})", ct.get_id())

        if gunner_only:
            return None

        return self._try_sentinel(ct, nav, s, ci, w, cx, cy, feed_dx, feed_dy, en_hvt)

    def _try_sentinel(
        self, ct: Controller, nav: NavBfs, s: State, ci: int,
        w: int, cx: int, cy: int, feed_dx: int, feed_dy: int, en_hvt: set[int],
    ) -> tuple[str, bool] | None:
        """Sentinel placement check — extracted for sentinel_only path."""
        rnd = s.age + s.birthday
        for eti in en_hvt:
            ebld = s.building[eti]
            if ebld is None or ebld.team == s.my_team:
                continue
            if isinstance(ebld, (BuildingRoad, BuildingMarker, BuildingHarvester)):
                continue
            # Only target buildings seen recently (avoid stale ghosts)
            if rnd - s.last_seen[eti] > 20:
                continue
            ex, ey = eti % w, eti // w
            if (ex - cx) ** 2 + (ey - cy) ** 2 > 32:
                continue
            # Find a facing that covers this target and isn't the feed direction
            for fdx, fdy in DIR8_DELTA:
                if (fdx, fdy) == (feed_dx, feed_dy):
                    continue
                if _in_sentinel_arc(cx, cy, fdx, fdy, ex, ey):
                    facing = DELTA_TO_DIR.get((fdx, fdy))
                    if facing is None:
                        continue
                    ename = type(ebld).__name__[8:]
                    _log(
                        f"  turret({cx},{cy}): sentinel face={facing.name} -> ({ex},{ey})={ename} r2={(ex-cx)**2+(ey-cy)**2}",
                        ct.get_id(),
                    )
                    return self._do_place_turret(ct, nav, s, ci, facing, sentinel=True)

        return None

    def _do_place_turret(
        self, ct: Controller, nav: NavBfs, s: State,
        ti: int, facing: Direction, *, sentinel: bool,
    ) -> tuple[str, bool] | None:
        """Step off, walk to, clear, and place turret."""
        w = s.w
        tx, ty = ti % w, ti // w
        tpos = Position(tx, ty)
        pos = ct.get_position()

        # Don't walk far for turret placement — max Manhattan 5
        if abs(pos.x - tx) + abs(pos.y - ty) > 5:
            return None

        if pos == tpos:
            for d in Direction:
                if d != Direction.CENTRE and ct.can_move(d):
                    ct.move(d)
                    return f"atk:stepoff({tx},{ty})", True
            return f"atk:trapped({tx},{ty})", False

        if pos.distance_squared(tpos) > 2:
            # Log passability around target to diagnose routing issues
            blocked: list[str] = []
            for ddx in range(-1, 2):
                for ddy in range(-1, 2):
                    nx, ny = tx + ddx, ty + ddy
                    if s.in_bounds(nx, ny):
                        np = Position(nx, ny)
                        if not nav.is_passable(np):
                            nbld = s.building[ny * w + nx]
                            bname = type(nbld).__name__[8:] if nbld else "wall?"
                            blocked.append(f"({nx},{ny})={bname}")
            if blocked:
                _log(f"  walk_turret({tx},{ty}): blocked_near=[{','.join(blocked)}]", ct.get_id())
            nav.set_goal(tpos)
            moved = nav.step(ct)
            if not moved:
                _log(f"  walk_turret({tx},{ty}): cant_move from ({pos.x},{pos.y})", ct.get_id())
            return f"atk:walk_turret({tx},{ty})", moved

        cost, _ = ct.get_sentinel_cost() if sentinel else ct.get_gunner_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < cost:
            return "atk:wait_ti", False

        # Re-verify target still exists before spending Ti
        w = s.w
        fdx, fdy = facing.delta()
        has_target = False
        if sentinel:
            en_hvt = s.en_core_tiles | s.en_turrets
            for eti in en_hvt:
                ebld = s.building[eti]
                if ebld is None or ebld.team == s.my_team:
                    continue
                if isinstance(ebld, (BuildingRoad, BuildingMarker, BuildingHarvester)):
                    continue
                etx, ety = eti % w, eti // w
                if _in_sentinel_arc(tx, ty, fdx, fdy, etx, ety):
                    has_target = True
                    break
        else:
            hit = _has_los(s, tx, ty, fdx, fdy)
            if hit is not None:
                hbld = s.building[hit]
                if hbld is not None and hbld.team != s.my_team and not isinstance(hbld, (BuildingRoad, BuildingMarker, BuildingHarvester)):
                    has_target = True

        if not has_target:
            _log(f"  place({tx},{ty}): target_gone face={facing.name}", ct.get_id())
            return None

        # Bot on tile? Can't place turret (only conveyors/roads allowed with bots). Wait.
        if tpos in s.unit_tiles:
            return f"atk:wait_bot_turret({tx},{ty})", False

        _clear_tile(ct, s, ti, tpos)
        kind = "sentinel" if sentinel else "gunner"
        if sentinel:
            if ct.can_build_sentinel(tpos, facing):
                ct.build_sentinel(tpos, facing)
                s.building[ti] = BuildingSentinel(s.my_team, facing)
                _log(f"  PLACED {kind}({tx},{ty}) face={facing.name}", ct.get_id())
                return f"atk:{kind}({tx},{ty})", True
        else:
            if ct.can_build_gunner(tpos, facing):
                ct.build_gunner(tpos, facing)
                s.building[ti] = BuildingGunner(s.my_team, facing)
                _log(f"  PLACED {kind}({tx},{ty}) face={facing.name}", ct.get_id())
                return f"atk:{kind}({tx},{ty})", True

        _log(f"  place({tx},{ty}): can_build_{kind} FAILED pos=({pos.x},{pos.y}) cd={ct.get_action_cooldown()}", ct.get_id())
        return None  # build failed, fall through to conveyor

    # ── Fire at enemy road ─────────────────────────────────

    def _fire_at(
        self, ct: Controller, nav: NavBfs, s: State, ti: int
    ) -> tuple[str, bool]:
        w = s.w
        tx, ty = ti % w, ti // w
        pos = ct.get_position()
        target = Position(tx, ty)
        # Don't walk into danger zones to fire
        if ti in s.danger_zones and pos != target:
            self.flow_source_ti = None
            self.source_type = None
            return f"atk:fire_danger({tx},{ty})", False
        if pos == target:
            if ct.can_fire(target):
                ct.fire(target)
                return f"atk:fire({tx},{ty})", True
            return "atk:fire_cd", False
        nav.set_goal(target)
        return f"atk:walk_fire({tx},{ty})", nav.step(ct)


# ── Pure helpers ───────────────────────────────────────────


def _in_sentinel_arc(
    sx: int, sy: int, fdx: int, fdy: int, tx: int, ty: int
) -> bool:
    """Check if target is in sentinel arc: within Chebyshev 1 of facing ray, r²≤32."""
    if (tx - sx) ** 2 + (ty - sy) ** 2 > 32:
        return False
    rx, ry = sx + fdx, sy + fdy
    while (rx - sx) ** 2 + (ry - sy) ** 2 <= 32:
        if max(abs(tx - rx), abs(ty - ry)) <= 1:
            return True
        rx += fdx
        ry += fdy
    return False


def _get_transport_output_ti(s: State, ti: int) -> int | None:
    """Get the first buildable output tile of a transport building.

    Returns the tile where Ti actually arrives, not the transport tile itself.
    """
    w = s.w
    bld = s.building[ti]
    if bld is None:
        return None
    tx, ty = ti % w, ti // w

    out_tiles: list[tuple[int, int]] = []
    match bld:
        case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
            ddx, ddy = d.delta()
            out_tiles.append((tx + ddx, ty + ddy))
        case BuildingSplitter(direction=d):
            ddx, ddy = d.delta()
            for odx, ody in [(ddx, ddy), (-ddy, ddx), (ddy, -ddx)]:
                out_tiles.append((tx + odx, ty + ody))
        case BuildingBridge(target=tgt):
            out_tiles.append((tgt.x, tgt.y))
        case _:
            return None

    for ox, oy in out_tiles:
        if not s.in_bounds(ox, oy):
            continue
        oi = oy * w + ox
        if s.env[oi] == Environment.WALL:
            continue
        out_bld = s.building[oi]
        if out_bld is None or isinstance(out_bld, _FREE_TYPES):
            return oi
        # Enemy transport is also OK (parasitize)
        if out_bld.team != s.my_team and isinstance(out_bld, TRANSPORT):
            return oi
    return None


def _enemy_building_goals(s: State) -> set[int]:
    """Tiles adjacent (Chebyshev 1) to enemy buildings — where turrets can be placed.

    We don't route TO enemy buildings (can't build there), we route to tiles
    NEXT TO them where a gunner/sentinel can attack.
    """
    w = s.w
    # High-value targets only — core, turrets, harvesters. NOT transport.
    # Conveyors/bridges are collateral damage, not routing targets.
    enemy = s.en_core_tiles | s.en_turrets | s.en_harvesters
    goals: set[int] = set()
    reach = s.reachable
    for eti in enemy:
        ex, ey = eti % w, eti // w
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = ex + dx, ey + dy
                if not s.in_bounds(nx, ny):
                    continue
                ni = ny * w + nx
                if ni in enemy:
                    continue  # don't include other enemy buildings
                if s.env[ni] == Environment.WALL:
                    continue
                if reach is not None and not reach.is_reachable_idx(ni):
                    continue
                goals.add(ni)
    return goals


def _emit_attack_vis(
    s: State, chain: list[int], source_ti: int, goals: set[int]
) -> None:
    """Emit vis overlays for attack debugging."""
    from vis import Palette, Tiles, emit

    w = s.w
    chain_tiles = [(c % w, c // w) for c in chain]
    source_tile = [(source_ti % w, source_ti // w)]
    goal_tiles = [(g % w, g // w) for g in goals]
    flow_tiles = [(t % w, t // w) for t in s.tiles_with_flow]
    econ_tiles = [(t % w, t // w) for t in s.connected_transport]

    emit(
        atk_chain=Tiles(data=chain_tiles),
        atk_source=Tiles(data=source_tile),
        atk_goals=Tiles(data=goal_tiles),
        atk_flow=Tiles(data=flow_tiles),
        atk_econ=Tiles(data=econ_tiles),
    )


# ── Top-level dispatcher ──────────────────────────────────


def _run_attack(builder: Builder, ct: Controller) -> tuple[str, bool]:
    a = builder._attack
    s = builder.state
    pos = ct.get_position()
    w = s.w

    result = a.run(builder, ct, builder.nav, s)

    # Fallback on failure/no-plan states
    _FALLBACK = ("atk:no_source", "atk:no_targets", "atk:no_chain",
                 "atk:chain_end", "atk:chain_done", "atk:cpu",
                 "atk:econ_hit", "atk:ore_wait", "atk:wait_ti")
    if result[0] in _FALLBACK or "blocked" in result[0] or "redir" in result[0] or "danger" in result[0]:
        # Persist target direction for explore
        if a.target_dir is None:
            if s.en_core_pos is not None:
                a.target_dir = s.en_core_pos.y * w + s.en_core_pos.x
            else:
                a.target_dir = (s.h - 1 - s.core_pos.y) * w + (w - 1 - s.core_pos.x)

        tgt_pos = Position(a.target_dir % w, a.target_dir // w) if a.target_dir else None

        # Fire at enemy building we're standing on (not roads/markers)
        if ct.get_action_cooldown() == 0:
            bid = ct.get_tile_building_id(pos)
            if bid is not None and ct.get_team(bid) != s.my_team:
                etype = ct.get_entity_type(bid)
                if etype not in (EntityType.ROAD, EntityType.MARKER) and ct.can_fire(pos):
                    ct.fire(pos)
                    return "atk:fire_infra", True

        # Harvest NEARBY ore only (Manhattan ≤ 5) — creates flow sources near enemy
        # Don't walk far for ore (that caused oscillation)
        if tgt_pos is not None:
            w2 = s.w
            for oi in builder.ti_ore.positions:
                if oi in s.my_harvesters or oi in s.en_harvesters:
                    continue
                ox, oy = oi % w2, oi // w2
                if abs(pos.x - ox) + abs(pos.y - oy) > 5:
                    continue  # too far — don't walk across map
                harvest = _task_harvest(builder, ct, target_pos=tgt_pos)
                if harvest is not None:
                    if "place" in harvest[0]:
                        a.flow_source_ti = None
                        a.source_type = None
                    return harvest
                break  # tried harvest, didn't work — move on

        # Explore toward enemy
        return _task_explore_enemy(builder, ct)

    return result
