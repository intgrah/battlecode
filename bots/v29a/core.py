from cambc import Controller, EntityType, Position
from params import SPAWN_INITIAL_CAP, SPAWN_SURPLUS_TURNS, SPAWN_TI_BUFFER
from util import DIRS, SPOKES, toward


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0
        self.spoke_idx = 0
        self.surplus_turns = 0

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
            self.surplus_turns = 0
            return

        pos = ct.get_position()
        my = ct.get_team()

        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            if et in (EntityType.BUILDER_BOT, EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                self._try_spawn_toward(ct, ct.get_position(eid))
                return

        if self.spawned < SPAWN_INITIAL_CAP:
            self._try_spawn(ct)
            return

        threshold = SPAWN_TI_BUFFER + cost * self.spawned
        if ti > threshold:
            self.surplus_turns += 1
        else:
            self.surplus_turns = 0

        if self.surplus_turns >= SPAWN_SURPLUS_TURNS:
            self._try_spawn(ct)
            self.surplus_turns = 0
