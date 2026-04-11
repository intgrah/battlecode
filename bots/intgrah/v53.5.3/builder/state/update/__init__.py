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
from builder.state.update.vision import prune_stale, update_vision

if TYPE_CHECKING:
    from cambc import Controller

    from builder.state import State


def update(state: State, ct: Controller) -> None:
    t0 = ct.get_cpu_time_elapsed()
    prune_stale(state, ct)
    t1 = ct.get_cpu_time_elapsed()
    print(f"  prune={t1 - t0}us")
    update_vision(state, ct)
    t2 = ct.get_cpu_time_elapsed()
    print(f"  vision={t2 - t1}us")
    update_costs(state, ct)
    t3 = ct.get_cpu_time_elapsed()
    print(f"  costs={t3 - t2}us")
    update_symmetry(state, ct)
    t4 = ct.get_cpu_time_elapsed()
    print(f"  symmetry={t4 - t3}us")
    update_enemy_turrets(state, ct)
    t5 = ct.get_cpu_time_elapsed()
    print(f"  turrets={t5 - t4}us")
    pos = ct.get_position()
    update_bfs(state, pos.x, pos.y)
    t6 = ct.get_cpu_time_elapsed()
    print(f"  bfs={t6 - t5}us")
    update_role(state, ct)
    t7 = ct.get_cpu_time_elapsed()
    print(f"  role={t7 - t6}us")
    if state.role not in (Role.OFFENSE, Role.PERM_OFFENSE):
        update_map_econ(state, ct)
        t8 = ct.get_cpu_time_elapsed()
        print(f"  econ_map={t8 - t7}us")
        update_dangling(state, ct)
        t9 = ct.get_cpu_time_elapsed()
        print(f"  loose={t9 - t8}us")
        update_ore_target(state, ct)
        t10 = ct.get_cpu_time_elapsed()
        print(f"  ore={t10 - t9}us")
    else:
        t10 = t7
    print(f"update={t10 - t0}us")
