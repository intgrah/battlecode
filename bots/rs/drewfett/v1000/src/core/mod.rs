//! Translation of `bots/intgrah/v54.7.9/core/__init__.py`.
//!
//! Phase 5 PosInt note: Core uses UnitState (not Builder). The count_incoming
//! loop walks DIR8 + DIR4 via Position::add and calls ct API — no Builder
//! per-tile arrays to use _p accessors on.
//! TODO Phase 5 holdout: convert if UnitState gains _p accessors.

pub mod opening;
pub mod spawn_tempo;

use std::collections::VecDeque;

use cambc::{Controller, ControllerApi, Direction, EntityType, Position, ResourceType};

use crate::core::opening::{OpeningTemplate, classify};
use crate::core::spawn_tempo::compute_spawn_tempo;
use crate::unit::{CoreAwareUnit, Unit, UnitState};
use crate::util::debug::Scope;
use crate::util::directions::{DIR4, DIR8};

const CORNERS: [Direction; 4] = [
    Direction::Northeast,
    Direction::Southeast,
    Direction::Southwest,
    Direction::Northwest,
];

const fn rotate_right(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::Northeast,
        Direction::Northeast => Direction::East,
        Direction::East => Direction::Southeast,
        Direction::Southeast => Direction::South,
        Direction::South => Direction::Southwest,
        Direction::Southwest => Direction::West,
        Direction::West => Direction::Northwest,
        Direction::Northwest => Direction::North,
        Direction::Centre => Direction::Centre,
    }
}

pub struct Core {
    state: UnitState,
    my_core: Position,
    /// Cumulative number of builders spawned by this core.
    pub spawned: i32,
    /// Round of the most recent spawn.
    pub last_spawn_round: i32,
    /// Rolling window of incoming-titanium counts, oldest entries at the
    /// back. Capped at `INCOME_SAMPLES`.
    pub deliveries: VecDeque<i32>,
    /// Cap on total team unit count (builders + turrets + core). Scales
    /// linearly with map size: 18 on a 20x20 map up to 36 on a 50x50 map.
    pub max_team_units: i32,
    /// Map-specific spawn-rate multiplier in [~0.7, ~1.3].
    pub spawn_tempo: f64,
    /// WS-3: opening template, classified once at `post_init`.
    pub opening: OpeningTemplate,
}

impl Core {
    pub const INITIAL_SPAWNS: i32 = 4;
    pub const INCOME_SAMPLES: usize = 16;
    pub const INCOME_PER_UNIT: f64 = 0.65;
    pub const INCOME_QUADRATIC_TERM: f64 = 0.04;
    pub const SURPLUS_BASELINE: i32 = 40;
    pub const SURPLUS_SCALE_FACTOR: i32 = 50;
    pub const TRICKLE_COST_MULTIPLIER: f64 = 8.0;
    pub const TRICKLE_MIN_INTERVAL: i32 = 40;
    pub const CROWDING_LIMIT: usize = 3;
    pub const CONVERSION_TI_THRESHOLD: i32 = 200;
    pub const CONVERSION_AX_THRESHOLD: i32 = 2;

    #[must_use]
    pub fn new() -> Self {
        let mut deliveries: VecDeque<i32> = VecDeque::with_capacity(Self::INCOME_SAMPLES);
        for _ in 0..Self::INCOME_SAMPLES {
            pyrust::vec::push_back!(deliveries, 0);
        }
        Self {
            state: UnitState::new(),
            my_core: Position { x: 0, y: 0 },
            spawned: 0,
            last_spawn_round: 0,
            deliveries,
            max_team_units: 0,
            spawn_tempo: 1.0,
            opening: OpeningTemplate::DefaultBalanced,
        }
    }

    fn maybe_convert(&self, ct: &mut Controller<'_>) {
        let need = Self::CONVERSION_TI_THRESHOLD - self.state.ti;
        let surplus_ax = self.state.ax - Self::CONVERSION_AX_THRESHOLD;
        if need > 0 && surplus_ax > 0 {
            let amount = pyrust::min!(surplus_ax, (need + 3) / 4);
            pyrust::unwrap!(ct.convert(amount));
        }
    }

    fn count_incoming(&self, ct: &mut Controller<'_>) -> i32 {
        let mut count: i32 = 0;
        for &d in &DIR8 {
            let tile = self.state.my_pos.add(d);
            for &cd in &DIR4 {
                let src = tile.add(cd);
                if !self.in_bounds(src) {
                    continue;
                }
                let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(src)) else {
                    continue;
                };
                let etype = pyrust::unwrap!(ct.get_entity_type(Some(bid)));
                if !matches!(etype, EntityType::Conveyor | EntityType::ArmouredConveyor) {
                    continue;
                }
                if pyrust::unwrap!(ct.get_direction(Some(bid))).opposite() != cd {
                    continue;
                }
                if pyrust::unwrap!(ct.get_stored_resource(Some(bid)))
                    == Some(ResourceType::Titanium)
                {
                    count += 1;
                }
            }
        }
        count
    }

    /// WS-3: per-game initial-spawn count, modulated by opening template.
    fn initial_spawns(&self) -> i32 {
        let scaled =
            pyrust::round!((Self::INITIAL_SPAWNS as f64 * self.opening.initial_spawn_factor()));
        pyrust::max!(scaled, 1.0) as i32
    }

    fn should_spawn(&self, ct: &mut Controller<'_>, income_rate: f64) -> bool {
        if self.spawned < self.initial_spawns() {
            return true;
        }
        let live_units = pyrust::unwrap!(ct.get_unit_count());
        if live_units >= self.max_team_units {
            return false;
        }
        if pyrust::len!(self.state.enemy_bots) > pyrust::len!(self.state.friendly_bots) {
            return true;
        }
        if pyrust::len!(self.state.friendly_bots) > Self::CROWDING_LIMIT {
            return false;
        }
        let eagerness = self.opening.spawn_eagerness();
        let live = pyrust::float!(live_units);
        let income_threshold =
            (Self::INCOME_PER_UNIT * live + Self::INCOME_QUADRATIC_TERM * live * live) * eagerness
                / self.spawn_tempo;
        let has_income = income_rate * 4.0 > income_threshold;
        let surplus_threshold = (pyrust::float!(Self::SURPLUS_BASELINE)
            + pyrust::float!(Self::SURPLUS_SCALE_FACTOR)
                * (pyrust::unwrap!(ct.get_scale_percent()) / 100.0))
            * (2.0 - self.spawn_tempo)
            * eagerness;
        let has_surplus = pyrust::float!(self.state.ti) > surplus_threshold;
        let builder_ti_cost = pyrust::unwrap!(ct.get_builder_bot_cost()).0;
        let has_trickle = pyrust::float!(self.state.ti)
            > pyrust::float!(builder_ti_cost) * Self::TRICKLE_COST_MULTIPLIER
            && self.state.round - self.last_spawn_round > Self::TRICKLE_MIN_INTERVAL;
        (self.state.round > 20 && has_income)
            || (self.state.round > 40 && has_surplus)
            || has_trickle
    }

    fn spawn_at(&mut self, ct: &mut Controller<'_>, pos: Position) {
        pyrust::unwrap!(ct.spawn_builder(pos));
        self.spawned += 1;
        self.last_spawn_round = self.state.round;
    }

    fn try_spawn(&mut self, ct: &mut Controller<'_>) {
        if self.spawned < self.initial_spawns() {
            let en_core = self.en_core_guess();
            let mut corners: Vec<Position> =
                pyrust::collect!(pyrust::map!(pyrust::iter!(CORNERS), |&d| self
                    .state
                    .my_pos
                    .add(d)));
            pyrust::sort_by_key!(corners, |p| en_core.distance_squared(*p));
            let idx = pyrust::min!((self.spawned as usize), pyrust::len!(corners) - 1);
            let preferred = corners[idx];
            if pyrust::unwrap!(ct.can_spawn(preferred)) {
                self.spawn_at(ct, preferred);
                return;
            }
            for sp in &corners {
                if *sp != preferred && pyrust::unwrap!(ct.can_spawn(*sp)) {
                    self.spawn_at(ct, *sp);
                    return;
                }
            }
            return;
        }
        let mut d = *self.state.rng.choice(&DIR8);
        for _ in 0..8 {
            let sp = self.state.my_pos.add(d);
            if pyrust::unwrap!(ct.can_spawn(sp)) {
                self.spawn_at(ct, sp);
                return;
            }
            d = rotate_right(d);
        }
        if pyrust::unwrap!(ct.can_spawn(self.state.my_pos)) {
            let p = self.state.my_pos;
            self.spawn_at(ct, p);
        }
    }
}

impl Default for Core {
    fn default() -> Self {
        Self::new()
    }
}

impl Unit for Core {
    #[pyrust::inline]
    fn unit_state(&self) -> &UnitState {
        &self.state
    }

    fn unit_state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn post_init(&mut self, ct: &mut Controller<'_>) {
        self.post_init_core_aware(ct);
        let area = self.state.width * self.state.height;
        let numerator = pyrust::float!((36 - 18) * (area - 20 * 20));
        let denominator = pyrust::float!(50 * 50 - 20 * 20);
        let raw = 18.0 + numerator / denominator;
        self.max_team_units = pyrust::round!(raw) as i32;
        let _scope = Scope::new_timed("spawn_tempo");
        self.spawn_tempo = compute_spawn_tempo(self.state.width, self.state.height, ct);
        pyrust::drop!(_scope);
        let _scope = Scope::new_timed("opening_classify");
        let en_core = self.en_core_guess();
        self.opening = classify(
            self.state.width,
            self.state.height,
            self.my_core,
            en_core,
            ct,
        );
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        self.state.cache_per_turn_state(ct);
        self.state.check_symmetry_marker(ct);
        let incoming = self.count_incoming(ct);
        if pyrust::len!(self.deliveries) == Self::INCOME_SAMPLES {
            pyrust::vec::pop_back!(self.deliveries);
        }
        pyrust::vec::push_front!(self.deliveries, incoming);
        let total: i32 = pyrust::sum!(pyrust::iter!(self.deliveries));
        let income_rate = pyrust::float!(total) / pyrust::len!(self.deliveries) as f64;

        self.maybe_convert(ct);

        if self.should_spawn(ct, income_rate) {
            self.try_spawn(ct);
        }
    }
}

impl CoreAwareUnit for Core {
    #[pyrust::inline]
    fn my_core_pos(&self) -> Position {
        self.my_core
    }

    fn set_my_core(&mut self, pos: Position) {
        self.my_core = pos;
    }

    fn resolve_my_core(&mut self, ct: &mut Controller<'_>) -> Position {
        pyrust::unwrap!(ct.get_position(None))
    }
}
