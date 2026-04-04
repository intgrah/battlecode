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
from turn import ActionMove, ActionOnly, MoveAction, MoveOnly, Turn, Wait
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
from .task_heal_infra import heal_infra
from .task_patrol import patrol
from .task_road_harvesters import road_harvesters
from .task_rush import rush
from .task_scout_enemy import scout_enemy

type OldResult = tuple[Direction, Action | None] | None
type TaskFn = Callable[[State, Controller], OldResult]

TASK_FNS: dict[Task, TaskFn] = {
    Task.HEAL_CORE: heal_core,
    Task.HEAL_INFRA: heal_infra,
    Task.ROAD_HARVESTERS: road_harvesters,
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
        t = ct.get_cpu_time_elapsed
        t0 = t()
        state_update(s, ct)
        t1 = t()
        _ROLE_NAMES = {0: "ECON", 1: "RUSH", 2: "HOME"}
        print(
            f"[{_ROLE_NAMES.get(s.role, '?')}] pos=({s.pos.x},{s.pos.y}) upd={t1 - t0} @{t1}"
        )

        s.claim = None

        turn = self._run_policy(ct)
        t2 = t()
        print(f"turn={turn}")
        pos_before = ct.get_position()
        self._execute_turn(ct, turn)
        pos_after = ct.get_position()
        t3 = t()
        print(f"tot={t3 - t0} upd={t1 - t0} pol={t2 - t1} exec={t3 - t2}")
        if pos_before == pos_after and turn is not None:
            print(f"STUCK at ({pos_before.x},{pos_before.y})")
        # Opportunistic heal: if action unused, heal nearby damaged building
        if ct.get_action_cooldown() == 0:
            self._opportunistic_heal(ct)
        self._write_marker(ct)

    def _run_policy(self, ct: Controller) -> Turn | None:
        s = self.state
        t = ct.get_cpu_time_elapsed
        for score, task in _policy(s):
            if score <= 0:
                continue
            t0 = t()
            fn = TASK_FNS[task]
            result = fn(s, ct)
            dt = t() - t0
            if result is not None:
                print(f"  {task.name} OK {dt}us")
                return _to_turn(result)
            print(f"  {task.name} FAIL {dt}us")
        print("  IDLE")
        return None

    def _move_or_detour(self, ct: Controller, direction: Direction) -> bool:
        """Try to move. If blocked, 50% chance to detour randomly (paving if needed)."""
        if ct.can_move(direction):
            ct.move(direction)
            return True
        import random

        if random.random() < 0.5:
            # Try walkable tiles first
            dirs = [d for d in Direction if d != Direction.CENTRE and ct.can_move(d)]
            if dirs:
                ct.move(random.choice(dirs))
                return False
            # No walkable tiles — try paving a road in a random direction
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
                self.state.out_target_dirty = True
            case ActionMove(action, direction):
                if isinstance(action, PlaceRoad):
                    if ct.can_move(direction):
                        ct.move(direction)
                    else:
                        execute(action, ct)
                        self.state.out_target_dirty = True
                        self._move_or_detour(ct, direction)
                else:
                    execute(action, ct)
                    self.state.out_target_dirty = True
                    self._move_or_detour(ct, direction)
            case MoveAction(direction, action):
                if self._move_or_detour(ct, direction):
                    execute(action, ct)
                    self.state.out_target_dirty = True

    def _opportunistic_heal(self, ct: Controller) -> None:
        """If we just moved (action unused), heal any damaged friendly building nearby."""
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) != my_team:
                continue
            if ct.get_hp(bid) >= ct.get_max_hp(bid):
                continue
            pos = ct.get_position(bid)
            if ct.can_heal(pos):
                ct.heal(pos)
                return

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


_ROLE_ECON = 0
_ROLE_RUSH = 1
_ROLE_HOME = 2


def _rush_ready(state: State) -> bool:
    core_flow = sum(state.flow.ti[i] for i in state.my_core_tiles)
    return core_flow >= 0.2 and state.en_core_pos is not None


def _policy(state: State) -> list[tuple[float, Task]]:
    seen = sum(1 for e in state.env if e is not None)
    seen_frac = seen / (state.w * state.h)
    explore_score = 95.0 if seen_frac < 0.3 else 55.0 if seen_frac < 0.5 else 20.0
    ready = _rush_ready(state)

    match state.role:
        case 1:  # RUSH — full all-rounder, econ early then siege
            scores: list[tuple[float, Task]] = [
                (999.0, Task.HEAL_CORE),
                (200.0 if ready else 0.0, Task.RUSH),
                (160.0 if ready else 0.0, Task.SCOUT_ENEMY),
                (150.0 if not ready else 0.0, Task.CONNECT_BACK),
                (120.0 if not ready else 0.0, Task.ROAD_HARVESTERS),
                (100.0 if not ready else 0.0, Task.HARVEST_TI),
                (250.0 if ready else 0.0, Task.HEAL_INFRA),
                (explore_score, Task.EXPLORE),
                (15.0, Task.PATROL),
            ]
        case 2:  # HOME — econ + defend harvesters, never goes to enemy half
            n_harv = len(state.my_harvesters)
            # Harvest until 4 harvesters, then patrol takes over
            harvest_score = 100.0 if n_harv < 4 else 20.0
            # Patrol scales: low early, rises with harvesters
            patrol_score = min(20.0 + n_harv * 20.0, 90.0)  # 0→20, 2→60, 3→80, 4→80 cap
            # Explore high early (find ore), drops once harvesters connected
            core_flow = sum(state.flow.ti[i] for i in state.my_core_tiles)
            home_explore = 80.0 if core_flow < 0.4 else 15.0
            scores = [
                (999.0, Task.HEAL_CORE),
                (200.0, Task.HEAL_INFRA),
                (180.0, Task.ROAD_HARVESTERS),
                (150.0, Task.CONNECT_BACK),
                (harvest_score, Task.HARVEST_TI),
                (patrol_score, Task.PATROL),
                (home_explore, Task.EXPLORE),
            ]
        case _:  # ECON — harvest, connect, explore. Never rushes.
            scores = [
                (999.0, Task.HEAL_CORE),
                (150.0, Task.CONNECT_BACK),
                (120.0, Task.ROAD_HARVESTERS),
                (100.0, Task.HARVEST_TI),
                (explore_score, Task.EXPLORE),
                (15.0, Task.PATROL),
            ]

    scores.sort(key=lambda t: t[0], reverse=True)
    return scores
