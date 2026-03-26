import json
from collections import deque

from cambc import Controller, EntityType, Position
from util import DIRS, SPOKES, toward

TI_WINDOW = 10


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0
        self.spoke_idx = 0
        self.ti_history: deque[int] = deque(maxlen=TI_WINDOW)
        self.gunners_built = 0
        self.barriers_built = 0
        self.enemy_core: Position | None = None

    def _try_spawn(self, ct: Controller) -> bool:
        pos = ct.get_position()
        spoke = SPOKES[self.spoke_idx % len(SPOKES)]
        for d in [spoke, spoke.rotate_left(), spoke.rotate_right(), *DIRS]:
            sp = pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                self.spoke_idx += 1
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

    def _ensure_enemy_core(self, ct: Controller) -> None:
        if self.enemy_core is None:
            pos = ct.get_position()
            w, h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(w - 1 - pos.x, h - 1 - pos.y)

    def _try_build_gunner(self, ct: Controller) -> bool:
        self._ensure_enemy_core(ct)
        assert self.enemy_core is not None
        facing = ct.get_position().direction_to(self.enemy_core)
        for d in DIRS:
            gp = ct.get_position().add(d)
            for f in [facing, facing.rotate_left(), facing.rotate_right()]:
                if ct.can_build_gunner(gp, f):
                    ct.build_gunner(gp, f)
                    self.gunners_built += 1
                    return True
        return False

    def _try_build_barriers(self, ct: Controller) -> int:
        self._ensure_enemy_core(ct)
        assert self.enemy_core is not None
        pos = ct.get_position()
        built = 0
        for d in DIRS:
            for dist in range(2, 4):
                bp = pos
                for _ in range(dist):
                    bp = bp.add(d)
                if ct.can_build_barrier(bp):
                    ct.build_barrier(bp)
                    built += 1
                    if built >= 3:
                        return built
        return built

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()

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
                if self.gunners_built < 2:
                    self._try_build_gunner(ct)
                    return
                self._try_spawn_toward(ct, ct.get_position(eid))
                return

        if self.spawned == 4 and ct.get_current_round() >= 20:
            self._ensure_enemy_core(ct)
            assert self.enemy_core is not None
            d = ct.get_position().direction_to(self.enemy_core)
            for try_d in [d, d.rotate_left(), d.rotate_right()]:
                sp = ct.get_position().add(try_d)
                if ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return

        if ti < cost:
            return

        if self.spawned < 4:
            if self._try_spawn(ct):
                print(
                    json.dumps(
                        {
                            "_dbg": True,
                            "unit": "core",
                            "action": "spawn_initial",
                            "spawned": self.spawned,
                            "ti": ti,
                        },
                        separators=(",", ":"),
                    ),
                )
            return

        if self.spawned >= 8:
            return

        self.ti_history.append(ti)
        if len(self.ti_history) < TI_WINDOW:
            return

        ti_delta = self.ti_history[-1] - self.ti_history[0]
        if ti_delta > 0 and ti > cost * 5 and self._try_spawn(ct):
            print(
                json.dumps(
                    {
                        "_dbg": True,
                        "unit": "core",
                        "action": "spawn_economy",
                        "spawned": self.spawned,
                        "ti": ti,
                        "ti_delta": ti_delta,
                    },
                    separators=(",", ":"),
                ),
            )
