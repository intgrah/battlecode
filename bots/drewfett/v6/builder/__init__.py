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
from .state_update import update as state_update
from .task import Task
from .task_connect_excess import ExcessKind, SearchKind, connect_excess
from .task_explore import explore
from .task_harvest_ti import harvest_ti
from .task_heal_core import heal_core
from .task_patrol import patrol
from .task_rush import rush
from .task_scout_enemy import scout_enemy

type TaskFn = Callable[[State, Controller], tuple[Direction, Action | None] | None]

TASK_FNS: dict[Task, TaskFn] = {
    Task.HEAL_CORE: heal_core,
    Task.RUSH: rush,
    Task.CONNECT_BACK: lambda s, c: connect_excess(
        s,
        c,
        ExcessKind.TI_RAX,
        SearchKind.MIXED,
    ),
    Task.HARVEST_TI: harvest_ti,
    Task.SCOUT_ENEMY: scout_enemy,
    Task.EXPLORE: explore,
    Task.PATROL: patrol,
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

    def run(self, ct: Controller) -> None:
        s = self.state
        t0 = ct.get_cpu_time_elapsed()
        state_update(s, ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"upd={t1 - t0}")

        s.claim = None

        move, build = self._run_policy(ct)
        self._execute(ct, move, build)

    def _run_policy(self, ct: Controller) -> tuple[Direction, Action | None]:
        s = self.state
        pos = s.pos
        print(f"  pos=({pos.x},{pos.y})")
        for score, task in _policy(s):
            if score <= 0:
                continue
            t0 = ct.get_cpu_time_elapsed()
            print(f"  try {task.name} @{t0}")
            fn = TASK_FNS[task]
            result = fn(s, ct)
            ct.get_cpu_time_elapsed() - t0
            if result is not None:
                print(f"  -> {task.name} {result}")
                return result
        print("  -> IDLE")
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


def _policy(state: State) -> list[tuple[float, Task]]:
    scores: list[tuple[float, Task]] = []

    seen = sum(1 for e in state.env if e is not None)
    seen_frac = seen / (state.w * state.h)
    explore_score = 95.0 if seen_frac < 0.3 else 55.0 if seen_frac < 0.5 else 20.0

    # Rush triggers when enough Ti flows to core (~2 connected harvesters)
    core_flow = sum(state.flow.ti[i] for i in state.my_core_tiles)
    rush_ready = core_flow >= 0.4 and state.en_core_pos is not None

    scores.append((999.0, Task.HEAL_CORE))
    scores.append((200.0 if rush_ready else 0.0, Task.RUSH))
    scores.append((160.0 if rush_ready else 0.0, Task.SCOUT_ENEMY))
    scores.append((150.0, Task.CONNECT_BACK))
    scores.append((100.0, Task.HARVEST_TI))
    scores.append((explore_score, Task.EXPLORE))
    scores.append((15.0, Task.PATROL))
    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
