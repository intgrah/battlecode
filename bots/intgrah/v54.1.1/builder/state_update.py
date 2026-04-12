from __future__ import annotations

from typing import TYPE_CHECKING

from .role import Role
from .state_update_econ import update_dangling, update_ore_target
from .state_update_role import update_role
from .state_update_vision import update_map, update_splittable_locations

if TYPE_CHECKING:
    from cambc import Controller

    from .state import State


def update(state: State, ct: Controller) -> None:
    t0 = ct.get_cpu_time_elapsed()
    update_map(state, ct)
    t1 = ct.get_cpu_time_elapsed()
    print(f"  vision={t1 - t0}us")
    update_splittable_locations(state, ct)
    t2 = ct.get_cpu_time_elapsed()
    print(f"  econ_map={t2 - t1}us")
    update_role(state, ct)
    t3 = ct.get_cpu_time_elapsed()
    print(f"  role={t3 - t2}us")
    if state.role != Role.OFFENSE:
        update_dangling(state, ct)
        t4 = ct.get_cpu_time_elapsed()
        print(f"  loose={t4 - t3}us")
        update_ore_target(state, ct)
        t5 = ct.get_cpu_time_elapsed()
        print(f"  ore={t5 - t4}us")
    else:
        t5 = t3
    print(f"update={t5 - t0}us")
