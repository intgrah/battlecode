"""Builder bot: task waterfall with BFS navigation and hard work caps.

Key design:
- BFS navigation with iteration cap (not time-based)
- NO flow simulation -- uses connected_harvesters set
- Greedy connect-back: one conveyor per turn toward core
- Sentinel-based attack: walk toward enemy flow, drop sentinels
- Hard iteration/work caps everywhere
"""

from __future__ import annotations

import random
from collections.abc import Callable

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from marker import MarkerEureka
from turn import ActionMove, ActionOnly, MoveAction, MoveOnly, Turn, Wait
from unit import Unit

from action import Action, PlaceRoad
from .helpers import execute
from .state import State
from .state_update import update as state_update
from .task import Task
from .task_cut_feed import cut_feed
from .task_defend import defend
from .task_explore import explore
from .task_harvest import harvest
from .task_heal_core import heal_core
from .task_siege import siege

type OldResult = tuple[Direction, Action | None] | None
type TaskFn = Callable[[State, Controller], OldResult]

TASK_FNS: dict[Task, TaskFn] = {
    Task.HEAL_CORE: heal_core,
    Task.CUT_FEED: cut_feed,
    Task.DEFEND: defend,
    Task.HARVEST: harvest,
    Task.SIEGE: siege,
    Task.EXPLORE: explore,
}


class Builder(Unit):
    def __init__(self, ct: Controller, pre_state: State | None = None) -> None:
        core_pos = _find_core(ct)
        self.state = State(ct, core_pos, pre=pre_state)
        self._stuck_turns = 0

    def run(self, ct: Controller) -> None:
        # First turn: init already burned most of budget
        if ct.get_cpu_time_elapsed() > 1400:
            s = self.state
            s.age += 1
            s.pos = ct.get_position()
            return

        s = self.state
        state_update(s, ct)

        # Self-heal if damaged -- priority over all tasks
        if ct.get_hp() < ct.get_max_hp() and ct.get_action_cooldown() == 0:
            pos = ct.get_position()
            ti, _ = ct.get_global_resources()
            if ti >= 1 and ct.can_heal(pos):
                ct.heal(pos)

        s.claim = None

        turn = self._run_policy(ct)
        pos_before = ct.get_position()
        self._execute_turn(ct, turn)
        pos_after = ct.get_position()

        # Livelock breaker
        if pos_before == pos_after and turn is not None:
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

        # Opportunistic heal: if action unused, heal nearby damaged building
        if ct.get_action_cooldown() == 0:
            self._opportunistic_heal(ct)

        self._write_marker(ct)

    def _run_policy(self, ct: Controller) -> Turn | None:
        s = self.state
        for score, task in _policy(s):
            if score <= 0:
                continue
            fn = TASK_FNS[task]
            result = fn(s, ct)
            if result is not None:
                return _to_turn(result)
        return None

    def _move_or_detour(self, ct: Controller, direction: Direction) -> bool:
        """Try to move. If blocked, 50% chance to detour randomly."""
        if ct.can_move(direction):
            ct.move(direction)
            return True
        if random.random() < 0.5:
            dirs = [d for d in Direction if d != Direction.CENTRE and ct.can_move(d)]
            if dirs:
                ct.move(random.choice(dirs))
                return False
            pos = ct.get_position()
            candidates = [d for d in Direction if d != Direction.CENTRE]
            random.shuffle(candidates)
            for d in candidates:
                nxt = pos.add(d)
                if ct.can_build_road(nxt):
                    ct.build_road(nxt)
                    if ct.can_move(d):
                        ct.move(d)
                    return False
        return False

    def _execute_turn(self, ct: Controller, turn: Turn | None) -> None:
        if turn is None:
            return
        match turn:
            case Wait():
                pass
            case MoveOnly(direction):
                self._move_or_detour(ct, direction)
            case ActionOnly(action):
                execute(action, ct)
            case ActionMove(action, direction):
                if isinstance(action, PlaceRoad):
                    if ct.can_move(direction):
                        ct.move(direction)
                    else:
                        execute(action, ct)
                        self._move_or_detour(ct, direction)
                else:
                    execute(action, ct)
                    self._move_or_detour(ct, direction)
            case MoveAction(direction, action):
                if self._move_or_detour(ct, direction):
                    execute(action, ct)

    def _opportunistic_heal(self, ct: Controller) -> None:
        my_team = ct.get_team()
        best_pos: Position | None = None
        best_frac = 1.0
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) != my_team:
                continue
            etype = ct.get_entity_type(bid)
            if etype == EntityType.CORE:
                bp = ct.get_position(bid)
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        tp = Position(bp.x + dx, bp.y + dy)
                        if ct.can_heal(tp):
                            hp = ct.get_hp(bid)
                            max_hp = ct.get_max_hp(bid)
                            frac = hp / max_hp
                            if frac < best_frac:
                                best_frac = frac
                                best_pos = tp
            else:
                hp = ct.get_hp(bid)
                max_hp = ct.get_max_hp(bid)
                if hp >= max_hp:
                    continue
                pos = ct.get_position(bid)
                if ct.can_heal(pos):
                    frac = hp / max_hp
                    if frac < best_frac:
                        best_frac = frac
                        best_pos = pos
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) != my_team:
                continue
            hp = ct.get_hp(uid)
            max_hp = ct.get_max_hp(uid)
            if hp >= max_hp:
                continue
            pos = ct.get_position(uid)
            if ct.can_heal(pos):
                frac = hp / max_hp
                if frac < best_frac:
                    best_frac = frac
                    best_pos = pos
        if best_pos is not None:
            ct.heal(best_pos)

    def _write_marker(self, ct: Controller) -> None:
        s = self.state
        marker_val = None
        if s.claim is not None:
            s.last_claim = s.claim
            marker_val = s.claim.encode()
        elif s.symmetry is not None:
            marker_val = MarkerEureka(s.symmetry.value).encode()
        if marker_val is None:
            return
        pos = ct.get_position()
        for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
            if t == pos:
                continue
            env = ct.get_tile_env(t)
            if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                continue
            if ct.can_place_marker(t):
                ct.place_marker(t, marker_val)
                return
        for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
            if t == pos:
                continue
            bid = ct.get_tile_building_id(t)
            if (
                bid is not None
                and ct.get_entity_type(bid) == EntityType.MARKER
                and ct.get_team(bid) == ct.get_team()
            ):
                ct.destroy(t)
                ct.place_marker(t, marker_val)
                return


def _find_core(ct: Controller) -> Position:
    my = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
            return ct.get_position(bid)
    raise RuntimeError


def _to_turn(result: OldResult) -> Turn | None:
    """Convert old-style (Direction, Action | None) to Turn."""
    if result is None:
        return None
    move, build = result
    if move == Direction.CENTRE and build is None:
        return Wait()
    if move == Direction.CENTRE and build is not None:
        return ActionOnly(build)
    if build is None:
        return MoveOnly(move)
    # All builds happen first (adjacent to target), then step toward next site
    return ActionMove(build, move)


def _rush_ready(state: State) -> bool:
    """True if any harvester is connected to core (flow gate)."""
    return bool(state.connected_harvesters)


def _policy(state: State) -> list[tuple[float, Task]]:
    seen = sum(1 for e in state.env if e is not None)
    seen_frac = seen / (state.w * state.h)
    ready = _rush_ready(state)

    match state.role:
        case 0:  # ECON -- harvest, connect, explore
            explore_score = (
                120.0 if seen_frac < 0.3 else 80.0 if seen_frac < 0.6 else 30.0
            )
            scores: list[tuple[float, Task]] = [
                (999.0, Task.HEAL_CORE),
                (500.0, Task.CUT_FEED),
                (300.0 if state.en_turrets else 0.0, Task.DEFEND),
                (200.0, Task.HARVEST),
                (explore_score, Task.EXPLORE),
            ]
        case 1:  # ATTACK -- econ early, then siege once flow established
            explore_score = (
                95.0 if seen_frac < 0.3 else 55.0 if seen_frac < 0.5 else 20.0
            )
            scores = [
                (999.0, Task.HEAL_CORE),
                (500.0, Task.CUT_FEED),
                (300.0 if state.en_turrets else 0.0, Task.DEFEND),
                (200.0, Task.SIEGE),
                (100.0 if not ready else 50.0, Task.HARVEST),
                (explore_score, Task.EXPLORE),
            ]
        case _:  # Fallback
            explore_score = (
                80.0 if seen_frac < 0.3 else 40.0 if seen_frac < 0.6 else 15.0
            )
            scores = [
                (999.0, Task.HEAL_CORE),
                (500.0, Task.CUT_FEED),
                (300.0 if state.en_turrets else 0.0, Task.DEFEND),
                (200.0, Task.HARVEST),
                (explore_score, Task.EXPLORE),
            ]

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
