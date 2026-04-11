from __future__ import annotations

from collections.abc import Callable

from cambc import Controller, EntityType
from config import DEBUG_DUMP
from unit import Unit
from util import DIR8, can_afford, try_move

from .extra import fix_enemy_conveyor, pave_near_harvesters
from .helpers import try_move_with_road
from .role import Role
from .state import State
from .state_dump import dump
from .state_update import update_economy, update_role
from .state_update_bfs import update_bfs
from .state_update_map import update_econ, update_map
from .task_attack import task_attack
from .task_build_conveyors import route_to_core
from .task_defend import place_gunner_nearby
from .task_explore import task_xplore
from .task_foundry import task_place_foundry, task_place_splitter
from .task_harvest import task_harvest_ti
from .task_heal import run_heal, task_heal
from .task_patrol import run_patrol

__all__ = ["Builder"]

TaskFn = Callable[[State, Controller], bool]


def _connect_close(s: State, ct: Controller) -> bool:
    my_pos = ct.get_position()
    if s.branch_start and my_pos.distance_squared(s.branch_start) <= 2:
        route_to_core(s, ct, s.branch_start)
        return True
    if s.dangling_output and my_pos.distance_squared(s.dangling_output) <= 2:
        route_to_core(s, ct, s.dangling_output)
        return True
    return False


def _connect_far(s: State, ct: Controller) -> bool:
    if s.branch_start:
        route_to_core(s, ct, s.branch_start)
        return True
    if s.dangling_output:
        route_to_core(s, ct, s.dangling_output)
        return True
    return False


def _heal(s: State, ct: Controller) -> bool:
    return run_heal(s, ct) or task_heal(s, ct)


def _patrol_cheap(s: State, ct: Controller) -> bool:
    return (
        s.role == Role.DEFENSE
        and not can_afford(ct, EntityType.HARVESTER)
        and run_patrol(s, ct)
    )


def _splitter(s: State, ct: Controller) -> bool:
    return task_place_splitter(s, ct)


def _foundry(s: State, ct: Controller) -> bool:
    return task_place_foundry(s, ct)


def _harvest(s: State, ct: Controller) -> bool:
    return s.ore_target is not None and task_harvest_ti(s, ct, s.ore_target)


def _patrol_late(s: State, ct: Controller) -> bool:
    return (
        s.role == Role.DEFENSE
        and len(s.adjacent_to_harvester) > 0
        and run_patrol(s, ct)
    )


def _opportunistic_attack(s: State, ct: Controller) -> bool:
    if (
        s.opportunistic
        and s.rng.random() < 0.2
        and ct.get_current_round() > 100
        and ct.can_fire(ct.get_position())
        and ct.get_team(ct.get_tile_building_id(ct.get_position())) != ct.get_team()
    ):
        ct.fire(ct.get_position())
        return True
    return False


def _explore(s: State, ct: Controller) -> bool:
    if ct.get_global_resources()[0] <= 100:
        return False
    task_xplore(s, ct)
    return True


def _wander(s: State, ct: Controller) -> bool:
    dir8 = DIR8[:]
    s.rng.shuffle(dir8)
    my_pos = ct.get_position()
    for d in dir8:
        if try_move(ct, my_pos.add(d)):
            return True
    return any(try_move_with_road(ct, my_pos.add(d), s) for d in dir8)


def _attack(s: State, ct: Controller) -> bool:
    task_attack(s, ct)
    return True


OFFENSE_TASKS: list[TaskFn] = [
    _heal,
    _attack,
]

ECON_TASKS: list[TaskFn] = [
    place_gunner_nearby,
    fix_enemy_conveyor,
    pave_near_harvesters,
    _splitter,
    _foundry,
    _connect_close,
    _heal,
    _connect_far,
    _harvest,
    _opportunistic_attack,
    _explore,
    _wander,
]

DEFENSE_TASKS: list[TaskFn] = [
    place_gunner_nearby,
    fix_enemy_conveyor,
    pave_near_harvesters,
    _connect_close,
    _heal,
    _connect_far,
    _patrol_cheap,
    _harvest,
    _patrol_late,
    _opportunistic_attack,
    _explore,
    _wander,
]

POLICIES: dict[Role, list[TaskFn]] = {
    Role.OFFENSE: OFFENSE_TASKS,
    Role.PERM_OFFENSE: OFFENSE_TASKS,
    Role.ECON: ECON_TASKS,
    Role.PERM_ECON: ECON_TASKS,
    Role.DEFENSE: DEFENSE_TASKS,
    Role.PERM_DEFENSE: DEFENSE_TASKS,
}


class Builder(Unit):
    def __init__(self, ct: Controller) -> None:
        self.state: State = State(ct)

    def run(self, ct: Controller) -> None:
        s = self.state
        pos = ct.get_position()
        t0 = ct.get_cpu_time_elapsed()
        update_map(s, ct)
        t1 = ct.get_cpu_time_elapsed()
        print(f"  map={t1 - t0}us")
        update_bfs(s, pos.x, pos.y)
        t2 = ct.get_cpu_time_elapsed()
        print(f"  bfs={t2 - t1}us")
        update_econ(s, ct)
        t3 = ct.get_cpu_time_elapsed()
        print(f"  econ_map={t3 - t2}us")
        update_role(s, ct)
        t4 = ct.get_cpu_time_elapsed()
        print(f"  role={t4 - t3}us")
        print(f"update={t4 - t0}us")

        if DEBUG_DUMP:
            dump(s, ct)

        if s.role not in (Role.OFFENSE, Role.PERM_OFFENSE):
            update_economy(s, ct)
            t5 = ct.get_cpu_time_elapsed()
            print(f"  econ={t5 - t4}us")
        else:
            t5 = t4

        assert s.role is not None
        chosen = "none"
        for task in POLICIES[s.role]:
            if task(s, ct):
                chosen = task.__name__
                break

        if s.role not in (Role.OFFENSE, Role.PERM_OFFENSE):
            _end_of_turn_heal(ct)

        t6 = ct.get_cpu_time_elapsed()
        print(f"task={t6 - t5}us [{chosen}]")
        print(f"total={t6 - t0}us")


def _end_of_turn_heal(ct: Controller) -> None:
    my_pos = ct.get_position()
    nearby_units = [
        unit
        for unit in ct.get_nearby_units()
        if (ct.get_position(unit).distance_squared(my_pos) <= 2)
        or (ct.get_entity_type(unit) == EntityType.CORE)
    ]

    current_position = ct.get_position()
    if ct.can_heal(current_position) and ct.get_hp() < ct.get_max_hp():
        ct.heal(current_position)
    for unit in nearby_units:
        if ct.get_entity_type(unit) == EntityType.CORE:
            core_center = ct.get_position(unit)
            for d in DIR8:
                heal_pos = core_center.add(d)
                if (
                    ct.can_heal(heal_pos)
                    and ct.get_team(unit) == ct.get_team()
                    and ct.get_hp(unit) < ct.get_max_hp(unit)
                ):
                    ct.heal(heal_pos)

        if (
            ct.can_heal(ct.get_position(unit))
            and ct.get_team(unit) == ct.get_team()
            and ct.get_hp(unit) < ct.get_max_hp(unit)
        ):
            ct.heal(ct.get_position(unit))
