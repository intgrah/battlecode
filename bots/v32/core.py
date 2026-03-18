from collections import deque

from cambc import Controller, EntityType, Position
from util import DIRS, SPOKES, toward

TI_WINDOW = 10


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0
        self.spoke_idx = 0
        self.ti_history: deque[int] = deque(maxlen=TI_WINDOW)

    def _try_spawn(self, ct: Controller) -> bool:
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

    def _try_spawn_toward(self, ct: Controller, target_pos: Position) -> bool:
        pos = ct.get_position()
        d = toward(pos, target_pos)
        for try_d in [d, d.rotate_left(), d.rotate_right(), *DIRS]:
            sp = pos.add(try_d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                return True
        return False

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()

        if ti < cost:
            return

        my = ct.get_team()
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            if et in (
                EntityType.BUILDER_BOT,
                EntityType.GUNNER,
                EntityType.SENTINEL,
                EntityType.BREACH,
            ):
                self._try_spawn_toward(ct, ct.get_position(eid))
                return

        if self.spawned < 4:
            self._try_spawn(ct)
            return

        if self.spawned >= 8:
            return

        self.ti_history.append(ti)
        if len(self.ti_history) < TI_WINDOW:
            return

        ti_delta = self.ti_history[-1] - self.ti_history[0]
        if ti_delta > 0 and ti > cost * 5:
            self._try_spawn(ct)
