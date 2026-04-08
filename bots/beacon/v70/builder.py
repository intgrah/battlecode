"""Builder bot: BFS nav + capacity-aware harvesting + role-based task dispatch.

Single NavBfs instance per builder. A* recomputed fresh each turn
(no cached path -- eliminates stale-path bugs).

Roles: ECON (0), ATTACK (1), DEFENSE (2).
"""

from __future__ import annotations

import random

from bbot_tracker import BbotTracker
from builder_attack import Attack, _run_attack
from builder_defense import _run_defense
from builder_econ import _run_econ
from builder_helpers import (
    _find_core,
    _log,
    _task_cut_feed,
    _update_nearby_tiles,
)
from cambc import Controller, Direction, Environment, Position
from core import OFFSET_TO_INDEX, role_for_spawn
from explore import ExploreGrid
from nav import NavBfs
from state import State
from state_update import update as state_update
from symmetry import SymmetryDetector
from tracker import Tracker
from unit import Unit


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        w = ct.get_map_width()
        h = ct.get_map_height()

        core_pos = _find_core(ct)

        # Role assignment via spawn offset from core
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
        self._my_harvesters: set[int] = set()
        self._blocked_ore: dict[int, int] = {}
        self._harvest_stuck: int = 0
        self._patrol_target: int | None = None

        # Attack -- delegated to Attack class
        self._attack = Attack()

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

        # -- Task dispatch --
        _ROLE_NAME = ("E", "A", "D")
        task_name, moved = self._run_tasks(ct)

        # -- VIS disabled for server --

        new_pos = ct.get_position()
        r = _ROLE_NAME[self._role] if self._role < 3 else "?"
        m = "M" if pos != new_pos else "."
        _log(
            f"T{s.age + s.birthday} {r}{m}@({new_pos.x},{new_pos.y}) {task_name}",
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
            return _run_econ(self, ct)
        if self._role == 1:
            return _run_attack(self, ct)
        if self._role == 2:
            return _run_defense(self, ct)
        return _run_econ(self, ct)  # fallback

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
        result = _task_cut_feed(s, self.nav, ct)
        if result is not None:
            return result

        return None
