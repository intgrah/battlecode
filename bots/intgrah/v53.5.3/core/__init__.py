from __future__ import annotations

from collections import deque
from random import Random
from typing import Final, override

from cambc import Controller, Direction, EntityType, GameConstants, ResourceType
from config import DEBUG_DUMP
from unit import Unit
from util import DIR4, DIR8
from visualiser import Scalar, emit

__all__ = ["Core"]


class Core(Unit):
    INITIAL_SPAWNS: Final[int] = 6
    INCOME_SAMPLES: Final[int] = 16
    MAX_BUILDERS: Final[int] = 12
    INCOME_HEADROOM: Final[int] = 5
    SURPLUS_BASELINE: Final[int] = 50
    SURPLUS_SCALE_FACTOR: Final[int] = 60
    AX_CONVERT_THRESHOLD: Final[int] = 50
    AX_STOP_CONVERT_ROUND: Final[int] = 1200

    @override
    def __init__(self, ct: Controller) -> None:
        self.w: int = ct.get_map_width()
        self.h: int = ct.get_map_height()
        self.rng = Random(ct.get_id())
        self.spawned: int = 0
        self.deliveries: deque[int] = deque(
            [0] * Core.INCOME_SAMPLES, maxlen=Core.INCOME_SAMPLES
        )
        self.ti_delivered: int = 0
        self.ax_delivered: int = 0

    @override
    def run(self, ct: Controller) -> None:
        ti_in, ax_in = self._count_incoming(ct)
        self.deliveries.appendleft(ti_in)
        self.ti_delivered += ti_in * GameConstants.STACK_SIZE
        self.ax_delivered += ax_in * GameConstants.STACK_SIZE
        income_rate = sum(self.deliveries) / len(self.deliveries)

        self._maybe_convert(ct)

        if self._should_spawn(ct, income_rate):
            self._try_spawn(ct)

        if DEBUG_DUMP:
            self._dump(ct, income_rate)

    def _count_incoming(self, ct: Controller) -> tuple[int, int]:
        pos = ct.get_position()
        ti_count = 0
        ax_count = 0
        for d in DIR8:
            tile = pos.add(d)
            for cd in DIR4:
                src = tile.add(cd)
                if not (0 <= src.x < self.w and 0 <= src.y < self.h):
                    continue
                if not ct.is_in_vision(src):
                    continue
                bid = ct.get_tile_building_id(src)
                if bid is None:
                    continue
                if ct.get_entity_type(bid) != EntityType.CONVEYOR:
                    continue
                if ct.get_direction(bid).opposite() != cd:
                    continue
                res = ct.get_stored_resource(bid)
                if res == ResourceType.TITANIUM:
                    ti_count += 1
                elif res == ResourceType.REFINED_AXIONITE:
                    ax_count += 1
        return ti_count, ax_count

    def _maybe_convert(self, ct: Controller) -> None:
        _, ax = ct.get_global_resources()
        if ax <= 0:
            return
        if ct.get_current_round() > Core.AX_STOP_CONVERT_ROUND:
            return
        excess = ax - Core.AX_CONVERT_THRESHOLD
        if excess >= GameConstants.STACK_SIZE:
            amount = (excess // GameConstants.STACK_SIZE) * GameConstants.STACK_SIZE
            ct.convert(amount)
            self.ax_delivered -= amount

    def _should_spawn(self, ct: Controller, income_rate: float) -> bool:
        rnd = ct.get_current_round()
        ti, _ = ct.get_global_resources()

        if rnd <= 20:
            return self.spawned < Core.INITIAL_SPAWNS

        if rnd <= 40:
            return (
                self.spawned < Core.MAX_BUILDERS
                and income_rate * 4 > self.spawned - Core.INCOME_HEADROOM
            )

        has_income = (
            self.spawned < Core.MAX_BUILDERS
            and income_rate * 4 > self.spawned - Core.INCOME_HEADROOM
        )
        has_surplus = ti > Core.SURPLUS_BASELINE + Core.SURPLUS_SCALE_FACTOR * (
            ct.get_scale_percent() / 100
        )
        return has_income or has_surplus

    def _try_spawn(self, ct: Controller) -> None:
        d: Direction = self.rng.choice(DIR8)
        for _ in range(8):
            sp = ct.get_position().add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.spawned += 1
                return
            d = d.rotate_right()
        if ct.can_spawn(ct.get_position()):
            ct.spawn_builder(ct.get_position())
            self.spawned += 1

    def _dump(self, _ct: Controller, income_rate: float) -> None:
        emit(
            ti_delivered=Scalar(self.ti_delivered),
            ax_delivered=Scalar(self.ax_delivered),
            income=Scalar(income_rate),
            spawned=Scalar(self.spawned),
        )
