from collections.abc import Callable
from enum import Enum, auto

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from marker import MarkerEureka
from unit import Unit

from .build import Action, PlaceRoad, Task, execute
from .state import State
from .state_dump import dump
from .state_update import update as state_update
from .task_bridge_chain import (
    _find_disconnected_harvester as find_disconnected_harvester,
)
from .task_bridge_chain import bridge_chain
from .task_connect_excess import ExcessKind, SearchKind, connect_excess
from .task_explore import explore
from .task_harvest_ti import harvest_ti
from .task_heal_bridge import find_damaged_bridge, heal_bridge
from .task_heal_core import heal_core
from .task_nav_enemy_core import nav_enemy_core
from .task_place_launcher import place_launcher
from .task_place_sentinel import place_sentinel
from .task_repair_bridge import _find_broken_bridge, repair_bridge
from .task_rush import rush

DEBUG_DUMP = False

_INITIAL_BUILDERS = 6
_ECON_BUILDERS = 2
_TI_HARVESTER_BUFFER = 600

type TaskFn = Callable[[State, Controller], tuple[Direction, Action | None] | None]

TASK_FNS: dict[Task, TaskFn] = {
    Task.CONNECT_EXCESS_TI: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.TI_RAX,
        SearchKind.MIXED,
    ),
    Task.CONNECT_EXCESS_TI_BRIDGE: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.TI_RAX,
        SearchKind.BRIDGE,
    ),
    Task.HARVEST_TI: harvest_ti,
    Task.EXPLORE: explore,
    Task.NAV_ENEMY_CORE: nav_enemy_core,
    Task.HEAL_CORE: heal_core,
    Task.PLACE_LAUNCHER: place_launcher,
    Task.REPAIR_BRIDGE: repair_bridge,
    Task.PLACE_SENTINEL: place_sentinel,
    Task.HEAL_BRIDGE: heal_bridge,
    Task.BRIDGE_CHAIN: bridge_chain,
    Task.RUSH: rush,
}


class Role(Enum):
    ECON = auto()
    AGGRO = auto()


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        core_pos = _find_core(ct)
        self.state = State(ct, core_pos)
        spawn_round = self.state.birthday - 1
        if spawn_round <= _ECON_BUILDERS:
            self.role = Role.ECON
        elif spawn_round <= _INITIAL_BUILDERS:
            self.role = Role.AGGRO
        else:
            self.role = Role.ECON

    def run(self, ct: Controller) -> None:
        s = self.state
        state_update(s, ct)

        if DEBUG_DUMP:
            dump(s, ct)
        s.claim = None

        move, build = self._run_policy(ct)

        if move != Direction.CENTRE:
            if ct.can_move(move):
                ct.move(move)
            elif isinstance(build, PlaceRoad):
                execute(build, ct)
                if ct.can_move(move):
                    ct.move(move)
                build = None
        if build is not None:
            execute(build, ct)

        if s.debug_target is not None:
            ct.draw_indicator_line(ct.get_position(), *s.debug_target)
        s.debug_target = None
        self._write_marker(ct)

    def _run_policy(self, ct: Controller) -> tuple[Direction, Action | None]:
        s = self.state
        match self.role:
            case Role.ECON:
                policy = _policy_econ(s, ct)
            case Role.AGGRO:
                policy = _policy_aggro(s, ct)
        for _, task in policy:
            fn = TASK_FNS[task]
            result = fn(s, ct)
            if result is not None:
                return result
        return Direction.CENTRE, None

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


def _policy_econ(state: State, ct: Controller) -> list[tuple[float, Task]]:
    scores: list[tuple[float, Task]] = []

    core_damaged = state.my_core_hp < GameConstants.CORE_MAX_HP
    scores.append((999.0 if core_damaged else 0.0, Task.HEAL_CORE))

    has_damaged_bridge = find_damaged_bridge(ct) is not None
    scores.append((250.0 if has_damaged_bridge else 0.0, Task.HEAL_BRIDGE))

    has_broken = _find_broken_bridge(state) is not None
    scores.append((200.0 if has_broken else 0.0, Task.REPAIR_BRIDGE))

    has_disconnected = find_disconnected_harvester(state) is not None
    scores.append((175.0 if has_disconnected else 0.0, Task.BRIDGE_CHAIN))

    has_excess = any(
        state.my_flow.excess[state.idx(p.x, p.y)] > 0.01
        for p in state.my_harvesters | state.my_transport
    )
    scores.append((160.0 if has_excess else 0.0, Task.CONNECT_EXCESS_TI_BRIDGE))

    ti, _ = ct.get_global_resources()
    n_harv = len(state.my_harvesters)
    need_harvester = (
        n_harv == 0
        or (
            n_harv < 2
            and state.age > 100
            and ti > _TI_HARVESTER_BUFFER
            and state.ore_ti - state.my_harvesters
        )
        or (
            n_harv >= 2
            and ti > _TI_HARVESTER_BUFFER
            and state.ore_ti - state.my_harvesters
        )
    )
    scores.append((100.0 if need_harvester else 0.0, Task.HARVEST_TI))

    scores.append((20.0, Task.EXPLORE))

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores


def _policy_aggro(state: State, _ct: Controller) -> list[tuple[float, Task]]:
    scores: list[tuple[float, Task]] = []

    core_damaged = state.my_core_hp < GameConstants.CORE_MAX_HP
    scores.append((999.0 if core_damaged else 0.0, Task.HEAL_CORE))

    scores.append((100.0, Task.RUSH))
    scores.append((20.0, Task.EXPLORE))

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
