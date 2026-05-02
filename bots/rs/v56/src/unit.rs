//! Models the Python `Unit` / `CoreAwareUnit` class hierarchy as two traits
//! plus a shared `UnitState` struct. Concrete unit types (Breach, Gunner,
//! Builder, Core, …) embed a `UnitState` and implement `Unit::state` /
//! `state_mut`; `CoreAwareUnit` adds `my_core` access on top.
//!
//! Per-turn caching mirrors Python:
//! - `post_init(ct)`: ct-dependent one-shot init. Populates `width`, `height`,
//!   `my_id`, `my_team`, `rng`, then narrows symmetry from initial vision.
//! - `run(ct)`: caches `my_pos`, neighbours, round, resources, visible bots,
//!   and checks for an allied symmetry marker in vision.

use std::collections::{HashMap, HashSet};

use cambc::{Controller, ControllerApi, Direction, EntityType, Environment, Position, Team};

use crate::marker::find_symmetry_marker;
use crate::util::constants::MAX_WIDTH;
use crate::util::directions::{DIR4, DIR8};
use crate::util::symmetry::{ALL, Symmetry};

/// Per-unit PRNG, seeded from the unit's entity id. Wraps
/// `pyrust::random::Random` (a bit-exact reimplementation of `CPython`'s
/// MT19937 + `_randbelow` algorithm), so any random call produces the
/// same sequence in native Rust as in pyrust-translated Python — the
/// requirement for v55-native ⇄ v55-translated replay parity.
pub use pyrust::random::Random as Rng;

/// Per-turn cached state shared by every unit. Concrete units embed this and
/// access via `Unit::state` / `state_mut`.
pub struct UnitState {
    /// Actual map width.
    pub width: i32,
    /// Actual map height.
    pub height: i32,
    /// This unit's entity id.
    pub my_id: i32,
    /// Allied team.
    pub my_team: Team,
    /// Random source, seeded with this unit's entity id.
    pub rng: Rng,

    /// This unit's position, updated at the start of the turn.
    pub my_pos: Position,
    /// Tiles within vision, updated at the start of the turn.
    pub nearby_tiles: Vec<Position>,
    /// Positions of visible enemy builder bots.
    pub enemy_bots: HashSet<Position>,
    /// Positions of visible friendly builder bots (excluding self).
    pub friendly_bots: HashSet<Position>,
    /// Position to entity id of all visible builder bots.
    pub all_bots: HashMap<Position, i32>,
    /// Current round number.
    pub round: i32,
    /// Global titanium at the start of the turn.
    pub ti: i32,
    /// Global (refined) axionite at the start of the turn.
    pub ax: i32,
    /// Scale percent / 100 at the start of the turn.
    pub scale: f64,
    /// Count of living friendly units (this team) at the start of the turn.
    pub unit_count: i32,
    /// Cardinal `(direction, position)` pairs from `my_pos`, in-bounds only.
    pub dir_neighbours_4: Vec<(Direction, Position)>,
    /// All 8 `(direction, position)` pairs from `my_pos`, in-bounds only.
    pub dir_neighbours_8: Vec<(Direction, Position)>,
    /// Cardinal neighbour positions of `my_pos`, in-bounds only.
    pub neighbours_4: Vec<Position>,
    /// All 8 neighbour positions of `my_pos`, in-bounds only.
    pub neighbours_8: Vec<Position>,

    /// Surviving symmetry candidates. Starts as `{Rot, Hor, Ver}` and is
    /// narrowed from vision and from allied symmetry markers.
    pub symmetry_candidates: HashSet<Symmetry>,
}

impl Default for UnitState {
    fn default() -> Self {
        Self::new()
    }
}

impl UnitState {
    /// ct-independent allocation. Mirrors Python `Unit.__init__` — runs in
    /// `Player::default()` (5s window).
    #[must_use]
    pub fn new() -> Self {
        let mut symmetry_candidates: HashSet<Symmetry> = pyrust::set::new!();
        for s in ALL {
            pyrust::set::add!(symmetry_candidates, s);
        }
        Self {
            width: 0,
            height: 0,
            my_id: 0,
            my_team: Team::A,
            rng: Rng::new(0),
            my_pos: Position { x: 0, y: 0 },
            nearby_tiles: pyrust::vec::new!(),
            enemy_bots: pyrust::set::new!(),
            friendly_bots: pyrust::set::new!(),
            all_bots: pyrust::dict::new!(),
            round: 0,
            ti: 0,
            ax: 0,
            scale: 0.0,
            unit_count: 0,
            dir_neighbours_4: pyrust::vec::new!(),
            dir_neighbours_8: pyrust::vec::new!(),
            neighbours_4: pyrust::vec::new!(),
            neighbours_8: pyrust::vec::new!(),
            symmetry_candidates,
        }
    }

    /// One-time setup shared by every unit. Concrete `Unit::post_init`
    /// impls call this on their `state` field — the receiver is concrete
    /// `&mut UnitState`, so pyrust translates field accesses cleanly.
    pub fn init_static_state(&mut self, ct: &mut Controller<'_>) {
        self.width = pyrust::unwrap!(ct.get_map_width());
        self.height = pyrust::unwrap!(ct.get_map_height());
        self.my_id = pyrust::unwrap!(ct.get_id());
        self.my_team = pyrust::unwrap!(ct.get_team(None));
        self.rng = Rng::new(i64::from(self.my_id));
    }

    /// Per-turn caching shared by every unit: position, neighbours, round,
    /// resources, visible bots. Concrete `Unit::run` impls call this on
    /// their `state` field.
    pub fn cache_per_turn_state(&mut self, ct: &mut Controller<'_>) {
        let my_pos = pyrust::unwrap!(ct.get_position(None));
        let width = self.width;
        let height = self.height;
        let my_team = self.my_team;
        let my_id = self.my_id;

        let mut dir_neighbours_4: Vec<(Direction, Position)> = Vec::with_capacity(4);
        for &d in &DIR4 {
            let p = my_pos.add(d);
            if in_bounds(p, width, height) {
                pyrust::vec::push!(dir_neighbours_4, (d, p));
            }
        }
        let mut dir_neighbours_8: Vec<(Direction, Position)> = Vec::with_capacity(8);
        for &d in &DIR8 {
            let p = my_pos.add(d);
            if in_bounds(p, width, height) {
                pyrust::vec::push!(dir_neighbours_8, (d, p));
            }
        }
        let neighbours_4: Vec<Position> =
            pyrust::collect!(pyrust::map!(pyrust::iter!(dir_neighbours_4), |t| t.1));
        let neighbours_8: Vec<Position> =
            pyrust::collect!(pyrust::map!(pyrust::iter!(dir_neighbours_8), |t| t.1));

        let round = pyrust::unwrap!(ct.get_current_round());
        let (ti, ax) = pyrust::unwrap!(ct.get_global_resources());
        let scale = pyrust::unwrap!(ct.get_scale_percent()) / 100.0;
        let unit_count = pyrust::unwrap!(ct.get_unit_count());
        let nearby_tiles = pyrust::unwrap!(ct.get_nearby_tiles(None));

        let mut enemy_bots: HashSet<Position> = pyrust::set::new!();
        let mut friendly_bots: HashSet<Position> = pyrust::set::new!();
        let mut all_bots: HashMap<Position, i32> = pyrust::dict::new!();
        for &pos in &nearby_tiles {
            let Some(uid) = pyrust::unwrap!(ct.get_tile_builder_bot_id(pos)) else {
                continue;
            };
            pyrust::dict::insert!(all_bots, pos, uid);
            if pyrust::unwrap!(ct.get_team(Some(uid))) == my_team {
                if uid != my_id {
                    pyrust::set::add!(friendly_bots, pos);
                }
            } else {
                pyrust::set::add!(enemy_bots, pos);
            }
        }

        self.my_pos = my_pos;
        self.dir_neighbours_4 = dir_neighbours_4;
        self.dir_neighbours_8 = dir_neighbours_8;
        self.neighbours_4 = neighbours_4;
        self.neighbours_8 = neighbours_8;
        self.round = round;
        self.ti = ti;
        self.ax = ax;
        self.scale = scale;
        self.unit_count = unit_count;
        self.nearby_tiles = nearby_tiles;
        self.enemy_bots = enemy_bots;
        self.friendly_bots = friendly_bots;
        self.all_bots = all_bots;
    }

    /// One-shot narrowing of `symmetry_candidates` from current vision.
    /// Mirrors Python `narrow_symmetry_from_vision`.
    pub fn narrow_symmetry_from_vision(&mut self, ct: &mut Controller<'_>) {
        if pyrust::is_some!(self.resolved_symmetry()) {
            return;
        }
        let width = self.width;
        let height = self.height;
        let mut vision: HashMap<Position, (Environment, bool)> = pyrust::dict::new!();
        for pos in pyrust::unwrap!(ct.get_nearby_tiles(None)) {
            let bid = pyrust::unwrap!(ct.get_tile_building_id(pos));
            let is_core = match bid {
                Some(b) => pyrust::unwrap!(ct.get_entity_type(Some(b))) == EntityType::Core,
                None => false,
            };
            pyrust::dict::insert!(
                vision,
                pos,
                (pyrust::unwrap!(ct.get_tile_env(pos)), is_core)
            );
        }

        let mut invalid: HashSet<Symmetry> = pyrust::set::new!();
        let candidates: Vec<Symmetry> =
            pyrust::collect!(pyrust::copied!(pyrust::iter!(self.symmetry_candidates)));
        for sym in candidates {
            for (&pos, val) in &vision {
                let other = vision.get(&sym.action(pos, width, height));
                if let Some(o) = other
                    && o != val
                {
                    pyrust::set::add!(invalid, sym);
                    break;
                }
            }
        }
        for sym in invalid {
            pyrust::set::remove!(self.symmetry_candidates, &sym);
        }
    }

    /// Mirrors Python `_check_symmetry_marker`: pin candidate set to whatever
    /// an allied symmetry marker in vision asserts.
    pub fn check_symmetry_marker(&mut self, ct: &mut Controller<'_>) {
        if pyrust::is_some!(self.resolved_symmetry()) {
            return;
        }
        let nearby = pyrust::clone!(self.nearby_tiles);
        let my_team = self.my_team;
        if let Some(sym) = find_symmetry_marker(ct, &nearby, my_team) {
            self.symmetry_candidates.clear();
            pyrust::set::add!(self.symmetry_candidates, sym);
        }
    }

    /// Resolved symmetry iff exactly one candidate remains. Renamed from
    /// `symmetry` to avoid clashing with concrete units' cached `symmetry`
    /// field (which Python would shadow).
    #[must_use]
    pub fn resolved_symmetry(&self) -> Option<Symmetry> {
        if pyrust::len!(self.symmetry_candidates) == 1 {
            pyrust::copied!(pyrust::next!(pyrust::iter!(self.symmetry_candidates)))
        } else {
            None
        }
    }

    /// Mirroring symmetry usable even when unresolved. ROT → VER → HOR
    /// priority; ROT fallback if all eliminated. Mirrors Python.
    #[must_use]
    pub fn symmetry_guess(&self) -> Symmetry {
        for sym in [Symmetry::Rot, Symmetry::Ver, Symmetry::Hor] {
            if pyrust::vec::contains!(self.symmetry_candidates, &sym) {
                return sym;
            }
        }
        Symmetry::Rot
    }
}

/// Behaviour shared by every unit. The post-init / run defaults delegate
/// to inherent methods on `UnitState`, so the receiver in their bodies is
/// concrete and pyrust translates field accesses cleanly. Subclasses
/// inherit by implementing `state` / `state_mut`.
pub trait Unit {
    /// Read access to the embedded `UnitState`.
    fn unit_state(&self) -> &UnitState;
    /// Mutable access to the embedded `UnitState`.
    fn unit_state_mut(&mut self) -> &mut UnitState;

    /// ct-dependent init. Runs once on first turn for this unit. Mirrors
    /// Python `Unit.post_init`.
    fn post_init(&mut self, ct: &mut Controller<'_>) {
        let s = self.unit_state_mut();
        s.init_static_state(ct);
        s.narrow_symmetry_from_vision(ct);
    }

    /// Cache per-turn state: position, neighbours, visible bots, resources.
    /// Mirrors Python `Unit.run`.
    fn run(&mut self, ct: &mut Controller<'_>) {
        let s = self.unit_state_mut();
        s.cache_per_turn_state(ct);
        s.check_symmetry_marker(ct);
    }

    /// Position to flat index. Stride is `MAX_WIDTH=50` regardless of actual
    /// map size.
    fn idx(&self, pos: Position) -> usize {
        (pos.y as usize) * MAX_WIDTH + (pos.x as usize)
    }

    /// Is in bounds of the actual map.
    fn in_bounds(&self, pos: Position) -> bool {
        let s = self.unit_state();
        in_bounds(pos, s.width, s.height)
    }
}

#[pyrust::inline]
/// In-bounds check shared with the trait's default `in_bounds` method. Free
/// function so trait impls can call it without going through `state()` twice.
#[must_use]
pub const fn in_bounds(pos: Position, width: i32, height: i32) -> bool {
    pos.x >= 0 && pos.x < width && pos.y >= 0 && pos.y < height
}

/// Unit that knows where its allied core is. Subclassed by `Core` (which IS
/// the core) and `Builder` (spawned next to it). Turrets stay as plain
/// `Unit` because they may be built far from the core.
pub trait CoreAwareUnit: Unit {
    /// Allied core position (top-left or centre per concrete subclass'
    /// convention — Python uses centre).
    fn my_core_pos(&self) -> Position;
    /// Set the cached core position; called from `post_init_core_aware`.
    fn set_my_core(&mut self, pos: Position);
    /// Resolve the allied core's position. Called once at `post_init` to
    /// populate `my_core`. Core returns its own position; Builder scans
    /// vision via `find_core`.
    fn resolve_my_core(&mut self, ct: &mut Controller<'_>) -> Position;

    /// Override `Unit::post_init` chain for core-aware units. Concrete
    /// `Unit::post_init` impls on `CoreAwareUnit` types should delegate here.
    fn post_init_core_aware(&mut self, ct: &mut Controller<'_>) {
        let s = self.unit_state_mut();
        s.init_static_state(ct);
        s.narrow_symmetry_from_vision(ct);
        let core = self.resolve_my_core(ct);
        self.set_my_core(core);
    }

    /// Best guess at the enemy core position: mirrors `my_core` under
    /// `symmetry_guess`. Exact once symmetry is resolved.
    fn en_core_guess(&self) -> Position {
        let s = self.unit_state();
        s.symmetry_guess()
            .action(self.my_core_pos(), s.width, s.height)
    }
}
