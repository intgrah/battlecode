from __future__ import annotations

from typing import TYPE_CHECKING

from builder.algorithms.bfs import update_bfs
from builder.role import Role
from builder.state_update_econ import update_dangling, update_ore_target
from builder.state_update_role import update_role
from builder.state_update_vision import update_map, update_splittable_locations

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State


def update(state: State, ct: Controller) -> None:
    t0 = ct.get_cpu_time_elapsed()
    update_map(state, ct)
    t1 = ct.get_cpu_time_elapsed()
    print(f"  vision={t1 - t0}us")
    pos = ct.get_position()
    update_bfs(state, pos.x, pos.y)
    t2 = ct.get_cpu_time_elapsed()
    print(f"  bfs={t2 - t1}us")
    update_splittable_locations(state, ct)
    t3 = ct.get_cpu_time_elapsed()
    print(f"  econ_map={t3 - t2}us")
    update_role(state, ct)
    t4 = ct.get_cpu_time_elapsed()
    print(f"  role={t4 - t3}us")
    if state.role != Role.OFFENSE:
        update_dangling(state, ct)
        t5 = ct.get_cpu_time_elapsed()
        print(f"  loose={t5 - t4}us")
        update_ore_target(state, ct)
        t6 = ct.get_cpu_time_elapsed()
        print(f"  ore={t6 - t5}us")
    else:
        t6 = t4
    print(f"update={t6 - t0}us")
