from cambc import Controller
from util import DIRS, SPOKES


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0
        self.target_spawned = 4
        self.spoke_idx = 0

    def _try_spawn(self, ct: Controller) -> bool:
        """Spawn builders in NESW directions."""
        pos = ct.get_position()
        spoke = SPOKES[self.spoke_idx % len(SPOKES)]
        for d in [spoke, spoke.rotate_left(), spoke.rotate_right(), *DIRS]:
            sp = pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                self.spoke_idx += 2
                return True
        return False

    def run(self, ct: Controller) -> None:
        if self.spawned >= self.target_spawned:
            return
        ti, _ax = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        if cost <= ti:
            self._try_spawn(ct)
