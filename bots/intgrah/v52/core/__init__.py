from __future__ import annotations

from collections import deque
from typing import Final, override

from cambc import Controller, Direction, EntityType, ResourceType
from unit import StationaryUnit
from util import DIR4, DIR8

__all__ = ["Core"]


class Core(StationaryUnit):
    INITIAL_SPAWNS = 6
    INCOME_SAMPLES = 16
    MAX_BUILDERS = 15
    INCOME_HEADROOM = 5
    SURPLUS_BASELINE = 50
    SURPLUS_SCALE_FACTOR = 60

    @override
    def __init__(self, ct: Controller) -> None:
        super().__init__(ct)
        self.spawned: int = 0
        self.deliveries: Final[deque[int]] = deque(
            [0] * Core.INCOME_SAMPLES, maxlen=Core.INCOME_SAMPLES
        )

    @override
    def run(self, ct: Controller) -> None:
        self.deliveries.appendleft(self._count_incoming(ct))
        income_rate = sum(self.deliveries) / len(self.deliveries)

        if self.should_spawn(ct, income_rate):
            self.try_spawn(ct)

    def _count_incoming(self, ct: Controller) -> int:
        count = 0
        for d in DIR8:
            tile = self.my_pos.add(d)
            for cd in DIR4:
                src = tile.add(cd)
                if self.in_bounds(src) and ct.is_in_vision(src):
                    bid = ct.get_tile_building_id(src)
                    if (
                        bid is not None
                        and ct.get_entity_type(bid) == EntityType.CONVEYOR
                        and ct.get_direction(bid).opposite() == cd
                        and ct.get_stored_resource(bid) == ResourceType.TITANIUM
                    ):
                        count += 1
        return count

    def should_spawn(self, ct: Controller, income_rate: float) -> bool:
        if self.spawned < Core.INITIAL_SPAWNS:
            return True
        if self.spawned >= Core.MAX_BUILDERS:
            return False
        rnd = ct.get_current_round()
        ti, _ = ct.get_global_resources()
        has_income = income_rate * 4 > self.spawned - Core.INCOME_HEADROOM
        has_surplus = ti > Core.SURPLUS_BASELINE + Core.SURPLUS_SCALE_FACTOR * (
            ct.get_scale_percent() / 100
        )
        return (rnd > 24 and has_income) or (rnd > 48 and has_surplus)

    def try_spawn(self, ct: Controller) -> None:
        dir9 = [*DIR8, Direction.CENTRE]
        self.rng.shuffle(dir9)
        for d in dir9:
            sp = self.my_pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                return
