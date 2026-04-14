from __future__ import annotations

from typing import TYPE_CHECKING

from builder.algorithms.bfs import update_bfs
from builder.role import Role
from builder.update.econ import (
    update_dangling,
    update_map_econ,
    update_ore_target,
)
from builder.update.prune import prune_stale
from builder.update.role import update_role
from builder.update.turrets import update_enemy_turrets, update_ore_denial
from builder.update.vision import update_vision

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def update(self: Builder, ct: Controller) -> None:
    t0 = ct.get_cpu_time_elapsed()
    prune_stale(self, ct)
    t1 = ct.get_cpu_time_elapsed()
    print(f"  prune={t1 - t0}us")
    update_vision(self, ct)
    t2 = ct.get_cpu_time_elapsed()
    print(f"  vision={t2 - t1}us")
    pos = ct.get_position()
    update_bfs(self, pos.x, pos.y)
    t3 = ct.get_cpu_time_elapsed()
    print(f"  bfs={t3 - t2}us")
    update_ore_denial(self, ct)
    t4 = ct.get_cpu_time_elapsed()
    print(f"  ore_deny={t4 - t3}us")
    update_enemy_turrets(self, ct)
    t5 = ct.get_cpu_time_elapsed()
    print(f"  turrets={t5 - t4}us")
    update_role(self, ct)
    t6 = ct.get_cpu_time_elapsed()
    print(f"  role={t6 - t5}us")
    if self.role != Role.OFFENSE:
        update_map_econ(self, ct)
        t7 = ct.get_cpu_time_elapsed()
        print(f"  econ_map={t7 - t6}us")
        update_dangling(self, ct)
        t8 = ct.get_cpu_time_elapsed()
        print(f"  loose={t8 - t7}us")
        update_ore_target(self, ct)
        t9 = ct.get_cpu_time_elapsed()
        print(f"  ore={t9 - t8}us")
    else:
        t9 = t6
    print(f"update={t9 - t0}us")
