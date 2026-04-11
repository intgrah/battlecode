from __future__ import annotations

from typing import TYPE_CHECKING

from builder.algorithms.bfs import update_bfs
from builder.state.role import Role
from builder.state.update.costs import update_costs, update_enemy_turrets
from builder.state.update.econ import (
    update_dangling,
    update_map_econ,
    update_ore_target,
)
from builder.state.update.role import update_role
from builder.state.update.symmetry import update_symmetry
from builder.state.update.vision import update_vision

if TYPE_CHECKING:
    from cambc import Controller

    from builder.state import State


def update(state: State, ct: Controller) -> None:
    t0 = ct.get_cpu_time_elapsed()
    update_vision(state, ct)
    t1 = ct.get_cpu_time_elapsed()
    print(f"  vision={t1 - t0}us")
    update_costs(state, ct)
    t2 = ct.get_cpu_time_elapsed()
    print(f"  costs={t2 - t1}us")
    update_symmetry(state)
    t3 = ct.get_cpu_time_elapsed()
    print(f"  symmetry={t3 - t2}us")
    update_enemy_turrets(state, ct)
    update_bfs(state, *ct.get_position())
    t4 = ct.get_cpu_time_elapsed()
    print(f"  bfs={t4 - t3}us")
    update_role(state, ct)
    t5 = ct.get_cpu_time_elapsed()
    print(f"  role={t5 - t4}us")
    if state.role not in (Role.OFFENSE, Role.PERM_OFFENSE):
        update_map_econ(state, ct)
        t6 = ct.get_cpu_time_elapsed()
        print(f"  econ_map={t6 - t5}us")
        update_dangling(state, ct)
        t7 = ct.get_cpu_time_elapsed()
        print(f"  loose={t7 - t6}us")
        update_ore_target(state, ct)
        t8 = ct.get_cpu_time_elapsed()
        print(f"  ore={t8 - t7}us")
    else:
        t8 = t5
    print(f"update={t8 - t0}us")
