from __future__ import annotations

from collections import deque
from math import ceil
from typing import Final, override

from cambc import Controller, Direction, EntityType, Position, ResourceType
from config import HARDCODE
from hardcode.identify import identify_map
from unit import CoreAwareUnit
from util.directions import DIR4, DIR8

_CORNERS: Final = (
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
)

__all__ = ["Core"]


class Core(CoreAwareUnit):
    INITIAL_SPAWNS: Final[int] = 4
    INCOME_SAMPLES: Final[int] = 16
    INCOME_HEADROOM: Final[int] = 5
    SURPLUS_BASELINE: Final[int] = 50
    SURPLUS_SCALE_FACTOR: Final[int] = 60
    CONVERSION_TI_THRESHOLD: Final[int] = 200
    """Convert Ax to Ti only when Ti is less than this."""
    CONVERSION_AX_THRESHOLD: Final[int] = 60
    """Convert Ax to Ti only when Ax is more than this."""

    @override
    def __init__(self) -> None:
        super().__init__()
        self.spawned: int = 0
        self.deliveries: deque[int] = deque(
            [0] * Core.INCOME_SAMPLES,
            maxlen=Core.INCOME_SAMPLES,
        )

    max_team_units: int
    """Cap on total team unit count (builders + turrets + core). Scales
    linearly with map size: 18 on a 20x20 map up to 36 on a 50x50 map.
    Team max is 50 overall, so the remainder leaves headroom for turret
    builds while preventing runaway spawning."""

    @override
    def _resolve_my_core(self, ct: Controller) -> Position:
        return ct.get_position()

    @override
    def post_init(self, ct: Controller) -> None:
        super().post_init(ct)
        self.known_map = (
            identify_map(self.w, self.h, self.my_core) if HARDCODE else None
        )
        # Linear interpolation on map area: 400 -> 18 units, 2500 -> 36.
        area = self.w * self.h
        self.max_team_units = round(
            18 + (36 - 18) * (area - 20 * 20) / (50 * 50 - 20 * 20),
        )

    @override
    def run(self, ct: Controller) -> None:
        super().run(ct)
        self.deliveries.appendleft(self._count_incoming(ct))
        income_rate = sum(self.deliveries) / len(self.deliveries)

        self._maybe_convert(ct)

        if self._should_spawn(ct, income_rate):
            self._try_spawn(ct)

    def _maybe_convert(self, ct: Controller) -> None:
        need = Core.CONVERSION_TI_THRESHOLD - self.ti
        surplus_ax = self.ax - Core.CONVERSION_AX_THRESHOLD
        if need > 0 and surplus_ax > 0:
            amount = min(surplus_ax, ceil(need / 4))
            ct.convert(amount)

    def _count_incoming(self, ct: Controller) -> int:
        count = 0
        for d in DIR8:
            tile = self.my_pos.add(d)
            for cd in DIR4:
                src = tile.add(cd)
                if not self.in_bounds(src):
                    continue
                bid = ct.get_tile_building_id(src)
                if (
                    bid is not None
                    and ct.get_entity_type(bid)
                    in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR)
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
        if live_units >= self.max_team_units:
            return False
        # Scale income requirement against live units, not cumulative
        # spawns — otherwise a decimated team requires production for
        # ghosts that died 500 rounds ago and never refills.
        has_income = income_rate * 4 > live_units - Core.INCOME_HEADROOM
        has_surplus = self.ti > Core.SURPLUS_BASELINE + Core.SURPLUS_SCALE_FACTOR * (
            ct.get_scale_percent() / 100
        )
        return (self.round > 20 and has_income) or (self.round > 40 and has_surplus)

    def _try_spawn(self, ct: Controller) -> None:
        # Initial spawns: each of the 4 spawns goes to a distinct corner
        # of the 3x3 core block. Sorted nearest-to-farthest from the
        # (guessed) enemy core, so spawn 0 -> toward enemy, 1 & 2 ->
        # perpendiculars, 3 -> away. If the indexed corner is blocked
        # (e.g., a builder hasn't moved off yet), fall back to any
        # other still-empty corner before giving up the turn.
        if self.spawned < Core.INITIAL_SPAWNS:
            en_core = self.en_core_guess
            corners = sorted(
                (self.my_pos.add(d) for d in _CORNERS),
                key=en_core.distance_squared,
            )
            preferred = corners[self.spawned]
            if ct.can_spawn(preferred):
                ct.spawn_builder(preferred)
                self.spawned += 1
                return
            for sp in corners:
                if sp != preferred and ct.can_spawn(sp):
                    ct.spawn_builder(sp)
                    self.spawned += 1
                    return
            return
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
