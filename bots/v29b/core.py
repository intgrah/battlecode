from cambc import Controller, EntityType, Position
from params import INITIAL_BUILDERS, MAX_ECON_BUILDERS, SPAWN_TI_BUFFER
from util import DIRS, SPOKES, toward


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0
        self.spoke_idx = 0

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

        pos = ct.get_position()
        my = ct.get_team()
        rnd = ct.get_current_round()

        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            if et in (EntityType.BUILDER_BOT, EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                self._try_spawn_toward(ct, ct.get_position(eid))
                return

        if rnd <= 50:
            target = min(INITIAL_BUILDERS, ti // cost)
        elif ti > SPAWN_TI_BUFFER:
            surplus_builders = (ti - SPAWN_TI_BUFFER) // (cost * 3)
            target = min(MAX_ECON_BUILDERS, INITIAL_BUILDERS + surplus_builders)
        else:
            target = INITIAL_BUILDERS

        if self.spawned < target and ti >= cost + SPAWN_TI_BUFFER:
            self._try_spawn(ct)
