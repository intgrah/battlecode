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
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Environment, Position
from chain_astar import AttackAstar, ChainAstar
from core import OFFSET_TO_INDEX, role_for_spawn
from explore import ExploreGrid
from marker import MarkerIdleGunner
from marker import decode as _decode_marker
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

# Tile cache keys (avoid recreating dicts every turn)
_ENV_INT: dict[Environment, int] = {e: i for i, e in enumerate(Environment)}
_ET_INT: dict[EntityType, int] = {e: i + 1 for i, e in enumerate(EntityType)}


import sys as _sys


def _log(msg: str, _bot_id: int = 0) -> None:
    print(msg, file=_sys.stderr, flush=True)


def _can_place_gunner_at(s: State, gi: int) -> bool:
    """Check if tile is valid for gunner placement (before calling can_build_gunner)."""
    env = s.env[gi]
    if env is not None and env in (
        Environment.WALL,
        Environment.ORE_TITANIUM,
        Environment.ORE_AXIONITE,
    ):
        return False
    if gi in s.danger_zones:
        return False
    bld = s.building[gi]
    if bld is not None:
        if isinstance(bld, BuildingMarker):
            return True  # can build over any marker
        if bld.team == s.my_team:
            return True  # can destroy any own building
        return False  # enemy building
    return True


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

        # Attack — delegated to Attack class
        from attack import Attack

        self._attack = Attack()

        # Defense state (reactive gunner uses stateless scan each turn)

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

        # Sync _my_harvesters with state (remove destroyed ones)
        self._my_harvesters &= s.my_harvesters

        # Enemy core estimate from symmetry
        if s.en_core_pos is None and self.sym.enemy_core is not None:
            s.en_core_pos = self.sym.enemy_core

        # -- Self-heal --
        if ct.get_hp() < ct.get_max_hp() and ct.get_action_cooldown() == 0:
            ti, _ = ct.get_global_resources()
            if ti >= 1 and ct.can_heal(pos):
                ct.heal(pos)

        # -- Task dispatch --
        _ROLE_NAME = ("E", "A", "D")
        import traceback

        try:
            task_name, moved = self._run_tasks(ct)
        except Exception:
            task_name = f"crash:{traceback.format_exc().splitlines()[-1]}"
            moved = False

        new_pos = ct.get_position()
        r = _ROLE_NAME[self._role] if self._role < 3 else "?"
        m = "M" if pos != new_pos else "."
        extra = ""
        if self._role == 1:
            a = self._attack
            parts = []
            if a.target is not None:
                parts.append(f"tgt=({a.target % s.w},{a.target // s.w})")
            if a.frontier is not None:
                parts.append(f"fr=({a.frontier % s.w},{a.frontier // s.w})")
            if a.gunner is not None:
                parts.append(f"gun=({a.gunner % s.w},{a.gunner // s.w})")
            extra = f" [{' '.join(parts)}]"
        px, py = new_pos.x, new_pos.y
        _log(
            f"T{s.age + s.birthday} {r}{m}@({px},{py}) {task_name}{extra}",
            ct.get_id(),
        )

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

        # Explore map
        return self._task_explore(ct)

    # -- Role: ATTACK --

    def _run_attack(self, ct: Controller) -> tuple[str, bool]:
        a = self._attack
        s = self.state

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
        result = a.run(ct, self.nav, s)

        # If attack has nothing to do, explore toward enemy
        if result[0] == "atk:no_target" or result[0] == "atk:no_source":
            return self._task_explore_enemy(ct)

        return result

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
        destroy_barriers: bool = False,
    ) -> tuple[str, bool]:
        """Build conveyor or bridge at the gap tile."""
        s = self.state
        w = s.w
        ci = cy * w + cx
        ni = ny * w + nx

        # Debug: log what's on the tiles
        ci_bld = s.building[ci]
        ni_bld = s.building[ni]
        ci_name = type(ci_bld).__name__[8:] if ci_bld else "empty"
        ni_name = type(ni_bld).__name__[8:] if ni_bld else "empty"
        ci_team = (
            "own" if ci_bld and ci_bld.team == s.my_team else "en" if ci_bld else ""
        )
        ni_team = (
            "own" if ni_bld and ni_bld.team == s.my_team else "en" if ni_bld else ""
        )
        ci_conn = "conn" if ci in s.connected_transport else ""
        _log(
            f"  gap@({cx},{cy})={ci_team}{ci_name}{ci_conn} -> ({nx},{ny})={ni_team}{ni_name} mode={'atk' if destroy_barriers else 'eco'}",
            0,
        )

        # Pre-check (econ only): can we remove existing building on gap tile?
        if not destroy_barriers:
            gap_bld = s.building[ci]
            if gap_bld is not None and not (
                isinstance(gap_bld, BuildingMarker)
                or (
                    gap_bld.team == s.my_team
                    and isinstance(gap_bld, (BuildingRoad, BuildingBarrier))
                )
            ):
                self._connect_path = None
                return f"{tag} tile_blocked:recompute", False

        dx, dy = nx - cx, ny - cy
        conv_dir = DELTA_TO_DIR.get((dx, dy))

        if conv_dir is None:
            # Bridge hop — verify target tile is usable
            target_env = s.env[ni]
            if target_env is not None and target_env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                if not destroy_barriers:
                    self._connect_path = None
                return f"{tag} bridge_target_blocked({nx},{ny}):recompute", False
            # Check for enemy building or danger zone on target
            target_bld = s.building[ni]
            if (
                target_bld is not None
                and target_bld.team != s.my_team
                and not isinstance(target_bld, BuildingMarker)
            ):
                if not destroy_barriers:
                    self._connect_path = None
                return f"{tag} bridge_target_enemy({nx},{ny}):recompute", False
            if ni in s.danger_zones:
                if not destroy_barriers:
                    self._connect_path = None
                return f"{tag} bridge_target_danger({nx},{ny}):recompute", False
            target_pos = Position(nx, ny)
            b_cost, _ = ct.get_bridge_cost()
            ti_res, _ = ct.get_global_resources()
            if ti_res < b_cost:
                return f"{tag} wait_ti(bridge)", False
            if ci not in s.connected_transport:
                _destroy_friendly(ct, build_pos, allow_barrier=True)
            if ct.can_build_bridge(build_pos, target_pos):
                ct.build_bridge(build_pos, target_pos)
                from building import BuildingBridge as BldBridge

                s.building[ci] = BldBridge(s.my_team, target_pos)
                s.my_transport.add(ci)
                self._walk_toward_next_gap(ct, path, gap_idx + 1)
                return f"{tag} bridge({cx},{cy})->({nx},{ny})", True
            # Build failed — try to destroy any own building blocking us
            if destroy_barriers:
                bid = ct.get_tile_building_id(build_pos)
                if bid is not None and ct.get_team(bid) == ct.get_team():
                    if ct.can_destroy(build_pos):
                        ct.destroy(build_pos)
                        s.building[ci] = None
                        s.my_transport.discard(ci)
                        return f"{tag} cleared({cx},{cy})", False
            else:
                self._connect_path = None
            return f"{tag} bridge_cant_build:recompute", False

        # Cardinal conveyor — verify tiles
        next_env = s.env[ni]
        if next_env == Environment.WALL:
            if destroy_barriers:
                pass  # frontier model — caller handles replan
            else:
                self._connect_path = None
            return f"{tag} conv_target_wall({nx},{ny}):recompute", False
        cur_env = s.env[ci]
        if cur_env is not None and cur_env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            if destroy_barriers:
                pass  # frontier model — caller handles replan
            else:
                self._connect_path = None
            return f"{tag} conv_tile_blocked({cx},{cy}):recompute", False
        c_cost, _ = ct.get_conveyor_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < c_cost:
            return f"{tag} wait_ti(conv)", False
        _destroy_friendly(ct, build_pos, allow_barrier=True)
        if ct.can_build_conveyor(build_pos, conv_dir):
            ct.build_conveyor(build_pos, conv_dir)
            from building import BuildingConveyor as BldConveyor

            s.building[ci] = BldConveyor(s.my_team, conv_dir)
            s.my_transport.add(ci)
            self._walk_toward_next_gap(ct, path, gap_idx + 1)
            return f"{tag} conv({cx},{cy})->{conv_dir.name}", True
        # Build failed — try to destroy any own building blocking us
        if destroy_barriers:
            bid = ct.get_tile_building_id(build_pos)
            if bid is not None and ct.get_team(bid) == ct.get_team():
                if ct.can_destroy(build_pos):
                    ct.destroy(build_pos)
                    s.building[ci] = None
                    s.my_transport.discard(ci)
                    return f"{tag} cleared({cx},{cy})", False  # retry next turn
        if not destroy_barriers:
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
        # Remove temporarily blocked ore
        blocked = getattr(self, "_blocked_ore", {})
        now = s.age + s.birthday
        unharvested = {oi for oi in unharvested if blocked.get(oi, 0) <= now}
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
            if existing is not None:
                if isinstance(existing, (BuildingRoad, BuildingMarker)):
                    pass  # removable
                elif (
                    isinstance(existing, BuildingBarrier)
                    and existing.team == s.my_team
                    and not _has_nearby_threat(s, ni)
                ):
                    pass  # our barrier, no threat — safe to remove
                else:
                    continue
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti < h_cost:
                return "harvest:wait_ti", False
            _destroy_friendly(ct, ore_pos, allow_barrier=True)
            if ct.can_build_harvester(ore_pos):
                ct.build_harvester(ore_pos)
                self._harvest_target = None
                self._my_harvesters.add(ni)
                return f"harvest:place({ore_pos.x},{ore_pos.y})", True
            # Failed — block this ore temporarily so we pick a different one
            self._harvest_target = None
            self._blocked_ore = getattr(self, "_blocked_ore", {})
            self._blocked_ore[ni] = s.age + s.birthday + 50  # block for 50 turns
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

            # Skip ore with enemy buildings on it
            valid_ore = set()
            for oi in unharvested:
                bld = s.building[oi]
                if (
                    bld is not None
                    and bld.team != s.my_team
                    and not isinstance(bld, BuildingMarker)
                ):
                    continue
                valid_ore.add(oi)
            scored = sorted(
                [(sc, oi) for oi in valid_ore if (sc := _score(oi)) < 1_000_000]
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
            # Already adjacent but can't place? Skip this ore.
            if pos.distance_squared(ore_pos) <= 2:
                self._harvest_target = None
                return None
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
            target = self._find_passable_near(s.en_core_pos)
            self.nav.set_goal(target)
        else:
            ex = s.w - 1 - s.core_pos.x
            ey = s.h - 1 - s.core_pos.y
            self.nav.set_goal(Position(ex, ey))
        moved = self.nav.step(ct)
        return "explore_enemy", moved

    def _find_passable_near(self, target: Position) -> Position:
        """Find a passable tile near the target. Returns target if already passable."""
        if self.nav.is_passable(target):
            return target
        # Search expanding rings for a passable tile
        for r in range(1, 5):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if abs(dx) != r and abs(dy) != r:
                        continue  # only ring edge
                    nx, ny = target.x + dx, target.y + dy
                    if self.state.in_bounds(nx, ny):
                        p = Position(nx, ny)
                        if self.nav.is_passable(p):
                            return p
        return target  # fallback

    # -- Attack methods moved to attack.py --

    # Legacy helper kept for explore_enemy
    def _attack_invalidate_REMOVED(self, _ct: Controller) -> None:
        """Light invalidation — only clear state when something is truly gone."""
        s = self.state
        w = s.w

        # Target gone (wall appeared)
        if self._attack_target is not None:
            env = s.env[self._attack_target]
            if env is not None and env == Environment.WALL:
                self._attack_target = None
                self._chain_frontier = None
                self._chain_source = None

        # Source harvester destroyed
        if self._chain_source is not None:
            src = self._chain_source
            found = False
            for dx, dy in DIR4_DELTA:
                nx, ny = src % w + dx, src // w + dy
                if s.in_bounds(nx, ny) and isinstance(
                    s.building[ny * w + nx], BuildingHarvester
                ):
                    found = True
                    break
            if not found:
                self._chain_source = None
                # Keep frontier — chain might still be intact from another feed

        # Frontier tile destroyed
        if self._chain_frontier is not None:
            bld = s.building[self._chain_frontier]
            if self._chain_frontier != self._chain_source and (
                bld is None
                or (bld.team != s.my_team and not isinstance(bld, BuildingMarker))
            ):
                # Frontier gone — don't try to recover, just clear and replan
                self._chain_frontier = None

        # Gunner destroyed
        if self._attack_gunner is not None:
            bld = s.building[self._attack_gunner]
            if not isinstance(bld, BuildingGunner) or bld.team != s.my_team:
                self._attack_gunner = None

    def _attack_find_target(self, _ct: Controller) -> None:
        """Pick an enemy building to push toward."""
        s = self.state
        w = s.w
        en = s.en_core_tiles | s.en_harvesters | s.en_transport | s.en_turrets
        if s.en_core_pos is not None and not en:
            self._attack_target = s.en_core_pos.y * w + s.en_core_pos.x
            return
        if not en:
            return
        pos = s.pos
        best_ti: int | None = None
        best_score = 1_000_000
        for ei in en:
            ex, ey = ei % w, ei // w
            score = abs(pos.x - ex) + abs(pos.y - ey)
            if ei in s.en_core_tiles:
                score -= 100
            if score < best_score:
                best_score = score
                best_ti = ei
        if best_ti is not None and best_ti != self._attack_target:
            self._chain_frontier = None
            self._chain_source = None
        if best_ti is not None:
            self._attack_target = best_ti

    def _attack_init_chain(self, ct: Controller) -> tuple[str, bool]:
        """Find Ti source and set frontier = source tile."""
        s = self.state
        target = self._attack_target
        if target is None:
            return self._task_explore_enemy(ct)

        source = self._find_attack_source(ct, target)
        if source is None:
            return self._task_explore_enemy(ct)

        self._chain_source = source
        self._chain_frontier = source
        self._attack_stuck = 0
        return f"attack:init_chain src=({source % s.w},{source // s.w})", False

    def _find_attack_source(self, _ct: Controller, target: int) -> int | None:
        """Find best Ti source tile for the attack chain.

        Preference:
        a. Own connected harvester with a free cardinal side
        c. Enemy harvester with a free cardinal side (parasitize their output)
        b. Ti ore near the target (would need new harvester)
        """
        s = self.state
        w = s.w
        tx, ty = target % w, target // w

        # (a) Any own harvester with free cardinal side, closest to target
        # Prefer harvesters this builder placed (avoids competing with other attackers)
        best_src: int | None = None
        best_dist = 1_000_000
        candidates = list(self._my_harvesters & s.my_harvesters) + [
            hi for hi in s.my_harvesters if hi not in self._my_harvesters
        ]
        for hi in candidates:
            hx, hy = hi % w, hi // w
            for dx, dy in DIR4_DELTA:
                fx, fy = hx + dx, hy + dy
                if not s.in_bounds(fx, fy):
                    continue
                fi = fy * w + fx
                env = s.env[fi]
                if env is not None and env in (
                    Environment.WALL,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    continue
                bld = s.building[fi]
                # Free side: empty, road, or marker only (no existing conveyors)
                if bld is not None and not isinstance(
                    bld, (BuildingRoad, BuildingMarker)
                ):
                    continue
                dist = abs(fx - tx) + abs(fy - ty)
                if dist < best_dist:
                    best_dist = dist
                    best_src = fi

        # (c) Enemy harvester with a free cardinal side (parasitize their output)
        # A conveyor on the free side will capture the enemy harvester's Ti output.
        # Prefer enemy harvesters closer to the attack target than our own harvesters.
        best_en_src: int | None = None
        best_en_dist = 1_000_000
        for hi in s.en_harvesters:
            hx, hy = hi % w, hi // w
            for dx, dy in DIR4_DELTA:
                fx, fy = hx + dx, hy + dy
                if not s.in_bounds(fx, fy):
                    continue
                fi = fy * w + fx
                env = s.env[fi]
                if env is not None and env in (
                    Environment.WALL,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    continue
                bld = s.building[fi]
                # Free side: empty, road, or marker only
                if bld is not None and not isinstance(
                    bld, (BuildingRoad, BuildingMarker)
                ):
                    continue
                dist = abs(fx - tx) + abs(fy - ty)
                if dist < best_en_dist:
                    best_en_dist = dist
                    best_en_src = fi

        # (b) Ti ore near target — pick closest ore to target
        best_ore: int | None = None
        best_ore_dist = 1_000_000
        for oi in self.ti_ore.positions:
            if oi in s.my_harvesters or oi in s.en_harvesters:
                continue
            # Skip ore with enemy building on it (barrier etc)
            ore_bld = s.building[oi]
            if ore_bld is not None and ore_bld.team != s.my_team:
                continue
            ox, oy = oi % w, oi // w
            dist = abs(ox - tx) + abs(oy - ty)
            if dist < best_ore_dist:
                best_ore_dist = dist
                best_ore = oi

        best_ore_src: int | None = None
        if best_ore is not None:
            ox, oy = best_ore % w, best_ore // w
            for dx, dy in DIR4_DELTA:
                fx, fy = ox + dx, oy + dy
                if not s.in_bounds(fx, fy):
                    continue
                fi = fy * w + fx
                env = s.env[fi]
                if env is not None and env in (
                    Environment.WALL,
                    Environment.ORE_TITANIUM,
                    Environment.ORE_AXIONITE,
                ):
                    continue
                bld = s.building[fi]
                if bld is not None and not isinstance(
                    bld, (BuildingRoad, BuildingMarker)
                ):
                    continue
                best_ore_src = fi
                break

        # Pick best source: own harvester > enemy harvester > ore
        if best_src is not None:
            if best_en_src is not None and best_en_dist < best_dist:
                return best_en_src
            return best_src
        if best_en_src is not None:
            return best_en_src
        if best_ore_src is not None:
            return best_ore_src
        return None

    # -- Attack: Advance frontier toward target --

    def _attack_advance(self, ct: Controller) -> tuple[str, bool]:
        """Compute short A* from frontier toward target, build one tile."""
        s = self.state
        w = s.w
        pos = ct.get_position()
        frontier = self._chain_frontier
        target = self._attack_target

        if frontier is None or target is None:
            return self._task_explore_enemy(ct)

        fx, fy = frontier % w, frontier // w
        tx, ty = target % w, target // w
        dist_to_target = abs(fx - tx) + abs(fy - ty)

        # Close enough to target — try to place gunner
        if dist_to_target <= 4:
            result = self._attack_place_gunner(ct)
            if result is not None:
                return result

        # Compute short A* from frontier toward target
        goals: set[int] = set()
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                gx, gy = tx + dx, ty + dy
                if s.in_bounds(gx, gy):
                    goals.add(gy * w + gx)

        search = AttackAstar(s, frontier, goals)
        path = search.compute(within_budget=lambda: ct.get_cpu_time_elapsed() < 1500)
        if path is None or len(path) < 2:
            self._attack_stuck += 1
            if self._attack_stuck >= 10:
                # Truly stuck — abandon this attack entirely, find new target
                self._chain_frontier = None
                self._chain_source = None
                self._attack_target = None
                self._attack_stuck = 0
            return "attack:no_path", False

        self._attack_stuck = 0

        # Log the computed path
        path_str = "->".join(f"({ti % w},{ti // w})" for ti in path[:6])
        if len(path) > 6:
            path_str += f"...({len(path)})"
        _log(f"  astar: {path_str}", 0)

        # Find first gap in the short path
        for k in range(len(path) - 1):
            ci, ni = path[k], path[k + 1]
            if _tile_has_correct_transport(s, ci, ni, w):
                # Already built — advance frontier
                self._chain_frontier = ci
                continue

            cx, cy = ci % w, ci // w
            nx, ny = ni % w, ni // w

            # Enemy building on THIS tile?
            gap_bld = s.building[ci]
            if (
                gap_bld is not None
                and gap_bld.team != s.my_team
                and not isinstance(gap_bld, BuildingMarker)
            ):
                return self._attack_place_gunner_at(ct, ci, ni)

            # Enemy building on NEXT tile? Drop gunner here instead of conveyor
            next_bld = s.building[ni]
            if (
                next_bld is not None
                and next_bld.team != s.my_team
                and not isinstance(next_bld, BuildingMarker)
            ):
                return self._attack_place_gunner_at(ct, ci, ni)

            # Terrain block?
            gap_env = s.env[ci]
            if gap_env is not None and gap_env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                # Can't build here — stuck, will replan next turn
                return f"attack:terrain({cx},{cy})", False

            # Build conveyor or bridge
            build_pos = Position(cx, cy)
            if pos.distance_squared(build_pos) <= 2:
                tag = f"attack:build({cx},{cy})"
                result = self._build_at_gap(
                    ct,
                    cx,
                    cy,
                    nx,
                    ny,
                    build_pos,
                    tag,
                    path,
                    k,
                    destroy_barriers=True,
                )
                if "cant_build" in result[0] or "recompute" in result[0]:
                    self._attack_stuck += 1
                    if self._attack_stuck >= 5:
                        # Stuck too long — retreat to source, A* will reroute
                        self._chain_frontier = self._chain_source
                        self._attack_stuck = 0
                    return result
                # Success — advance frontier
                self._chain_frontier = ci
                return result

            # Walk toward the gap
            self.nav.set_goal(build_pos)
            moved = self.nav.step(ct)
            return f"attack:walk({cx},{cy})", moved

        # All gaps filled — chain reached the goal ring, place gunner
        self._chain_frontier = path[-1]
        return self._attack_place_gunner(ct)

    def _attack_place_gunner_at(
        self, ct: Controller, gi: int, enemy_ti: int
    ) -> tuple[str, bool]:
        """Place gunner at gi facing enemy_ti. Used when enemy is ahead."""
        s = self.state
        w = s.w
        pos = ct.get_position()
        gx, gy = gi % w, gi // w
        ex, ey = enemy_ti % w, enemy_ti // w

        if not _can_place_gunner_at(s, gi):
            return f"attack:cant_gunner({gx},{gy})", False

        fdx = 0 if ex == gx else (1 if ex > gx else -1)
        fdy = 0 if ey == gy else (1 if ey > gy else -1)
        if fdx == 0 and fdy == 0:
            return f"attack:no_facing({gx},{gy})", False
        facing_dir = DELTA_TO_DIR.get((fdx, fdy))
        if facing_dir is None:
            return f"attack:no_facing({gx},{gy})", False

        g_cost, _ = ct.get_gunner_cost()
        ti_res, _ = ct.get_global_resources()
        if ti_res < g_cost:
            return "attack:gunner_wait_ti", False

        gpos = Position(gx, gy)
        if pos.distance_squared(gpos) > 2:
            self.nav.set_goal(gpos)
            moved = self.nav.step(ct)
            return f"attack:gunner_walk({gx},{gy})", moved

        # Can't build on our own tile — step off first
        if pos == gpos:
            for d in Direction:
                if d != Direction.CENTRE and ct.can_move(d):
                    ct.move(d)
                    return f"attack:gunner_stepoff({gx},{gy})", True
            return f"attack:gunner_trapped({gx},{gy})", False

        # Destroy any own building at this tile
        bid = ct.get_tile_building_id(gpos)
        if bid is not None and ct.get_team(bid) == ct.get_team():
            if ct.can_destroy(gpos):
                ct.destroy(gpos)
                s.building[gi] = None
                s.my_transport.discard(gi)

        if ct.can_build_gunner(gpos, facing_dir):
            ct.build_gunner(gpos, facing_dir)
            from building import BuildingGunner as BldGunner

            s.building[gi] = BldGunner(s.my_team, facing_dir)
            self._attack_gunner = gi
            return f"attack:gunner_built({gx},{gy})", True

        return f"attack:gunner_blocked({gx},{gy})", False

    def _attack_place_gunner(self, ct: Controller) -> tuple[str, bool] | None:
        """Place gunner at or near frontier facing target."""
        s = self.state
        w = s.w
        frontier = self._chain_frontier
        target = self._attack_target
        if frontier is None or target is None:
            return None
        tx, ty = target % w, target // w
        fx, fy = frontier % w, frontier // w

        # Try frontier itself and its cardinal neighbors
        candidates = [frontier]
        for dx, dy in DIR4_DELTA:
            nx, ny = fx + dx, fy + dy
            if s.in_bounds(nx, ny):
                candidates.append(ny * w + nx)

        for gi in candidates:
            if not _can_place_gunner_at(s, gi):
                continue
            gx, gy = gi % w, gi // w
            fdx = 0 if tx == gx else (1 if tx > gx else -1)
            fdy = 0 if ty == gy else (1 if ty > gy else -1)
            if fdx == 0 and fdy == 0:
                continue
            facing_dir = DELTA_TO_DIR.get((fdx, fdy))
            if facing_dir is None:
                continue
            return self._attack_place_gunner_at(ct, gi, target)

        return None

    # -- Attack: Recycle gunner --

    def _attack_recycle(self, ct: Controller) -> tuple[str, bool] | None:
        """Check if gunner is dead or idle. If so, recycle. Never clears frontier."""
        s = self.state
        w = s.w
        gunner_ti = self._attack_gunner
        if gunner_ti is None:
            return None

        # Gunner destroyed?
        bld = s.building[gunner_ti]
        if not (isinstance(bld, BuildingGunner) and bld.team == s.my_team):
            self._attack_gunner = None
            return "attack:gunner_gone", False

        # Check for idle marker
        for tile in ct.get_nearby_tiles():
            ti = tile.y * w + tile.x
            mbld = s.building[ti]
            if not isinstance(mbld, BuildingMarker) or mbld.team != s.my_team:
                continue
            msg = _decode_marker(mbld.value)
            if isinstance(msg, MarkerIdleGunner) and msg.gunner_tile_index == gunner_ti:
                # Idle — destroy gunner and clean up marker
                gx, gy = gunner_ti % w, gunner_ti // w
                gpos = Position(gx, gy)
                pos = ct.get_position()
                if pos.distance_squared(gpos) <= 2 and ct.can_destroy(gpos):
                    ct.destroy(gpos)
                    s.building[gunner_ti] = None
                    self._attack_gunner = None
                    # Clean up marker
                    mpos = Position(tile.x, tile.y)
                    if ct.can_destroy(mpos):
                        ct.destroy(mpos)
                        s.building[ti] = None
                    return "attack:recycled", True
                self.nav.set_goal(gpos)
                moved = self.nav.step(ct)
                return f"attack:recycle_walk({gx},{gy})", moved

        return None  # gunner still fighting

    # -- Task: Cut Feed --

    def _task_cut_feed(self, ct: Controller) -> tuple[str, bool] | None:
        s = self.state
        w = s.w
        pos = ct.get_position()

        for ti in s.en_turrets:
            # Launchers have no ammo — feeding them is harmless, skip
            turret_bld = s.building[ti]
            if isinstance(turret_bld, BuildingLauncher):
                continue
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

        # Also check bridges targeting enemy turrets (skip launchers)
        for ti in s.en_turrets:
            turret_bld2 = s.building[ti]
            if isinstance(turret_bld2, BuildingLauncher):
                continue
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

        # Collect threats: enemy turrets near core + enemy bots attacking our buildings
        # Skip threats that already have a friendly gunner within r²=13
        threats: list[int] = []
        for ti in s.en_turrets:
            if isinstance(s.building[ti], BuildingLauncher):
                continue  # launchers are nav threats but don't need gunner response
            tx, ty = ti % w, ti // w
            dist_sq = (tx - core_x) ** 2 + (ty - core_y) ** 2
            if dist_sq <= 100:
                if not _has_friendly_gunner_covering(s, ti):
                    threats.append(ti)

        # Enemy bots actually attacking our infrastructure (building damaged)
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == s.my_team:
                continue
            epos = ct.get_position(uid)
            ei = epos.y * w + epos.x
            bld = s.building[ei]
            if (
                bld is not None
                and bld.team == s.my_team
                and not isinstance(bld, (BuildingMarker, BuildingRoad))
            ):
                bid = ct.get_tile_building_id(epos)
                if bid is not None and ct.get_hp(bid) < ct.get_max_hp(bid):
                    if not _has_friendly_gunner_covering(s, ei):
                        threats.append(ei)

        if not threats:
            return None

        # Find nearest own transport tile with flow near the threat
        flow_tiles = s.tiles_with_flow & s.connected_transport
        if not flow_tiles:
            return None

        # Pick closest threat to us
        best_threat: int | None = None
        best_tdist = 1_000_000
        for ti in threats:
            tx, ty = ti % w, ti // w
            d = abs(pos.x - tx) + abs(pos.y - ty)
            if d < best_tdist:
                best_tdist = d
                best_threat = ti

        if best_threat is None:
            return None
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
            if not _can_place_gunner_at(s, gi):
                continue
            gpos = Position(gx, gy)

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

            # Feed direction must not equal facing direction
            chain_dx, chain_dy = fx - gx, fy - gy
            if (chain_dx, chain_dy) == (facing_dx, facing_dy):
                continue
            # Verify flow tile actually outputs toward gunner position
            flow_fi = fy * w + fx
            if not _tile_has_correct_transport(s, flow_fi, gi, w):
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
        w = s.w
        pos = ct.get_position()

        # Enemy bot actively attacking our building (HP < max) → heal if adjacent.
        # Reactive gunner handles offensive response; don't force reroute here.
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == s.my_team:
                continue
            epos = ct.get_position(uid)
            ei = epos.y * w + epos.x
            bld = s.building[ei]
            if bld is None or bld.team != s.my_team:
                continue
            if isinstance(bld, (BuildingMarker, BuildingRoad)):
                continue
            bid = ct.get_tile_building_id(epos)
            if bid is None:
                continue
            if ct.get_hp(bid) >= ct.get_max_hp(bid):
                continue  # not damaged — bot is just passing through
            # Damaged with enemy on it — heal opportunistically if adjacent
            if pos.distance_squared(epos) <= 2:
                if ct.get_action_cooldown() == 0 and ct.can_heal(epos):
                    ct.heal(epos)
                    return f"heal_infra:opp_heal({epos.x},{epos.y})", True

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
                if ni in s.connected_transport:
                    continue  # don't barrier our own transport chain
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
                    # Walk to an adjacent walkable tile of the barrier spot
                    best_adj: Position | None = None
                    best_d = 1_000_000
                    for adx, ady in DIR4_DELTA:
                        ax, ay = nx + adx, ny + ady
                        if not s.in_bounds(ax, ay):
                            continue
                        adj = Position(ax, ay)
                        if not self.nav.is_passable(adj):
                            continue
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
        """Walk to least-recently-seen infra tile. Sticky until arrived."""
        s = self.state
        w = s.w
        pos = ct.get_position()

        infra = s.connected_transport | s.my_harvesters | s.core_tiles
        if not infra:
            return self._task_explore(ct)

        # Sticky target — repick when arrived or gone
        pt = getattr(self, "_patrol_target", None)
        if pt is not None:
            if pt not in infra:
                pt = None
            else:
                ptx, pty = pt % w, pt // w
                if (pos.x - ptx) ** 2 + (pos.y - pty) ** 2 <= 2:
                    pt = None  # arrived

        if pt is None:
            # Pick tile with oldest last_seen
            best_ti: int | None = None
            best_seen = s.age + s.birthday + 1
            for ti in infra:
                if ti == pos.y * w + pos.x:
                    continue
                seen = s.last_seen[ti]
                if seen < best_seen:
                    best_seen = seen
                    best_ti = ti
            pt = best_ti
            self._patrol_target = pt

        if pt is not None:
            tx, ty = pt % w, pt // w
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


def _destroy_friendly(
    ct: Controller, pos: Position, *, allow_barrier: bool = False
) -> None:
    """Destroy own road/marker (and optionally barrier) at pos."""
    bid = ct.get_tile_building_id(pos)
    if bid is None:
        return
    if ct.get_team(bid) != ct.get_team():
        return
    etype = ct.get_entity_type(bid)
    if etype == EntityType.ROAD or etype == EntityType.MARKER:
        if ct.can_destroy(pos):
            ct.destroy(pos)
    elif allow_barrier and etype == EntityType.BARRIER:
        if ct.can_destroy(pos):
            ct.destroy(pos)


def _has_nearby_threat(s: State, tile_idx: int) -> bool:
    """Check if any enemy turret is within Manhattan distance 5 of a tile."""
    w = s.w
    tx, ty = tile_idx % w, tile_idx // w
    for eti in s.en_turrets:
        ex, ey = eti % w, eti // w
        if abs(ex - tx) + abs(ey - ty) <= 5:
            return True
    return False


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
    """Walk ray from gunner position, return first enemy building tile or None.

    Per game rules:
    - Walls: block LoS, NOT targetable -> return None
    - Markers: targetable but DON'T block LoS -> skip
    - All other buildings: block LoS AND are targetable
      -> if enemy, return the tile; if friendly, return None (blocked)
    """
    w, h = s.w, s.h
    my_team = s.my_team
    x, y = gx + fdx, gy + fdy
    while 0 <= x < w and 0 <= y < h:
        if (x - gx) ** 2 + (y - gy) ** 2 > 13:
            break
        ni = y * w + x
        env = s.env[ni]
        if env == Environment.WALL:
            return None  # wall blocks LoS, not targetable
        bld = s.building[ni]
        if bld is not None and not isinstance(bld, BuildingMarker):
            # Non-marker building: blocks LoS and is targetable
            if bld.team != my_team:
                return ni  # enemy target
            return None  # friendly building blocks LoS
        # Marker or no building: keep walking
        x += fdx
        y += fdy
    return None


def _has_friendly_gunner_covering(s: State, threat_ti: int) -> bool:
    """Check if we already have a friendly gunner within r²=13 of the threat."""
    w = s.w
    tx, ty = threat_ti % w, threat_ti // w
    for dx in range(-4, 5):
        for dy in range(-4, 5):
            if dx * dx + dy * dy > 13:
                continue
            gx, gy = tx + dx, ty + dy
            if not s.in_bounds(gx, gy):
                continue
            bld = s.building[gy * w + gx]
            if isinstance(bld, BuildingGunner) and bld.team == s.my_team:
                return True
    return False


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

    env_int = _ENV_INT
    et_int = _ET_INT

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
