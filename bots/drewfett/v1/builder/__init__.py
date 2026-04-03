from collections.abc import Callable

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
    Team,
)
from config import DEBUG_DUMP, OPENING, OpeningMode
from hardcode.known import KnownMap
from hardcode.map import SYMMETRY
from hardcode.opening import Opening, get_opening
from hardcode.opening.compiler import (
    CompiledActionMove,
    CompiledMoveAction,
    CompiledTurn,
    dsl_compile,
)
from hardcode.opening.mirror import mirror_opening
from marker import MarkerEureka, MarkerOpeningBook
from marker import decode as decode_marker
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
from .task_defend import defend
from .task_defend_core import defend_core
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
    Task.DEFEND: defend,
    Task.DEFEND_CORE: defend_core,
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
        self._compiled: list[CompiledTurn] | None = None
        self._script_idx: int = 0
        self._off_script: bool = False

        opening, km = _read_opening(ct, core_pos)
        if opening is not None and km is not None:
            if ct.get_team() == Team.B:
                opening = mirror_opening(opening, SYMMETRY[km])
            spawn_turn = self.state.birthday - 1
            spawn_order = sum(
                1 for s in opening.core_spawns[:spawn_turn] if s is not None
            )
            if 0 <= spawn_order < len(opening.builder_scripts):
                self._compiled = dsl_compile(
                    ct.get_position(),
                    opening.builder_scripts[spawn_order],
                )

    def run(self, ct: Controller) -> None:
        s = self.state
        t0 = ct.get_cpu_time_elapsed()
        state_update(s, ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"update={t1 - t0}us")

        if DEBUG_DUMP:
            dump(s, ct)
        s.claim = None

        has_script = self._compiled is not None and not self._off_script
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
        assert self._compiled is not None
        if self._script_idx >= len(self._compiled):
            self._off_script = True
            return

        turn = self._compiled[self._script_idx]
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

        if self._script_idx >= len(self._compiled):
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
        if isinstance(build, PlaceRoad) and move != Direction.CENTRE:
            # Road: only build if we can't move (need the road to walk on)
            if ct.can_move(move):
                ct.move(move)
            else:
                execute(build, ct)
                if ct.can_move(move):
                    ct.move(move)
        elif build is not None and move != Direction.CENTRE:
            # Build first (while adjacent), then step toward next site
            execute(build, ct)
            if ct.can_move(move):
                ct.move(move)
        elif move != Direction.CENTRE:
            if ct.can_move(move):
                ct.move(move)
        elif build is not None:
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


_MARKER_OFFSETS = ((2, 2), (-2, -2), (2, -2), (-2, 2), (0, 2), (0, -2), (2, 0), (-2, 0))


def _read_opening(
    ct: Controller,
    core_pos: Position,
) -> tuple[Opening | None, KnownMap | None]:
    w, h = ct.get_map_width(), ct.get_map_height()
    for odx, ody in _MARKER_OFFSETS:
        mx, my = core_pos.x + odx, core_pos.y + ody
        if not (0 <= mx < w and 0 <= my < h):
            continue
        mp = Position(mx, my)
        bid = ct.get_tile_building_id(mp)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != ct.get_team():
            continue
        marker_val = ct.get_marker_value(bid)
        msg = decode_marker(marker_val)
        if isinstance(msg, MarkerOpeningBook):
            km_list = list(KnownMap)
            idx = msg.map_index
            if 0 <= idx < len(km_list):
                km = km_list[idx]
                return get_opening(km), km
    return None, None


def _policy(state: State) -> list[tuple[float, Task]]:
    scores: list[tuple[float, Task]] = []

    seen = sum(1 for e in state.env if e is not None)
    seen_frac = seen / (state.w * state.h)
    explore_score = 95.0 if seen_frac < 0.3 else 55.0 if seen_frac < 0.5 else 20.0

    scores.append((999.0, Task.HEAL_CORE))
    scores.append((180.0 if state.en_turrets else 0.0, Task.DEFEND))
    scores.append((150.0, Task.CONNECT_EXCESS_TI))
    scores.append((100.0, Task.HARVEST_TI))
    scores.append((90.0, Task.DEFEND_CORE))
    scores.append((40.0 if state.en_harvesters else 0.0, Task.PLACE_SENTINEL))
    scores.append((25.0 if state.infra_max_staleness > 50 else 15.0, Task.PATROL))
    scores.append((explore_score, Task.EXPLORE))
    scores.append((10.0, Task.HEAL_TURRET))
    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
