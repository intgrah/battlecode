from __future__ import annotations

from collections import deque
from typing import Final, override

from cambc import Controller, Direction, EntityType, ResourceType
from unit import Unit
from util import DIR4, DIR8

__all__ = ["Core"]


class Core(Unit):
    INITIAL_SPAWNS: Final[int] = 6
    INCOME_SAMPLES: Final[int] = 16
    MAX_TEAM_UNITS: Final[int] = 40
    """
    Cap on total team unit count (builders + turrets + core). Team max
    is 50 — 40 leaves real headroom for turret builds while preventing
    runaway spawning. Replaces the old monotonic `self.spawned <
    _MAX_BUILDERS` check, which never reset when builders died: once
    12 had ever been spawned, the core stopped spawning even if all
    of them got killed and we were sitting on a huge Ti surplus.
    """
    INCOME_HEADROOM: Final[int] = 5
    SURPLUS_BASELINE: Final[int] = 50
    SURPLUS_SCALE_FACTOR: Final[int] = 60

    @override
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.spawned: int = 0
        self.deliveries: deque[int] = deque(
            [0] * Core.INCOME_SAMPLES,
            maxlen=Core.INCOME_SAMPLES,
        )

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        self.deliveries.appendleft(self._count_incoming(ct))
        income_rate = sum(self.deliveries) / len(self.deliveries)

        if self._should_spawn(ct, income_rate):
            self._try_spawn(ct)

    def _count_incoming(self, ct: Controller) -> int:
        count = 0
        for d in DIR8:
            tile = self.my_pos.add(d)
            for cd in DIR4:
                src = tile.add(cd)
                if not (0 <= src.x < self.w and 0 <= src.y < self.h):
                    continue
                if not ct.is_in_vision(src):
                    continue
                bid = ct.get_tile_building_id(src)
                if (
                    bid is not None
                    and ct.get_entity_type(bid) == EntityType.CONVEYOR
                    and ct.get_direction(bid).opposite() == cd
                    and ct.get_stored_resource(bid) == ResourceType.TITANIUM
                ):
                    count += 1
        return count

    def _should_spawn(self, ct: Controller, income_rate: float) -> bool:
        if self.spawned < Core.INITIAL_SPAWNS:
            return True
        # Live unit count (includes core, builders, turrets). When
        # builders die the count drops and spawning resumes.
        live_units = ct.get_unit_count()
        if live_units >= Core.MAX_TEAM_UNITS:
            return False
        rnd = ct.get_current_round()
        ti, _ = ct.get_global_resources()
        # Scale income requirement against live units, not cumulative
        # spawns — otherwise a decimated team requires production for
        # ghosts that died 500 rounds ago and never refills.
        has_income = income_rate * 4 > live_units - Core.INCOME_HEADROOM
        has_surplus = ti > Core.SURPLUS_BASELINE + Core.SURPLUS_SCALE_FACTOR * (
            ct.get_scale_percent() / 100
        )
        return (rnd > 20 and has_income) or (rnd > 40 and has_surplus)

    def _try_spawn(self, ct: Controller) -> None:
        d: Direction = self.rng.choice(DIR8)
        for _ in range(8):
            sp = self.my_pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                return
            d = d.rotate_right()
        if ct.can_spawn(self.my_pos):
            ct.spawn_builder(self.my_pos)
            self.spawned += 1
