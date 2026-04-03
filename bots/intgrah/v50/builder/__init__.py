from collections.abc import Callable

from action import (
    ActionMove,
    ActionOnly,
    MoveAction,
    MoveOnly,
    Turn,
    Wait,
    can_execute,
    execute,
)
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from config import DEBUG_DUMP, OPENING, OpeningMode
from marker import MarkerRole
from unit import Unit

from .role import ROLE_TARGET_TOTAL, ROLE_TARGETS, Role
from .state import State
from .state_dump import dump
from .state_update import update as state_update
from .task import Task
from .task_barrier_harvester import barrier_harvester
from .task_barrier_ore import barrier_ore
from .task_connect_excess import ExcessKind, SearchKind, connect_excess
from .task_explore import explore
from .task_fire_enemy_transport import fire_enemy_transport
from .task_harvest_ax import harvest_ax
from .task_harvest_ti import harvest_ti
from .task_heal_core import heal_core
from .task_heal_econ import heal_econ
from .task_heal_turret import heal_turret
from .task_patrol import patrol
from .task_place_launcher import place_launcher
from .task_place_sentinel import place_sentinel

type TaskFn = Callable[[State, Controller], Turn | None]

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
    Task.HEAL_ECON: heal_econ,
    Task.BARRIER_HARVESTER: barrier_harvester,
}


class Builder(Unit):
    @staticmethod
    def find_core(ct: Controller) -> Position:
        my = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my and ct.get_entity_type(bid) == EntityType.CORE:
                return ct.get_position(bid)
        raise RuntimeError

    def __init__(self, ct: Controller) -> None:
        core_pos = Builder.find_core(ct)
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
            self.run_script(ct)
            if OPENING == OpeningMode.OPENING_ONLY:
                return
            if not self._off_script:
                return

        turn = self.run_policy(ct)
        t2 = ct.get_cpu_time_elapsed()
        print(f"policy={t2 - t1}us total={t2 - t0}us")
        if turn is not None:
            self.execute_turn(ct, turn)

    def run_script(self, ct: Controller) -> None:
        compiled = self.state.compiled
        assert compiled is not None
        if self._script_idx >= len(compiled):
            self._off_script = True
            return

        turn = compiled[self._script_idx]
        self._script_idx += 1
        pos = ct.get_position()

        match turn:
            case Wait():
                pass
            case ActionOnly(action):
                execute(action, ct)
            case MoveOnly(move):
                if ct.can_move(move):
                    ct.move(move)
                else:
                    ct.draw_indicator_dot(pos, 255, 0, 0)
                    self._off_script = True
            case ActionMove(action, move):
                execute(action, ct)
                if ct.can_move(move):
                    ct.move(move)
                else:
                    ct.draw_indicator_dot(pos, 255, 0, 0)
                    self._off_script = True
            case MoveAction(move, action):
                if ct.can_move(move):
                    ct.move(move)
                else:
                    ct.draw_indicator_dot(pos, 255, 0, 0)
                    self._off_script = True
                    return
                execute(action, ct)

        if self._script_idx >= len(compiled):
            ct.draw_indicator_dot(ct.get_position(), 0, 255, 0)
            self._off_script = True

    def run_policy(self, ct: Controller) -> Turn | None:
        s = self.state
        for score, task, transition in POLICIES[s.role]:
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
                if transition is None:
                    s.role = self.rebalance()
                else:
                    s.role = transition
                return result
            print(f"  task={task.name} {elapsed}us FAIL")
        print("  task=NONE")
        return None

    def rebalance(self) -> Role:
        """Pick the role with the largest deficit from the target ratio."""
        s = self.state
        counts: dict[Role, int] = dict.fromkeys(Role, 0)
        for role, _turn in s.role_census.values():
            counts[role] += 1
        total = sum(counts.values()) or 1
        best_role = s.role
        best_deficit = -999.0
        for role, target_weight in ROLE_TARGETS.items():
            deficit = target_weight / ROLE_TARGET_TOTAL - counts[role] / total
            if deficit > best_deficit:
                best_deficit = deficit
                best_role = role
        return best_role

    def execute_turn(self, ct: Controller, turn: Turn) -> None:
        match turn:
            case Wait():
                pass
            case ActionOnly(action):
                execute(action, ct)
            case MoveOnly(move):
                self._move_or_detour(ct, move)
            case ActionMove(action, move):
                execute(action, ct)
                self._move_or_detour(ct, move)
            case MoveAction(move, action):
                if self._move_or_detour(ct, move) and can_execute(action, ct):
                    execute(action, ct)

        self.write_marker(ct)

    def _move_or_detour(self, ct: Controller, move: Direction) -> bool:
        if ct.can_move(move):
            ct.move(move)
            return True
        rng = self.state.rng
        if rng.random() < 0.5:
            dirs = [d for d in Direction if d != Direction.CENTRE and ct.can_move(d)]
            if dirs:
                ct.move(dirs[rng.randrange(len(dirs))])
        return False

    def write_marker(self, ct: Controller) -> None:
        s = self.state
        marker_val = MarkerRole(
            role=s.role.value,
            birthday=s.birthday,
            turn=ct.get_current_round(),
        ).encode()
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


POLICIES: dict[Role, list[tuple[float, Task, Role | None]]] = {
    Role.ECON: [
        (999.0, Task.HEAL_CORE, Role.DEFENSE),
        (200.0, Task.HEAL_ECON, Role.ECON),
        (150.0, Task.CONNECT_EXCESS_TI, Role.ECON),
        (100.0, Task.HARVEST_TI, Role.ECON),
        (75.0, Task.BARRIER_HARVESTER, Role.ECON),
        (50.0, Task.EXPLORE, Role.ECON),
        (20.0, Task.PATROL, None),
    ],
    Role.DEFENSE: [
        (999.0, Task.HEAL_CORE, Role.DEFENSE),
        (200.0, Task.HEAL_ECON, Role.DEFENSE),
        (200.0, Task.HEAL_TURRET, Role.DEFENSE),
        (150.0, Task.BARRIER_HARVESTER, Role.DEFENSE),
        (80.0, Task.BARRIER_ORE, Role.DEFENSE),
        (50.0, Task.PATROL, None),
    ],
    Role.OFFENSE: [
        (999.0, Task.HEAL_CORE, Role.DEFENSE),
        (200.0, Task.FIRE_ENEMY_TRANSPORT, Role.OFFENSE),
        (150.0, Task.PLACE_LAUNCHER, Role.OFFENSE),
        (100.0, Task.PLACE_SENTINEL, Role.OFFENSE),
        (50.0, Task.EXPLORE, Role.ECON),
        (20.0, Task.PATROL, None),
    ],
}
