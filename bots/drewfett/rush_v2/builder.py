"""Builder bot — state update, role-based policy dispatch, turn execution."""

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum, auto

from action import execute
from cambc import (
    Controller,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from marker import MarkerEureka, MarkerRole
from state import State
from state_update import update
from turn import ActionMove, ActionOnly, MoveAction, MoveOnly, Turn, Wait
from unit import Unit
from util import Role

# ---------------------------------------------------------------------------
# Task enum — each entry is a distinct builder objective
# ---------------------------------------------------------------------------


class Task(IntEnum):
    HEAL_CORE = auto()
    HEAL_INFRA = auto()
    SIEGE = auto()
    SCOUT = auto()
    CONNECT = auto()
    HARVEST = auto()
    EXPLORE = auto()
    PATROL = auto()


# ---------------------------------------------------------------------------
# Task dispatch table
# ---------------------------------------------------------------------------

type TaskFn = Callable[[State, Controller], Turn | None]

from tasks import connect, explore, harvest, heal_core, heal_infra, patrol, scout, siege

TASK_FNS: dict[Task, TaskFn] = {
    Task.HEAL_CORE: heal_core.run,
    Task.HEAL_INFRA: heal_infra.run,
    Task.SIEGE: siege.run,
    Task.SCOUT: scout.run,
    Task.CONNECT: connect.run,
    Task.HARVEST: harvest.run,
    Task.EXPLORE: explore.run,
    Task.PATROL: patrol.run,
}


# ---------------------------------------------------------------------------
# Policy tables: list of (priority, task, task_fn) per role
# Higher priority = tried first. Callable is the task function.
# ---------------------------------------------------------------------------

type PolicyEntry = tuple[float, Task, TaskFn]


def _policy_econ(state: State) -> list[PolicyEntry]:
    seen = sum(1 for e in state.env if e is not None)
    seen_frac = seen / (state.w * state.h)
    explore_score = 95.0 if seen_frac < 0.3 else 55.0 if seen_frac < 0.5 else 20.0
    return [
        (999.0, Task.HEAL_CORE, heal_core.run),
        (150.0, Task.CONNECT, connect.run),
        (100.0, Task.HARVEST, harvest.run),
        (explore_score, Task.EXPLORE, explore.run),
        (15.0, Task.PATROL, patrol.run),
    ]


def _policy_rush(state: State) -> list[PolicyEntry]:
    ready = _rush_ready(state)
    seen = sum(1 for e in state.env if e is not None)
    seen_frac = seen / (state.w * state.h)
    explore_score = 95.0 if seen_frac < 0.3 else 55.0 if seen_frac < 0.5 else 20.0
    entries: list[PolicyEntry] = [
        (999.0, Task.HEAL_CORE, heal_core.run),
    ]
    if ready:
        entries.append((200.0, Task.SIEGE, siege.run))
        entries.append((160.0, Task.SCOUT, scout.run))
    else:
        entries.append((100.0, Task.HARVEST, harvest.run))
        entries.append((150.0, Task.CONNECT, connect.run))
    entries.append((explore_score, Task.EXPLORE, explore.run))
    entries.append((15.0, Task.PATROL, patrol.run))
    entries.sort(key=lambda e: e[0], reverse=True)
    return entries


def _policy_home(state: State) -> list[PolicyEntry]:
    return [
        (999.0, Task.HEAL_CORE, heal_core.run),
        (200.0, Task.HEAL_INFRA, heal_infra.run),
        (150.0, Task.CONNECT, connect.run),
        (100.0, Task.HARVEST, harvest.run),
        (50.0, Task.PATROL, patrol.run),
        (20.0, Task.EXPLORE, explore.run),
    ]


def _rush_ready(state: State) -> bool:
    """Check if we have enough titanium flowing and know where the enemy is."""
    core_flow = sum(state.flow.ti[i] for i in state.my_core_tiles)
    return core_flow >= 0.4 and state.en_core_pos is not None


# ---------------------------------------------------------------------------
# Builder class
# ---------------------------------------------------------------------------


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        core_pos = _find_core(ct)
        self.state: State = State(ct, core_pos)

    def run(self, ct: Controller) -> None:
        s = self.state
        update(s, ct)
        s.claim = None

        turn = self._run_policy(ct)
        if turn is not None:
            self._execute_turn(ct, turn)

        self._write_marker(ct)

    # -- Policy dispatch ------------------------------------------------

    def _run_policy(self, ct: Controller) -> Turn | None:
        s = self.state
        policy = _get_policy(s)
        for score, task, fn in policy:
            if score <= 0:
                continue
            result = fn(s, ct)
            if result is not None:
                print(f"  task={task.name} OK")
                return result
        print("  task=NONE")
        return None

    # -- Turn execution -------------------------------------------------

    def _execute_turn(self, ct: Controller, turn: Turn) -> None:
        match turn:
            case Wait():
                pass
            case MoveOnly(direction):
                if ct.can_move(direction):
                    ct.move(direction)
            case ActionOnly(action):
                execute(action, ct)
            case ActionMove(action, direction):
                execute(action, ct)
                if ct.can_move(direction):
                    ct.move(direction)
            case MoveAction(direction, action):
                if ct.can_move(direction):
                    ct.move(direction)
                    execute(action, ct)
                # If move failed, don't execute action (not in position)

    # -- Marker writing -------------------------------------------------

    def _write_marker(self, ct: Controller) -> None:
        s = self.state

        # If we have a claim to broadcast, write that
        if s.claim is not None:
            encoded = s.claim.encode()
            _place_marker_nearby(ct, encoded)
            return

        # Otherwise broadcast eureka if symmetry is known
        if s.symmetry is not None:
            encoded = MarkerEureka(symmetry=s.symmetry.value).encode()
            _place_marker_nearby(ct, encoded)
            return

        # Fallback: write role marker so census stays fresh
        encoded = MarkerRole(
            role=s.role.value,
            birthday=s.birthday,
            turn=ct.get_current_round(),
        ).encode()
        _place_marker_nearby(ct, encoded)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_core(ct: Controller) -> Position:
    """Scan nearby buildings for own CORE and return its position."""
    my_team = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) == my_team and ct.get_entity_type(bid) == EntityType.CORE:
            return ct.get_position(bid)
    msg = "Builder could not find own core on spawn"
    raise RuntimeError(msg)


def _get_policy(state: State) -> list[PolicyEntry]:
    """Dispatch to the correct policy table based on current role."""
    match state.role:
        case Role.ECON:
            return _policy_econ(state)
        case Role.RUSH:
            return _policy_rush(state)
        case Role.HOME:
            return _policy_home(state)
        case Role.FLEX:
            # Flex defaults to RUSH if rush-ready, else ECON
            if _rush_ready(state):
                return _policy_rush(state)
            return _policy_econ(state)
        case _:
            return _policy_econ(state)


def _place_marker_nearby(ct: Controller, encoded: int) -> None:
    """Place a marker on a nearby non-ore tile within action radius."""
    pos = ct.get_position()
    for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
        if t == pos:
            continue
        env = ct.get_tile_env(t)
        if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            continue
        if ct.can_place_marker(t):
            ct.place_marker(t, encoded)
            return
    # Fallback: overwrite an existing own marker
    my_team = ct.get_team()
    for t in ct.get_nearby_tiles(GameConstants.ACTION_RADIUS_SQ):
        if t == pos:
            continue
        bid = ct.get_tile_building_id(t)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.MARKER
            and ct.get_team(bid) == my_team
        ):
            ct.destroy(t)
            ct.place_marker(t, encoded)
            return
