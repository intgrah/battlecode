from __future__ import annotations

from collections import deque
from math import ceil
from typing import Final, override

from cambc import Controller, Direction, EntityType, Position, ResourceType
from config import HARDCODE
from hardcode.identify import identify_map
from unit import CoreAwareUnit
from util.debug import Scope
from util.directions import DIR4, DIR8

from core.spawn_tempo import compute_spawn_tempo

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
    INCOME_PER_UNIT: Final[float] = 0.65
    """Each live unit demands at least this much expected income per
    round (x4 for the actual harvest cadence) before another spawn is
    allowed. Setting this above 0.25 (a single harvester's contribution)
    means new spawns require strictly growing income — at equilibrium
    no further spawns happen, so constant-income games don't bleed Ti
    into builders that contribute nothing extra."""
    INCOME_QUADRATIC_TERM: Final[float] = 0.04
    """Quadratic kicker on the income gate: required income grows as
    `INCOME_PER_UNIT * N + INCOME_QUADRATIC_TERM * N²`. Mild at small
    N (4 builders ≈ +27% over linear, 8 ≈ +53%, 16 ≈ +106%) so early
    growth still works, but the marginal income demanded by builder
    N grows with N — captures the diminishing-return nature of late
    builders (longer chains, distant ores, more competition for sites)."""
    SURPLUS_BASELINE: Final[int] = 40
    SURPLUS_SCALE_FACTOR: Final[int] = 50
    TRICKLE_COST_MULTIPLIER: Final[float] = 8.0
    """Banked Ti above `TRICKLE_COST_MULTIPLIER * current builder cost`
    triggers a slow trickle-spawn gate regardless of income / standard
    surplus. We're rich enough to spend ~10 builders' worth and still
    have a builder left over. The threshold tracks scaling, so late-game
    expensive builders raise the bar automatically."""
    TRICKLE_MIN_INTERVAL: Final[int] = 40
    """Minimum rounds between trickle-spawns. Keeps the trickle slow."""
    CROWDING_LIMIT: Final[int] = 3
    """Maximum friendly builders allowed in core's vision before
    spawning is refused. If more than this are crowding the core, they're
    likely stuck (route blocked, can't find work, etc.) — adding more
    builders won't help. Save the Ti for buildings instead."""
    CONVERSION_TI_THRESHOLD: Final[int] = 200
    """Convert Ax to Ti only when Ti is less than this."""
    CONVERSION_AX_THRESHOLD: Final[int] = 2
    """Convert Ax to Ti only when Ax is more than this.
    A lot of bots try and save 1 Ax, so we save 2 Ax, just in case.
    """

    @override
    def __init__(self) -> None:
        super().__init__()
        self.spawned: int = 0
        self.last_spawn_round: int = 0
        self.deliveries: deque[int] = deque(
            [0] * Core.INCOME_SAMPLES,
            maxlen=Core.INCOME_SAMPLES,
        )

    max_team_units: int
    """Cap on total team unit count (builders + turrets + core). Scales
    linearly with map size: 18 on a 20x20 map up to 36 on a 50x50 map.
    Team max is 50 overall, so the remainder leaves headroom for turret
    builds while preventing runaway spawning."""

    spawn_tempo: float
    """Map-specific spawn-rate multiplier in [~0.7, ~1.3]. Computed at
    `post_init` from features the Core can see (eccentricity, local
    wall density inner/outer, cardinal exits, nearest Ti ore, nearest
    wall, edge distance). Higher tempo = looser income/surplus gates,
    so we spawn earlier and more often.

    Coefficients were obtained by fitting a linear regression model
    against hand-rated maps (1-5 scale, "how many builders should this
    map spawn"). The fitted rating is then folded through
    `tempo = 1.0 + (rating - 3.0) * 0.15` to keep the multiplier near
    1.0 for an average map. See `core/spawn_tempo.py`."""

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
        with Scope("spawn_tempo", time=True):
            self.spawn_tempo = compute_spawn_tempo(self, ct)

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
        # Threat gate: enemy builders outnumber the friendlies we can
        # see near the core. Spawn ASAP regardless of income / surplus
        # / crowding — a decimated defence is worse than a crowded one.
        if len(self.enemy_bots) > len(self.friendly_bots):
            return True
        # Crowding gate: too many friendly builders in our vision means
        # they're stuck near the core (blocked routes, no reachable
        # work). Adding more won't help — they'd just join the pile.
        if len(self.friendly_bots) > Core.CROWDING_LIMIT:
            return False
        # Scale income requirement against live units, not cumulative
        # spawns — otherwise a decimated team requires production for
        # ghosts that died 500 rounds ago and never refills.
        # Spawn-tempo modulates the gates in two opposite directions:
        # - Income gate: divided by tempo. High tempo loosens (spawn at
        #   lower income), low tempo tightens (require more income).
        # - Surplus gate: multiplied by (2 - tempo). High tempo loosens
        #   (spend banked Ti freely on more builders); low tempo
        #   tightens (hoard Ti for buildings — sparse maps spend better
        #   on infrastructure than on builders that have nothing to do).
        # Linear share + small quadratic kicker — diminishing returns
        # for the Nth builder, without making the cap intractable.
        income_threshold = (
            Core.INCOME_PER_UNIT * live_units
            + Core.INCOME_QUADRATIC_TERM * live_units * live_units
        ) / self.spawn_tempo
        has_income = income_rate * 4 > income_threshold
        has_surplus = self.ti > (
            Core.SURPLUS_BASELINE
            + Core.SURPLUS_SCALE_FACTOR * (ct.get_scale_percent() / 100)
        ) * (2.0 - self.spawn_tempo)
        builder_ti_cost = ct.get_builder_bot_cost()[0]
        has_trickle = (
            self.ti > builder_ti_cost * Core.TRICKLE_COST_MULTIPLIER
            and self.round - self.last_spawn_round > Core.TRICKLE_MIN_INTERVAL
        )
        return (
            (self.round > 20 and has_income)
            or (self.round > 40 and has_surplus)
            or has_trickle
        )

    def _spawn_at(self, ct: Controller, pos: Position) -> None:
        ct.spawn_builder(pos)
        self.spawned += 1
        self.last_spawn_round = self.round

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
                self._spawn_at(ct, preferred)
                return
            for sp in corners:
                if sp != preferred and ct.can_spawn(sp):
                    self._spawn_at(ct, sp)
                    return
            return
        d: Direction = self.rng.choice(DIR8)
        for _ in range(8):
            sp = self.my_pos.add(d)
            if ct.can_spawn(sp):
                self._spawn_at(ct, sp)
                return
            d = d.rotate_right()
        if ct.can_spawn(self.my_pos):
            self._spawn_at(ct, self.my_pos)
