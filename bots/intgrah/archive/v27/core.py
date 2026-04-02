from cambc import Controller, EntityType, Position
from util import DIRS, SPOKES, toward

NUM_INITIAL = 4
RAID_START = 200
IDLE_BEFORE_RAID = 60


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()[0]
        rnd = ct.get_current_round()
        core_pos = ct.get_position()
        my = ct.get_team()

        enemy_threat: Position | None = None
        enemy_builder_nearby = False
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my:
                continue
            et = ct.get_entity_type(eid)
            ep = ct.get_position(eid)
            dist = core_pos.distance_squared(ep)
            if (
                et in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH)
                and dist <= 36
            ):
                if enemy_threat is None or dist < core_pos.distance_squared(
                    enemy_threat,
                ):
                    enemy_threat = ep
            elif et == EntityType.HARVESTER and dist <= 25:
                if enemy_threat is None:
                    enemy_threat = ep
            elif et == EntityType.BUILDER_BOT and dist <= 36:
                enemy_builder_nearby = True

        if enemy_threat and ti >= cost:
            spawn_dir = toward(core_pos, enemy_threat)
            for d in [
                spawn_dir,
                spawn_dir.rotate_left(),
                spawn_dir.rotate_right(),
                *DIRS,
            ]:
                sp = core_pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return

        if enemy_builder_nearby and ti >= cost and self.spawned < NUM_INITIAL:
            for d in DIRS:
                sp = core_pos.add(d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return
            return

        if self.spawned < NUM_INITIAL:
            if ti < cost + ct.get_harvester_cost()[0]:
                return
        elif rnd < RAID_START or ti < 500:
            return

        spoke = self.spawned % len(SPOKES)
        sd = SPOKES[spoke]
        for d in [sd, sd.rotate_left(), sd.rotate_right(), *DIRS]:
            sp = core_pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                return
