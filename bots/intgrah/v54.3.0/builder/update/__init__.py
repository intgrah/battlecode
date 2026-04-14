from __future__ import annotations

from typing import TYPE_CHECKING

from builder.role import Role

if TYPE_CHECKING:
    from cambc import Controller

    from builder import Builder


def update(self: Builder, ct: Controller) -> None:
    t0 = ct.get_cpu_time_elapsed()
    self.prune_stale(ct)
    t1 = ct.get_cpu_time_elapsed()
    print(f"  prune={t1 - t0}us")
    self.update_vision(ct)
    t2 = ct.get_cpu_time_elapsed()
    print(f"  vision={t2 - t1}us")
    pos = ct.get_position()
    self.update_bfs(pos.x, pos.y)
    t3 = ct.get_cpu_time_elapsed()
    print(f"  bfs={t3 - t2}us")
    self.update_ore_denial(ct)
    t4 = ct.get_cpu_time_elapsed()
    print(f"  ore_deny={t4 - t3}us")
    self.update_enemy_turrets(ct)
    t5 = ct.get_cpu_time_elapsed()
    print(f"  turrets={t5 - t4}us")
    self.update_role(ct)
    t6 = ct.get_cpu_time_elapsed()
    print(f"  role={t6 - t5}us")
    if self.role != Role.OFFENSE:
        self.update_map_econ(ct)
        t7 = ct.get_cpu_time_elapsed()
        print(f"  econ_map={t7 - t6}us")
        self.update_dangling(ct)
        t8 = ct.get_cpu_time_elapsed()
        print(f"  loose={t8 - t7}us")
        self.update_ore_target(ct)
        t9 = ct.get_cpu_time_elapsed()
        print(f"  ore={t9 - t8}us")
    else:
        t9 = t6
    print(f"update={t9 - t0}us")
