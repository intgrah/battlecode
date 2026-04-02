from collections.abc import Callable

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from config import DEBUG_DUMP, OPENING, OpeningMode
from hardcode.opening.compiler import (
    CompiledActionMove,
    CompiledMoveAction,
)
from marker import MarkerEureka
from unit import Unit

from .action import (
    Action,
    PlaceBarrier,
    PlaceBridge,
    PlaceConveyor,
    PlaceFoundry,
    PlaceGunner,
    PlaceHarvester,
    PlaceLauncher,
    PlaceRoad,
    PlaceSentinel,
    PlaceSplitter,
)
from .helpers import execute
from .state import State
from .state_dump import dump
from .state_update import update as state_update
from .task import Task
from .task_barrier_ore import barrier_ore
from .task_connect_excess import ExcessKind, SearchKind, connect_excess
from .task_explore import explore
from .task_fire_enemy_transport import fire_enemy_transport
from .task_harvest_ax import harvest_ax
from .task_harvest_ti import harvest_ti
from .task_heal_core import heal_core
from .task_heal_turret import heal_turret
from .task_patrol import patrol
from .task_place_launcher import place_launcher
from .task_place_sentinel import place_sentinel

type TaskFn = Callable[[State, Controller], tuple[Direction, Action | None] | None]

TASK_FNS: dict[Task, TaskFn] = {
    Task.CONNECT_EXCESS_TI: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.TI_RAX,
        SearchKind.MIXED,
    ),
    Task.CONNECT_EXCESS_AX: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.AX,
        SearchKind.AX_CHAIN,
    ),
    Task.HARVEST_TI: harvest_ti,
    Task.HARVEST_AX: harvest_ax,
    Task.EXPLORE: explore,
    Task.PATROL: patrol,
    Task.HEAL_CORE: heal_core,
    Task.PLACE_LAUNCHER: place_launcher,
    Task.BARRIER_ORE: barrier_ore,
    Task.FIRE_ENEMY_TRANSPORT: fire_enemy_transport,
    Task.PLACE_SENTINEL: place_sentinel,
    Task.HEAL_TURRET: heal_turret,
}


def _destroy_friendly(ct: Controller, pos: Position) -> None:
    bid = ct.get_tile_building_id(pos)
    if bid is not None and ct.get_team(bid) == ct.get_team() and ct.can_destroy(pos):
        ct.destroy(pos)


def _exec_build(ct: Controller, action: Action) -> None:
    match action:
        case PlaceRoad(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_road(pos):
                ct.build_road(pos)
        case PlaceHarvester(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_harvester(pos):
                ct.build_harvester(pos)
        case PlaceConveyor(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_conveyor(pos, direction):
                ct.build_conveyor(pos, direction)
        case PlaceSplitter(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_splitter(pos, direction):
                ct.build_splitter(pos, direction)
        case PlaceBridge(pos, target):
            _destroy_friendly(ct, pos)
            if ct.can_build_bridge(pos, target):
                ct.build_bridge(pos, target)
        case PlaceBarrier(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_barrier(pos):
                ct.build_barrier(pos)
        case PlaceLauncher(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_launcher(pos):
                ct.build_launcher(pos)
        case PlaceGunner(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_gunner(pos, direction):
                ct.build_gunner(pos, direction)
        case PlaceSentinel(pos, direction):
            _destroy_friendly(ct, pos)
            if ct.can_build_sentinel(pos, direction):
                ct.build_sentinel(pos, direction)
        case PlaceFoundry(pos):
            _destroy_friendly(ct, pos)
            if ct.can_build_foundry(pos):
                ct.build_foundry(pos)


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        core_pos = _find_core(ct)
        self.state = State(ct, core_pos)
        self._script_idx: int = 0
        self._off_script: bool = False

    def run(self, ct: Controller) -> None:
        s = self.state
        t0 = ct.get_cpu_time_elapsed()
        state_update(s, ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"update={t1 - t0}us")

        if DEBUG_DUMP:
            dump(s, ct)
        s.claim = None

        has_script = s.compiled is not None and not self._off_script
        if OPENING != OpeningMode.OFF and has_script:
            self._run_script(ct)
            if OPENING == OpeningMode.OPENING_ONLY:
                return
            if not self._off_script:
                return

        move, build = self._run_policy(ct)
        t2 = ct.get_cpu_time_elapsed()
        print(f"policy={t2 - t1}us total={t2 - t0}us")
        self._execute(ct, move, build)

    def _run_script(self, ct: Controller) -> None:
        compiled = self.state.compiled
        assert compiled is not None
        if self._script_idx >= len(compiled):
            self._off_script = True
            return

        turn = compiled[self._script_idx]
        self._script_idx += 1
        pos = ct.get_position()

        match turn:
            case CompiledActionMove(action, move):
                if action is not None:
                    _exec_build(ct, action)
                if move is not None:
                    if ct.can_move(move):
                        ct.move(move)
                    else:
                        ct.draw_indicator_dot(pos, 255, 0, 0)
                        self._off_script = True
            case CompiledMoveAction(move, action):
                if move is not None:
                    if ct.can_move(move):
                        ct.move(move)
                    else:
                        ct.draw_indicator_dot(pos, 255, 0, 0)
                        self._off_script = True
                        return
                if action is not None:
                    _exec_build(ct, action)

        if self._script_idx >= len(compiled):
            ct.draw_indicator_dot(ct.get_position(), 0, 255, 0)
            self._off_script = True

    def _run_policy(self, ct: Controller) -> tuple[Direction, Action | None]:
        s = self.state
        for score, task in _policy(s):
            if score <= 0:
                continue
            t0 = ct.get_cpu_time_elapsed()
            fn = TASK_FNS[task]
            result = fn(s, ct)
            t1 = ct.get_cpu_time_elapsed()
            elapsed = t1 - t0
            if result is not None:
                print(f"  task={task.name} {elapsed}us OK")
                print(f"  {result}")
                return result
            print(f"  task={task.name} {elapsed}us FAIL")
        print("  task=NONE")
        return Direction.CENTRE, None

    def _execute(self, ct: Controller, move: Direction, build: Action | None) -> None:
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

        self._write_marker(ct)

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


def _policy(state: State) -> list[tuple[float, Task]]:
    scores: list[tuple[float, Task]] = []
    scores.append((999.0, Task.HEAL_CORE))
    scores.append((150.0, Task.CONNECT_EXCESS_TI))
    scores.append((100.0, Task.HARVEST_TI))
    scores.append((20.0, Task.EXPLORE))
    scores.append((25.0 if state.infra_max_staleness > 50 else 15.0, Task.PATROL))
    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
