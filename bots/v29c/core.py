from cambc import Controller, EntityType, Position
from params import (
    INITIAL_EXPLORERS,
    MAX_BUILDERS,
    RAIDER_SPAWN_INTERVAL_EARLY,
    RAIDER_SPAWN_INTERVAL_LATE,
    RAIDER_SPAWN_ROUND_EARLY,
    RAIDER_SPAWN_ROUND_LATE,
    RAIDER_SPAWN_TI_EARLY,
    RAIDER_SPAWN_TI_LATE,
    SPAWN_TI_BUFFER,
)
from util import DIRS, SPOKES, toward


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0
        self.spoke_idx = 0
        self.last_raider_round = 0
        self.enemy_core: Position | None = None

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

        if self.enemy_core is None:
            w, h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(w - 1 - pos.x, h - 1 - pos.y)

        if self.spawned >= MAX_BUILDERS:
            return

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

        if rnd < 50:
            target = min(INITIAL_EXPLORERS, ti // cost)
            if self.spawned < target:
                self._try_spawn_toward(ct, self.enemy_core)
            return

        raider_interval = RAIDER_SPAWN_INTERVAL_EARLY
        raider_ti = RAIDER_SPAWN_TI_EARLY
        if rnd > RAIDER_SPAWN_ROUND_LATE:
            raider_interval = RAIDER_SPAWN_INTERVAL_LATE
            raider_ti = RAIDER_SPAWN_TI_LATE

        if (
            rnd >= RAIDER_SPAWN_ROUND_EARLY
            and ti > raider_ti
            and rnd - self.last_raider_round >= raider_interval
        ):
            if self._try_spawn_toward(ct, self.enemy_core):
                self.last_raider_round = rnd
                return

        if rnd < 200:
            target = (
                INITIAL_EXPLORERS + (ti - SPAWN_TI_BUFFER) // (cost * 3)
                if ti > SPAWN_TI_BUFFER
                else INITIAL_EXPLORERS
            )
        else:
            target = (
                INITIAL_EXPLORERS + (ti - SPAWN_TI_BUFFER) // (cost * 2)
                if ti > SPAWN_TI_BUFFER
                else INITIAL_EXPLORERS
            )

        target = min(target, MAX_BUILDERS)
        if self.spawned < target:
            self._try_spawn(ct)
