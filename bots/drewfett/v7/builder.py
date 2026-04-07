"""Builder bot: BFS nav + capacity-aware harvesting + role-based task dispatch.

Single NavBfs instance per builder. A* recomputed fresh each turn
(no cached path -- eliminates stale-path bugs).

Roles: ECON (0), ATTACK (1), DEFENSE (2).
"""

from __future__ import annotations

import random

from bbot_tracker import BbotTracker
from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from chain_astar import ChainAstar
from core import OFFSET_TO_INDEX, role_for_spawn
from explore import ExploreGrid
from nav import NavBfs
from state import State
from state_update import _outputs_toward
from state_update import update as state_update
from symmetry import SymmetryDetector
from tracker import Tracker
from unit import Unit
from util import DELTA_TO_DIR, DIR4_DELTA, Symmetry

# Max harvesters per branch (4 = true throughput limit, 1 stack/turn)
_BRANCH_CAPACITY = 4


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()

        core_pos = _find_core(ct)

        # Role assignment via spawn offset
        spawn_pos = ct.get_position()
        dx = spawn_pos.x - core_pos.x
        dy = spawn_pos.y - core_pos.y
        idx = OFFSET_TO_INDEX.get((dx, dy), 0)
        self._role: int = role_for_spawn(idx)

        # Single NavBfs -- grid + BFS + movement in one
        self.nav = NavBfs(w, h)
        self.nav._init_pnb_chunk(lambda: True)

        # Symmetry
        self.sym = SymmetryDetector(w, h, core_pos)
        self._mirrored = False
        self._tile_cache: bytearray = bytearray(b"\xff" * (w * h))

        # Trackers
        self.ti_ore = Tracker(w, h, environment=Environment.ORE_TITANIUM)
        self.friend_tracker = BbotTracker(w)
        self.explore = ExploreGrid(w, h)

        # Game state
        self.state = State(ct, core_pos)
        self.state.nav = self.nav

        self._stuck_turns = 0
        self._harvest_target: int | None = None
        self._connect_harvester: int | None = None
        self._connect_path: list[int] | None = None
        self._my_harvesters: set[int] = set()  # harvesters THIS builder placed

        # Attack state
        self._attack_path: list[int] | None = None
        self._attack_target_ti: int | None = None

        # Defense state
        self._reactive_gunner_state: str | None = None
        self._reactive_gunner_target: int | None = None
        self._reactive_gunner_pos: int | None = None

    def run(self, ct: Controller) -> None:
        if ct.get_cpu_time_elapsed() > 1400:
            self.state.age += 1
            self.state.pos = ct.get_position()
            return

        s = self.state
        pos = ct.get_position()

        # -- Symmetry detection --
        resolved_sym = self.sym.resolved
        if resolved_sym is None:
            for tile in ct.get_nearby_tiles():
                self.sym.update(tile.y * s.w + tile.x, ct.get_tile_env(tile))
            if self.sym.resolved is not None:
                s.symmetry = self.sym.resolved
                resolved_sym = s.symmetry

        if not self._mirrored and resolved_sym is not None:
            self.nav.mirror_known(resolved_sym, self.sym.known_env)
            self.ti_ore.mirror_known(resolved_sym)
            self._mirrored = True

        # -- Vision scan + state update --
        _update_nearby_tiles(
            self.nav, self.ti_ore, s, ct, self._tile_cache, resolved_sym
        )
        self.friend_tracker.update(ct)
        self.explore.update(ct, pos, s.core_pos)
        state_update(s, ct)

        # Enemy core estimate from symmetry
        if s.en_core_pos is None and self.sym.enemy_core is not None:
            s.en_core_pos = self.sym.enemy_core

        # -- Self-heal --
        if ct.get_hp() < ct.get_max_hp() and ct.get_action_cooldown() == 0:
            ti, _ = ct.get_global_resources()
            if ti >= 1 and ct.can_heal(pos):
                ct.heal(pos)

        # -- Task dispatch --
        try:
            task_name, moved = self._run_tasks(ct)
        except Exception:
            _task_name, moved = "crash", False

        new_pos = ct.get_position()

        # Livelock breaker
        if new_pos == pos and not moved:
            self._stuck_turns += 1
            if self._stuck_turns >= 3:
                dirs = [
                    d for d in Direction if d != Direction.CENTRE and ct.can_move(d)
                ]
                if dirs:
                    ct.move(random.choice(dirs))
                    self._stuck_turns = 0
        else:
            self._stuck_turns = 0

    def _run_tasks(self, ct: Controller) -> tuple[str, bool]:
        """Execute highest-priority task via role dispatch."""

        # Emergency layer (all roles)
        result = self._emergency_tasks(ct)
        if result is not None:
            return result

        # Role-specific tasks
        if self._role == 0:
            return self._run_econ(ct)
        if self._role == 1:
            return self._run_attack(ct)
        if self._role == 2:
            return self._run_defense(ct)
        return self._run_econ(ct)  # fallback

    def _emergency_tasks(self, ct: Controller) -> tuple[str, bool] | None:
        """Emergency tasks for all roles."""
        s = self.state
        pos = ct.get_position()

        # Self-heal (critical)
        if ct.get_hp() < ct.get_max_hp() // 2 and ct.get_action_cooldown() == 0:
            ti, _ = ct.get_global_resources()
            if ti >= 1 and ct.can_heal(pos):
                ct.heal(pos)
                return "emergency:self_heal", True

        # Heal core
        if s.my_core_hp < 500 and ct.is_in_vision(s.core_pos):
            self.nav.set_goal(s.core_pos)
            if self.nav.step(ct):
                return "heal_core:walk", True
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    tp = Position(s.core_pos.x + dx, s.core_pos.y + dy)
                    if ct.can_heal(tp):
                        ct.heal(tp)
                        return "heal_core:heal", True
            return "heal_core:wait", False

        # Cut feed (stop our buildings feeding enemy turrets)
        result = self._task_cut_feed(ct)
        if result is not None:
            return result

        return None

    # -- Role: ECON --

    def _run_econ(self, ct: Controller) -> tuple[str, bool]:
        s = self.state

        # Connect unconnected harvesters
        unconnected = s.my_harvesters - s.connected_harvesters
        if unconnected:
            result = self._task_connect(ct, unconnected)
            if result is not None:
                return result

        # Place new harvesters
        result = self._task_harvest(ct)
        if result is not None:
            return result

        # Switch to attack if enough flow
        if self._should_switch_to_attack():
            self._role = 1
            return self._run_attack(ct)

        # Explore map
        return self._task_explore(ct)

    def _should_switch_to_attack(self) -> bool:
        s = self.state
        own_connected = len(s.connected_harvesters & self._my_harvesters)
        total_connected = len(s.connected_harvesters)
        return own_connected >= 2 or total_connected >= 4

    # -- Role: ATTACK --

    def _run_attack(self, ct: Controller) -> tuple[str, bool]:
        s = self.state

        # 1. Place gunner if chain tip has flow + LoS to enemy
        result = self._task_place_gunner(ct)
        if result is not None:
            return result

        # 2. Extend attack chain toward enemy
        result = self._task_extend_attack(ct)
        if result is not None:
            return result

        # 3. If no enemy known, harvest (build econ in enemy half)
        if s.en_core_pos is None:
            result = self._task_harvest(ct)
            if result is not None:
                return result

        # 4. Explore enemy half
        return self._task_explore_enemy(ct)

    # -- Role: DEFENSE --

    def _run_defense(self, ct: Controller) -> tuple[str, bool]:

        # 1. Reactive gunner against enemy turret in our base
        result = self._task_reactive_gunner(ct)
        if result is not None:
            return result

        # 2. Repair broken chains
        result = self._task_repair_chain(ct)
        if result is not None:
            return result

        # 3. Heal damaged infra
        result = self._task_heal_infra(ct)
        if result is not None:
            return result

        # 4. Barrier harvesters
        result = self._task_barrier_harvesters(ct)
        if result is not None:
            return result

        # 5. Patrol
        return self._task_patrol(ct)

    # -- Task: Connect (cached A* with validation) --

    def _task_connect(
        self, ct: Controller, unconnected: set[int]
    ) -> tuple[str, bool] | None:
        """Connect nearest unconnected harvester. Caches path for stability."""
        s = self.state
        w = s.w
        pos = ct.get_position()

        # Only connect harvesters THIS builder placed
        my_unconnected = unconnected & self._my_harvesters

        # Stick with current target if still unconnected
        if (
            self._connect_harvester is not None
            and self._connect_harvester in my_unconnected
        ):
            best_hi = self._connect_harvester
        else:
            best_hi = None
            best_dist = 1_000_000
            for hi in my_unconnected:
                hx, hy = hi % w, hi // w
                d = (pos.x - hx) ** 2 + (pos.y - hy) ** 2
                if d < best_dist:
                    best_dist = d
                    best_hi = hi

        if best_hi is None:
            self._connect_harvester = None
            self._connect_path = None
            return None

        self._connect_harvester = best_hi
        hx, hy = best_hi % w, best_hi // w

        # Validate cached path: endpoint still a valid goal?
        path = self._connect_path
        if path is not None:
            end_ti = path[-1]
            end_bn = s.bottleneck.get(end_ti, 0)
            still_valid = (
                end_bn < _BRANCH_CAPACITY
                and (end_ti in s.connected_transport or end_ti in s.core_tiles)
                and path[0] == best_hi  # same harvester
            )
            if not still_valid:
                path = None
                self._connect_path = None

        # Recompute A* if no cached path
        if path is None:
            goals = self._capacity_filtered_goals()
            len(goals)
            if not goals:
                # Everything is full or stale — can't connect safely
                return f"connect:no_valid_goals h=({hx},{hy})", False

            search = ChainAstar(
                s,
                hx,
                hy,
                goals,
                bottleneck=s.bottleneck,
                capacity=_BRANCH_CAPACITY,
            )
            path = search.compute(
                within_budget=lambda: ct.get_cpu_time_elapsed() < 1500
            )

            if path is None:
                self._connect_path = None
                return f"connect:no_path h=({hx},{hy})", False

            self._connect_path = path

        end_ti = path[-1]
        end_bn = s.bottleneck.get(end_ti, 0)

        # Find first gap in the path (from harvester toward core).
        # Sequential building ensures we complete chains without bouncing.
        gap_idx: int | None = None
        for k in range(len(path) - 1):
            ci = path[k]
            ni = path[k + 1]
            if _tile_has_correct_transport(s, ci, ni, w):
                continue
            gap_idx = k
            break

        if gap_idx is None:
            # Path is complete -- harvester is now connected
            return f"connect:complete h=({hx},{hy})", False

        ci = path[gap_idx]
        ni = path[gap_idx + 1]
        cx, cy = ci % w, ci // w
        nx, ny = ni % w, ni // w
        build_pos = Position(cx, cy)
        tag = f"connect:h=({hx},{hy}) gap=({cx},{cy})"

        # Check if adjacent to gap -- if so, build + walk toward next gap
        if pos.distance_squared(build_pos) <= 2:
            return self._build_at_gap(ct, cx, cy, nx, ny, build_pos, tag, path, gap_idx)

        # Walk toward gap (may build roads to get there)
        self.nav.set_goal(build_pos)
        moved = self.nav.step(ct)
        return f"{tag} walk->({cx},{cy})", moved

    def _walk_toward_next_gap(
        self, ct: Controller, path: list[int], from_k: int
    ) -> None:
        """After building, use remaining movement to walk toward next gap."""
        s = self.state
        w = s.w
        for k in range(from_k, len(path) - 1):
            ci = path[k]
            ni = path[k + 1]
            if _tile_has_correct_transport(s, ci, ni, w):
                continue
            # Found next gap — try to walk toward it
            gx, gy = ci % w, ci // w
            target = Position(gx, gy)
            direction = ct.get_position().direction_to(target)
            if direction != Direction.CENTRE and ct.can_move(direction):
                ct.move(direction)
            return

    def _build_at_gap(
        self,
        ct: Controller,
        cx: int,
        cy: int,
        nx: int,
        ny: int,
        build_pos: Position,
        tag: str,
        path: list[int] | None = None,
        gap_idx: int = 0,
    ) -> tuple[str, bool]:
        """Build conveyor or bridge at the gap tile."""
        s = self.state
        w = s.w
        ci = cy * w + cx
        ni = ny * w + nx
        dx, dy = nx - cx, ny - cy
        conv_dir = DELTA_TO_DIR.get((dx, dy))

        if conv_dir is None:
            # Bridge hop — verify target is not a wall before spending 20 Ti
            target_env = s.env[ni]
            if target_env == Environment.WALL:
                self._connect_path = None
                return f"{tag} bridge_target_wall({nx},{ny}):recompute", False
            target_pos = Position(nx, ny)
            b_cost, _ = ct.get_bridge_cost()
            ti_res, _ = ct.get_global_resources()
            if ti_res < b_cost:
                return f"{tag} wait_ti(bridge)", False
            _destroy_friendly(ct, build_pos)
            if ct.can_build_bridge(build_pos, target_pos):
                ct.build_bridge(build_pos, target_pos)
                from building import BuildingBridge as BldBridge

                s.building[ci] = BldBridge(s.my_team, target_pos)
                s.my_transport.add(ci)
                self._walk_toward_next_gap(ct, path, gap_idx + 1)
                return f"{tag} bridge({cx},{cy})->({nx},{ny})", True
            self._connect_path = None
            return f"{tag} bridge_cant_build:recompute", False

        # Cardinal conveyor — verify tiles
        next_env = s.env[ni]
        if next_env == Environment.WALL:
            self._connect_path = None
            return f"{tag} conv_target_wall({nx},{ny}):recompute", False
        cur_env = s.env[ci]
        if cur_env is not None and cur_env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            self._connect_path = None
            return f"{tag} conv_tile_blocked({cx},{cy}):recompute", False
        c_cost, _ = ct.get_conveyor_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < c_cost:
            return f"{tag} wait_ti(conv)", False
        _destroy_friendly(ct, build_pos)
        if ct.can_build_conveyor(build_pos, conv_dir):
            ct.build_conveyor(build_pos, conv_dir)
            from building import BuildingConveyor as BldConveyor

            s.building[ci] = BldConveyor(s.my_team, conv_dir)
            s.my_transport.add(ci)
            self._walk_toward_next_gap(ct, path, gap_idx + 1)
            return f"{tag} conv({cx},{cy})->{conv_dir.name}", True
        self._connect_path = None
        return f"{tag} conv_cant_build:recompute", False

    def _capacity_filtered_goals(self) -> set[int]:
        """Goals = core tiles + connected transport with spare capacity."""
        s = self.state
        goals: set[int] = set(s.core_tiles)
        for ti in s.connected_transport:
            if s.bottleneck.get(ti, 0) < _BRANCH_CAPACITY:
                goals.add(ti)
        return goals

    # -- Task: Explore Tree --

    # -- Task: Harvest --

    def _task_harvest(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        w = s.w
        pos = ct.get_position()

        unharvested = self.ti_ore.positions - s.my_harvesters - s.en_harvesters
        if not unharvested:
            self._harvest_target = None
            return None

        # Phase 1: adjacent to ore -- place harvester
        for dx, dy in DIR4_DELTA:
            ni = (pos.y + dy) * w + (pos.x + dx)
            if ni not in unharvested:
                continue
            ore_pos = Position(pos.x + dx, pos.y + dy)
            if ore_pos in s.unit_tiles:
                continue
            # Check that there's no existing building we can't remove
            existing = s.building[ni]
            if existing is not None and not isinstance(
                existing, (BuildingRoad, BuildingMarker)
            ):
                continue
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti < h_cost:
                return "harvest:wait_ti", False
            _destroy_friendly(ct, ore_pos)
            if ct.can_build_harvester(ore_pos):
                ct.build_harvester(ore_pos)
                self._harvest_target = None
                self._my_harvesters.add(ni)
                self._needs_barrier = ni  # barrier this harvester next turn
                return f"harvest:place({ore_pos.x},{ore_pos.y})", True
            return f"harvest:cant_place({ore_pos.x},{ore_pos.y})", False

        # Phase 2: walk toward committed ore target (sticky -- no oscillation)
        # Re-pick only if current target is gone (harvested, out of unharvested set)
        ht = self._harvest_target
        if ht is not None and ht not in unharvested:
            ht = None
            self._harvest_target = None

        if ht is None:
            # Pick best ore: conn_dist weighted heavily (cheap to connect > close to walk)
            network = s.connected_transport | s.core_tiles
            core_x, core_y = s.core_pos.x, s.core_pos.y

            def _score(oi: int) -> int:
                ox, oy = oi % w, oi // w
                walk_dist = max(abs(pos.x - ox), abs(pos.y - oy))
                if network:
                    conn_dist = min(
                        abs(ox - ti % w) + abs(oy - ti // w) for ti in network
                    )
                else:
                    conn_dist = abs(ox - core_x) + abs(oy - core_y)
                return walk_dist + conn_dist * 2

            scored = sorted(
                [(sc, oi) for oi in unharvested if (sc := _score(oi)) < 1_000_000]
            )
            if scored:
                ht = scored[0][1]
                self._harvest_target = ht

        if ht is None:
            return None

        ore_pos = Position(ht % w, ht // w)
        # Walk to cardinal neighbor of ore closest to core (must be passable)
        best_adj: Position | None = None
        best_d = 1_000_000
        core_x, core_y = s.core_pos.x, s.core_pos.y
        for dx, dy in DIR4_DELTA:
            ax, ay = ore_pos.x + dx, ore_pos.y + dy
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            env = s.env[ai]
            if env is not None and env == Environment.WALL:
                continue
            d = abs(core_x - ax) + abs(core_y - ay)
            if d < best_d:
                best_d = d
                best_adj = Position(ax, ay)

        if best_adj is not None:
            self.nav.set_goal(best_adj)
            moved = self.nav.step(ct)
            return f"harvest:walk->ore({ore_pos.x},{ore_pos.y})", moved

        return None

    # -- Task: Explore --

    def _task_explore(self, ct: Controller) -> tuple[str, bool]:
        target = self.explore.target
        if target is None:
            return "explore:no_target", False

        # If ore found, walk toward it instead
        if self.ti_ore.positions:
            unharvested = (
                self.ti_ore.positions
                - self.state.my_harvesters
                - self.state.en_harvesters
            )
            if unharvested:
                w = self.state.w
                ore_positions = [Position(i % w, i // w) for i in unharvested]
                self.nav.set_goals(ore_positions)
                moved = self.nav.step(ct)
                return f"explore:walk->ore({len(ore_positions)})", moved

        self.nav.set_goal(target)
        moved = self.nav.step(ct)
        return f"explore:walk->({target.x},{target.y})", moved

    # -- Task: Explore Enemy (attack builders) --

    def _task_explore_enemy(self, ct: Controller) -> tuple[str, bool]:
        s = self.state
        if s.en_core_pos is not None:
            self.nav.set_goal(s.en_core_pos)
        else:
            # Guess enemy is on opposite side of map
            ex = s.w - 1 - s.core_pos.x
            ey = s.h - 1 - s.core_pos.y
            self.nav.set_goal(Position(ex, ey))
        moved = self.nav.step(ct)
        return "explore_enemy", moved

    # -- Task: Extend Attack Chain --

    def _task_extend_attack(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        w = s.w

        # Need enemy buildings to target
        en_buildings = s.en_core_tiles | s.en_harvesters | s.en_transport | s.en_turrets
        if not en_buildings:
            return None

        # Need connected transport to start from
        network = s.connected_transport | s.core_tiles
        if not network:
            return None

        # Compute target tiles: tiles within gunner r^2=13 of enemy buildings
        targets: set[int] = set()
        for ei in en_buildings:
            ex, ey = ei % w, ei // w
            for dx in range(-4, 5):
                for dy in range(-4, 5):
                    if dx * dx + dy * dy > 13:
                        continue
                    nx, ny = ex + dx, ey + dy
                    if not s.in_bounds(nx, ny):
                        continue
                    ni = ny * w + nx
                    env = s.env[ni]
                    if env is not None and env in (
                        Environment.WALL,
                        Environment.ORE_TITANIUM,
                        Environment.ORE_AXIONITE,
                    ):
                        continue
                    targets.add(ni)

        # Already connected to target zone?
        if targets & network:
            return None

        # Validate cached path
        path = self._attack_path
        if path is not None:
            # After reverse: path[0]=network, path[-1]=target
            still_valid = (
                (path[0] in network or path[0] in s.core_tiles)
                and path[-1] in targets
            )
            if not still_valid:
                path = None
                self._attack_path = None

        # Find nearest target tile to start A* from
        if path is None:
            pos = ct.get_position()
            best_start: int | None = None
            best_dist = 1_000_000
            for ti in targets:
                tx, ty = ti % w, ti // w
                d = abs(pos.x - tx) + abs(pos.y - ty)
                if d < best_dist:
                    best_dist = d
                    best_start = ti

            if best_start is None:
                return None

            sx, sy = best_start % w, best_start // w
            goals = self._capacity_filtered_goals()
            if not goals:
                return None

            search = ChainAstar(
                s,
                sx,
                sy,
                goals,
                bottleneck=s.bottleneck,
                capacity=_BRANCH_CAPACITY,
            )
            path = search.compute(
                within_budget=lambda: ct.get_cpu_time_elapsed() < 1500,
            )
            if path is None:
                return None
            # Reverse: path goes target→network, but we need conveyors
            # pointing FROM network TOWARD target (Ti flows outward)
            path.reverse()
            self._attack_path = path

        # Find first gap (same logic as connect)
        pos = ct.get_position()
        gap_idx: int | None = None
        for k in range(len(path) - 1):
            ci = path[k]
            ni = path[k + 1]
            if _tile_has_correct_transport(s, ci, ni, w):
                continue
            gap_idx = k
            break

        if gap_idx is None:
            self._attack_path = None
            return None  # path complete

        ci = path[gap_idx]
        ni = path[gap_idx + 1]
        cx, cy = ci % w, ci // w
        nx, ny = ni % w, ni // w
        build_pos = Position(cx, cy)
        tag = f"attack_chain:gap=({cx},{cy})"

        if pos.distance_squared(build_pos) <= 2:
            return self._build_at_gap(ct, cx, cy, nx, ny, build_pos, tag, path, gap_idx)

        self.nav.set_goal(build_pos)
        moved = self.nav.step(ct)
        return f"{tag} walk", moved

    # -- Task: Place Gunner --

    def _task_place_gunner(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        w = s.w
        pos = ct.get_position()

        en_buildings = s.en_core_tiles | s.en_harvesters | s.en_transport | s.en_turrets
        if not en_buildings:
            return None

        flow_tiles = s.tiles_with_flow
        if not flow_tiles:
            return None

        # Check each flow tile in connected transport
        flow_on_network = flow_tiles & s.connected_transport
        if not flow_on_network:
            return None

        g_cost, _ = ct.get_gunner_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < g_cost:
            return None

        for fti in flow_on_network:
            fx, fy = fti % w, fti // w
            # Check adjacent tiles for gunner placement
            for dx, dy in DIR4_DELTA:
                gx, gy = fx + dx, fy + dy
                if not s.in_bounds(gx, gy):
                    continue
                gi = gy * w + gx
                gpos = Position(gx, gy)
                # Must be empty (or road/marker) and not on transport
                env = s.env[gi]
                if env is not None and env in (
                    Environment.WALL,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    continue
                bld = s.building[gi]
                if bld is not None and not isinstance(
                    bld, (BuildingRoad, BuildingMarker)
                ):
                    continue
                if gi in s.danger_zones:
                    continue

                # Check LoS from this tile toward each enemy building
                for ei in en_buildings:
                    ex, ey = ei % w, ei // w
                    facing_dx = 0 if ex == gx else (1 if ex > gx else -1)
                    facing_dy = 0 if ey == gy else (1 if ey > gy else -1)
                    if facing_dx == 0 and facing_dy == 0:
                        continue
                    facing_dir = DELTA_TO_DIR.get((facing_dx, facing_dy))
                    if facing_dir is None:
                        continue

                    hit = _has_los(s, gx, gy, facing_dx, facing_dy)
                    if hit is None:
                        continue

                    # Check feed direction: chain comes from fti, gunner faces toward enemy
                    # Feed must not come from facing direction
                    chain_dx, chain_dy = fx - gx, fy - gy
                    if (chain_dx, chain_dy) == (facing_dx, facing_dy):
                        continue  # can't feed from facing side

                    if pos.distance_squared(gpos) > 2:
                        self.nav.set_goal(gpos)
                        moved = self.nav.step(ct)
                        return f"place_gunner:walk({gx},{gy})", moved

                    _destroy_friendly(ct, gpos)
                    if ct.can_build_gunner(gpos, facing_dir):
                        ct.build_gunner(gpos, facing_dir)
                        return f"place_gunner:built({gx},{gy})", True

        return None

    # -- Task: Cut Feed --

    def _task_cut_feed(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        w = s.w
        pos = ct.get_position()

        for ti in s.en_turrets:
            tx, ty = ti % w, ti // w
            # Check each cardinal neighbor for our building feeding the turret
            for dx, dy in DIR4_DELTA:
                nx, ny = tx + dx, ty + dy
                if not s.in_bounds(nx, ny):
                    continue
                ni = ny * w + nx
                bld = s.building[ni]
                if bld is None or bld.team != s.my_team:
                    continue

                # Check if our building outputs toward the enemy turret
                if _outputs_toward(bld, ni, ti, w):
                    feed_pos = Position(nx, ny)
                    if pos.distance_squared(feed_pos) <= 2 and ct.can_destroy(feed_pos):
                        ct.destroy(feed_pos)
                        if ct.can_build_barrier(feed_pos):
                            ct.build_barrier(feed_pos)
                        return f"cut_feed:destroy({nx},{ny})", True
                    self.nav.set_goal(feed_pos)
                    moved = self.nav.step(ct)
                    return f"cut_feed:walk({nx},{ny})", moved

        # Also check bridges targeting enemy turrets
        for ti in s.en_turrets:
            for bi in s.bridges_by_target.get(ti, []):
                bld = s.building[bi]
                if bld is not None and bld.team == s.my_team:
                    bx, by = bi % w, bi // w
                    bridge_pos = Position(bx, by)
                    if pos.distance_squared(bridge_pos) <= 2 and ct.can_destroy(
                        bridge_pos
                    ):
                        ct.destroy(bridge_pos)
                        return f"cut_feed:destroy_bridge({bx},{by})", True
                    self.nav.set_goal(bridge_pos)
                    moved = self.nav.step(ct)
                    return f"cut_feed:walk_bridge({bx},{by})", moved

        return None

    # -- Task: Reactive Gunner (defense) --

    def _task_reactive_gunner(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        w = s.w
        pos = ct.get_position()
        core_x, core_y = s.core_pos.x, s.core_pos.y

        # Find enemy turrets near our core
        threat_turrets: list[int] = []
        for ti in s.en_turrets:
            tx, ty = ti % w, ti // w
            dist_sq = (tx - core_x) ** 2 + (ty - core_y) ** 2
            if dist_sq <= 100:  # ~10 tile radius
                threat_turrets.append(ti)

        if not threat_turrets:
            self._reactive_gunner_state = None
            return None

        # Find nearest own transport tile with flow near the threat
        flow_tiles = s.tiles_with_flow & s.connected_transport
        if not flow_tiles:
            return None

        best_threat = threat_turrets[0]
        ttx, tty = best_threat % w, best_threat // w

        # Find flow tile nearest to threat
        best_flow: int | None = None
        best_fdist = 1_000_000
        for fti in flow_tiles:
            fx, fy = fti % w, fti // w
            d = abs(fx - ttx) + abs(fy - tty)
            if d < best_fdist:
                best_fdist = d
                best_flow = fti

        if best_flow is None:
            return None

        fx, fy = best_flow % w, best_flow // w

        # Check adjacent tiles for gunner placement with LoS
        g_cost, _ = ct.get_gunner_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < g_cost:
            return None

        for dx, dy in DIR4_DELTA:
            gx, gy = fx + dx, fy + dy
            if not s.in_bounds(gx, gy):
                continue
            gi = gy * w + gx
            gpos = Position(gx, gy)
            env = s.env[gi]
            if env is not None and env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                continue
            bld = s.building[gi]
            if bld is not None and not isinstance(bld, (BuildingRoad, BuildingMarker)):
                continue

            # Check LoS to threat turret
            facing_dx = 0 if ttx == gx else (1 if ttx > gx else -1)
            facing_dy = 0 if tty == gy else (1 if tty > gy else -1)
            if facing_dx == 0 and facing_dy == 0:
                continue
            facing_dir = DELTA_TO_DIR.get((facing_dx, facing_dy))
            if facing_dir is None:
                continue

            hit = _has_los(s, gx, gy, facing_dx, facing_dy)
            if hit is None:
                continue

            # Check feed direction
            chain_dx, chain_dy = fx - gx, fy - gy
            if (chain_dx, chain_dy) == (facing_dx, facing_dy):
                continue

            if pos.distance_squared(gpos) > 2:
                self.nav.set_goal(gpos)
                moved = self.nav.step(ct)
                return f"reactive_gunner:walk({gx},{gy})", moved

            _destroy_friendly(ct, gpos)
            if ct.can_build_gunner(gpos, facing_dir):
                ct.build_gunner(gpos, facing_dir)
                return f"reactive_gunner:built({gx},{gy})", True

        return None

    # -- Task: Repair Chain (defense) --

    def _task_repair_chain(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        disconnected = s.my_harvesters - s.connected_harvesters
        if not disconnected:
            return None
        # Use existing connect logic
        return self._task_connect(ct, disconnected)

    # -- Task: Heal Infra (defense) --

    def _task_heal_infra(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        pos = ct.get_position()

        if ct.get_action_cooldown() != 0:
            return None

        ti_res, _ = ct.get_global_resources()
        if ti_res < 1:
            return None

        # Find lowest HP% friendly building in vision
        best_pos: Position | None = None
        best_ratio = 1.0
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) != s.my_team:
                continue
            etype = ct.get_entity_type(bid)
            if etype in (EntityType.MARKER, EntityType.ROAD):
                continue
            hp = ct.get_hp(bid)
            max_hp = ct.get_max_hp(bid)
            if hp >= max_hp:
                continue
            ratio = hp / max_hp
            if ratio < best_ratio:
                best_ratio = ratio
                best_pos = ct.get_position(bid)

        if best_pos is None or best_ratio >= 0.8:
            return None

        if pos.distance_squared(best_pos) <= 2 and ct.can_heal(best_pos):
            ct.heal(best_pos)
            return f"heal_infra:heal({best_pos.x},{best_pos.y})", True
        self.nav.set_goal(best_pos)
        moved = self.nav.step(ct)
        return f"heal_infra:walk({best_pos.x},{best_pos.y})", moved

    # -- Task: Barrier Harvesters (defense) --

    def _task_barrier_harvesters(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        w = s.w
        pos = ct.get_position()

        b_cost, _ = ct.get_barrier_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < b_cost:
            return None

        for hi in s.connected_harvesters:
            hx, hy = hi % w, hi // w
            for dx, dy in DIR4_DELTA:
                nx, ny = hx + dx, hy + dy
                if not s.in_bounds(nx, ny):
                    continue
                ni = ny * w + nx
                env = s.env[ni]
                if env is not None and env in (
                    Environment.WALL,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    continue
                bld = s.building[ni]
                # Skip tiles that already have important buildings
                if bld is not None and not isinstance(
                    bld, (BuildingRoad, BuildingMarker)
                ):
                    continue
                barrier_pos = Position(nx, ny)
                if barrier_pos in s.unit_tiles:
                    continue
                if pos.distance_squared(barrier_pos) <= 2 and barrier_pos != pos:
                    _destroy_friendly(ct, barrier_pos)
                    if ct.can_build_barrier(barrier_pos):
                        ct.build_barrier(barrier_pos)
                        return f"barrier:place({nx},{ny})", True
                else:
                    # Walk to an adjacent tile of the barrier spot, not the spot itself
                    best_adj: Position | None = None
                    best_d = 1_000_000
                    for adx, ady in DIR4_DELTA:
                        ax, ay = nx + adx, ny + ady
                        if not s.in_bounds(ax, ay):
                            continue
                        adj = Position(ax, ay)
                        d = (pos.x - ax) ** 2 + (pos.y - ay) ** 2
                        if d < best_d:
                            best_d = d
                            best_adj = adj
                    if best_adj is not None:
                        self.nav.set_goal(best_adj)
                        moved = self.nav.step(ct)
                        return f"barrier:walk({nx},{ny})", moved

        return None

    # -- Task: Patrol (defense) --

    def _task_patrol(self, ct: Controller) -> tuple[str, bool]:
        s = self.state
        w = s.w
        pos = ct.get_position()
        rnd = s.age + s.birthday

        patrol_set = s.connected_transport | s.my_harvesters
        if not patrol_set:
            return self._task_explore(ct)

        best_ti: int | None = None
        best_score = -1_000_000
        for ti in patrol_set:
            tx, ty = ti % w, ti // w
            age = rnd - s.last_seen[ti]
            dist = abs(pos.x - tx) + abs(pos.y - ty)
            bonus = 10 if ti in s.my_harvesters else 0
            score = age + bonus - dist
            if score > best_score:
                best_score = score
                best_ti = ti

        if best_ti is not None:
            tx, ty = best_ti % w, best_ti // w
            self.nav.set_goal(Position(tx, ty))
            moved = self.nav.step(ct)
            return f"patrol:walk({tx},{ty})", moved

        return self._task_explore(ct)

    # -- Visualiser --


# -- Helpers --


def _find_core(ct: Controller) -> Position:
    my = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
            return ct.get_position(bid)
    return ct.get_position()


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    if ct.get_entity_type(bid) in (
        EntityType.ROAD,
        EntityType.MARKER,
    ) and ct.can_destroy(pos):
        ct.destroy(pos)


def _tile_has_correct_transport(s: State, ci: int, ni: int, w: int) -> bool:
    """Check if tile ci already has transport outputting toward ni."""
    # Skip core tiles and harvester tiles -- they're fine as-is
    if ci in s.core_tiles:
        return True
    bld = s.building[ci]
    if isinstance(bld, BuildingHarvester):
        return True

    if bld is None:
        return False

    if bld.team != s.my_team:
        return False

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


def _has_los(s: State, gx: int, gy: int, fdx: int, fdy: int) -> int | None:
    """Walk ray from gunner position, return first enemy building tile or None."""
    w, h = s.w, s.h
    my_team = s.my_team
    x, y = gx + fdx, gy + fdy
    while 0 <= x < w and 0 <= y < h:
        if (x - gx) ** 2 + (y - gy) ** 2 > 13:
            break
        ni = y * w + x
        env = s.env[ni]
        if env == Environment.WALL:
            return None  # blocked by wall
        bld = s.building[ni]
        if bld is not None and not isinstance(bld, BuildingMarker):
            if bld.team != my_team:
                return ni  # hit enemy building
            return None  # blocked by own building
        x += fdx
        y += fdy
    return None


def _update_nearby_tiles(
    nav: NavBfs,
    ti_ore: Tracker,
    state: State,
    ct: Controller,
    tile_cache: bytearray,
    sym: Symmetry | None,
) -> None:
    """Read nearby tiles and update nav grid + ore tracker."""
    w = state.w
    my_team = ct.get_team()

    env_int: dict[Environment, int] = {e: i for i, e in enumerate(Environment)}
    et_int: dict[EntityType, int] = {e: i + 1 for i, e in enumerate(EntityType)}

    for tile in ct.get_nearby_tiles():
        i = tile.y * w + tile.x
        env = ct.get_tile_env(tile)
        bid = ct.get_tile_building_id(tile)
        building_type = ct.get_entity_type(bid) if bid is not None else None
        is_allied = bid is not None and ct.get_team(bid) == my_team

        bt = et_int.get(building_type, 0) if building_type is not None else 0
        key = env_int.get(env, 0) | (bt << 2) | (int(is_allied) << 6)
        if tile_cache[i] == key:
            continue
        tile_cache[i] = key

        nav.update_tile(i, env, building_type, is_allied, sym)
        ti_ore.update_tile(i, env, sym)
