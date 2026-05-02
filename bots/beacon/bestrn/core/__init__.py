"""Translation of `bots/intgrah/v54.7.9/core/__init__.py`."""
from __future__ import annotations

from typing import Final

from unit import in_bounds
from cambc import Direction, EntityType, Position, ResourceType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
from config import HARDCODE
from core.spawn_tempo import compute_spawn_tempo
from hardcode.identify import identify_map
if TYPE_CHECKING:
    from hardcode.identify import KnownMap
from unit import UnitState
from util.debug import Scope
from util.directions import DIR4, DIR8
CORNERS: Final[list[Direction]] = [Direction.NORTHEAST, Direction.SOUTHEAST, Direction.SOUTHWEST, Direction.NORTHWEST]

def rotate_right(d):
    match d:
        case Direction.NORTH:
            return Direction.NORTHEAST
        case Direction.NORTHEAST:
            return Direction.EAST
        case Direction.EAST:
            return Direction.SOUTHEAST
        case Direction.SOUTHEAST:
            return Direction.SOUTH
        case Direction.SOUTH:
            return Direction.SOUTHWEST
        case Direction.SOUTHWEST:
            return Direction.WEST
        case Direction.WEST:
            return Direction.NORTHWEST
        case Direction.NORTHWEST:
            return Direction.NORTH
        case Direction.CENTRE:
            return Direction.CENTRE

class Core:
    state: UnitState
    my_core: Position
    spawned: int
    last_spawn_round: int
    deliveries: list[int]
    max_team_units: int
    spawn_tempo: float
    known_map: KnownMap | None

    def __init__(self):
        deliveries: list[int] = []
        for _ in range(0, Core.INCOME_SAMPLES):
            deliveries.append(0)
        self.state = UnitState()
        self.my_core = Position(x=0, y=0)
        self.spawned = 0
        self.last_spawn_round = 0
        self.deliveries = deliveries
        self.max_team_units = 0
        self.spawn_tempo = 1.0
        self.known_map = None
    INITIAL_SPAWNS: Final[int] = 4
    INCOME_SAMPLES: Final[int] = 16
    INCOME_PER_UNIT: Final[float] = 0.65
    INCOME_QUADRATIC_TERM: Final[float] = 0.04
    SURPLUS_BASELINE: Final[int] = 40
    SURPLUS_SCALE_FACTOR: Final[int] = 50
    TRICKLE_COST_MULTIPLIER: Final[float] = 8.0
    TRICKLE_MIN_INTERVAL: Final[int] = 40
    CROWDING_LIMIT: Final[int] = 3
    CONVERSION_TI_THRESHOLD: Final[int] = 200
    CONVERSION_AX_THRESHOLD: Final[int] = 2

    def maybe_convert(self, ct):
        need = Core.CONVERSION_TI_THRESHOLD - self.state.ti
        surplus_ax = self.state.ax - Core.CONVERSION_AX_THRESHOLD
        if need > 0 and surplus_ax > 0:
            amount = min(surplus_ax, (need + 3) // 4)
            ct.convert(amount)

    def count_incoming(self, ct):
        count: int = 0
        for d in DIR8:
            tile = self.state.my_pos.add(d)
            for cd in DIR4:
                src = tile.add(cd)
                if not self.in_bounds(src):
                    continue
                bid = ct.get_tile_building_id(src)
                if bid is None:
                    continue
                etype = ct.get_entity_type(bid)
                if not (etype == EntityType.CONVEYOR or etype == EntityType.ARMOURED_CONVEYOR):
                    continue
                if ct.get_direction(bid).opposite() != cd:
                    continue
                if ct.get_stored_resource(bid) == ResourceType.TITANIUM:
                    count += 1
        return count

    def should_spawn(self, ct, income_rate):
        if self.spawned < Core.INITIAL_SPAWNS:
            return True
        live_units = ct.get_unit_count()
        if live_units >= self.max_team_units:
            return False
        if len(self.state.enemy_bots) > len(self.state.friendly_bots):
            return True
        if len(self.state.friendly_bots) > Core.CROWDING_LIMIT:
            return False
        live = float(live_units)
        income_threshold = (Core.INCOME_PER_UNIT * live + Core.INCOME_QUADRATIC_TERM * live * live) / self.spawn_tempo
        has_income = income_rate * 4.0 > income_threshold
        surplus_threshold = (float(Core.SURPLUS_SCALE_FACTOR) * ct.get_scale_percent() / 100.0 + float(Core.SURPLUS_BASELINE)) * (2.0 - self.spawn_tempo)
        has_surplus = float(self.state.ti) > surplus_threshold
        builder_ti_cost = ct.get_builder_bot_cost()[0]
        has_trickle = float(self.state.ti) > float(builder_ti_cost) * Core.TRICKLE_COST_MULTIPLIER and self.state.round - self.last_spawn_round > Core.TRICKLE_MIN_INTERVAL
        return self.state.round > 20 and has_income or self.state.round > 40 and has_surplus or has_trickle

    def spawn_at(self, ct, pos):
        ct.spawn_builder(pos)
        self.spawned += 1
        self.last_spawn_round = self.state.round

    def try_spawn(self, ct):
        if self.spawned < Core.INITIAL_SPAWNS:
            en_core = self.en_core_guess()
            corners: list[Position] = list((self.state.my_pos.add(d) for d in CORNERS))
            corners.sort(key=lambda p: en_core.distance_squared(p))
            preferred = corners[int(self.spawned)]
            if ct.can_spawn(preferred):
                self.spawn_at(ct, preferred)
                return
            for sp in corners:
                if sp != preferred and ct.can_spawn(sp):
                    self.spawn_at(ct, sp)
                    return
            return
        d = self.state.rng.choice(DIR8)
        for _ in range(0, 8):
            sp = self.state.my_pos.add(d)
            if ct.can_spawn(sp):
                self.spawn_at(ct, sp)
                return
            d = rotate_right(d)
        if ct.can_spawn(self.state.my_pos):
            p = self.state.my_pos
            self.spawn_at(ct, p)

    @staticmethod
    def default():
        return Core()

    def unit_state(self):
        return self.state

    def unit_state_mut(self):
        return self.state

    def post_init(self, ct):
        self.state.init_static_state(ct)
        self.state.narrow_symmetry_from_vision(ct)
        core = self.resolve_my_core(ct)
        self.set_my_core(core)
        known = identify_map(self.state.width, self.state.height, self.my_core) if False else None
        self.known_map = known
        area = self.state.width * self.state.height
        numerator = float((36 - 18) * (area - 20 * 20))
        denominator = float(50 * 50 - 20 * 20)
        raw = 18.0 + numerator / denominator
        self.max_team_units = int(round(raw))
        with Scope.new_timed("spawn_tempo") as _scope:
            self.spawn_tempo = compute_spawn_tempo(self.state.width, self.state.height, ct)

    def run(self, ct):
        self.state.cache_per_turn_state(ct)
        self.state.check_symmetry_marker(ct)
        incoming = self.count_incoming(ct)
        if len(self.deliveries) == Core.INCOME_SAMPLES:
            (self.deliveries.pop() if self.deliveries else None)
        self.deliveries.insert(0, incoming)
        total: int = sum(self.deliveries)
        income_rate = float(total) / float(len(self.deliveries))
        self.maybe_convert(ct)
        if self.should_spawn(ct, income_rate):
            self.try_spawn(ct)

    def my_core_pos(self):
        return self.my_core

    def set_my_core(self, pos):
        self.my_core = pos

    def resolve_my_core(self, ct):
        return ct.get_position(None)

    def post_init_core_aware(self, ct):
        """
        Override `Unit::post_init` chain for core-aware units. Concrete
        `Unit::post_init` impls on `CoreAwareUnit` types should delegate here.
        """
        s = self.unit_state_mut()
        s.init_static_state(ct)
        s.narrow_symmetry_from_vision(ct)
        core = self.resolve_my_core(ct)
        self.set_my_core(core)

    def en_core_guess(self):
        """
        Best guess at the enemy core position: mirrors `my_core` under
        `symmetry_guess`. Exact once symmetry is resolved.
        """
        s = self.unit_state()
        return s.symmetry_guess().action(self.my_core_pos(), s.width, s.height)

    def idx(self, pos):
        """
        Position to flat index. Stride is `MAX_WIDTH=50` regardless of actual
        map size.
        """
        return int(pos.y) * 50 + int(pos.x)

    def in_bounds(self, pos):
        """Is in bounds of the actual map."""
        s = self.unit_state()
        return in_bounds(pos, s.width, s.height)
