//! Translation of `bots/intgrah/v54.7.9/unit/__init__.py`.
//!
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
use crate::util::symmetry::Symmetry;

/// Deterministic per-unit PRNG, seeded from the unit's entity id. Mirrors
/// Python's `Random(self.my_id)` for shape; concrete RNG operations
/// (`shuffle`, `choices`, `random`) are added as concrete units start needing
/// them. For now this is a tiny LCG that exposes a bare `next_u64`.
#[derive(Clone, Copy, Debug)]
pub struct Rng {
    state: u64,
}

impl Rng {
    /// Seed from a 32-bit value (the entity id).
    #[must_use]
    pub const fn from_seed(seed: i32) -> Self {
        // Splitmix-style cast so seed=0 is non-degenerate.
        let s = (seed as u64).wrapping_add(0x9E37_79B9_7F4A_7C15);
        Self { state: s }
    }

    /// Advance and return a 64-bit value (LCG step + xorshift).
    pub fn next_u64(&mut self) -> u64 {
        self.state = self
            .state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        let mut x = self.state;
        x ^= x >> 33;
        x = x.wrapping_mul(0xff51_afd7_ed55_8ccd);
        x ^= x >> 33;
        x
    }
}

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
        let mut symmetry_candidates: HashSet<Symmetry> = HashSet::new();
        for s in Symmetry::ALL {
            symmetry_candidates.insert(s);
        }
        Self {
            width: 0,
            height: 0,
            my_id: 0,
            my_team: Team::A,
            rng: Rng::from_seed(0),
            my_pos: Position { x: 0, y: 0 },
            nearby_tiles: Vec::new(),
            enemy_bots: HashSet::new(),
            friendly_bots: HashSet::new(),
            all_bots: HashMap::new(),
            round: 0,
            ti: 0,
            ax: 0,
            scale: 0.0,
            dir_neighbours_4: Vec::new(),
            dir_neighbours_8: Vec::new(),
            neighbours_4: Vec::new(),
            neighbours_8: Vec::new(),
            symmetry_candidates,
        }
    }
}

/// Behaviour shared by every unit. Default methods mirror Python `Unit`'s
/// `post_init`, `run`, and helpers; subclasses inherit by simply implementing
/// `state` / `state_mut`.
pub trait Unit {
    /// Read access to the embedded `UnitState`.
    fn state(&self) -> &UnitState;
    /// Mutable access to the embedded `UnitState`.
    fn state_mut(&mut self) -> &mut UnitState;

    /// ct-dependent init. Runs once on first turn for this unit. Mirrors
    /// Python `Unit.post_init`.
    fn post_init(&mut self, ct: &mut Controller<'_>) {
        post_init_default(self, ct);
    }

    /// Cache per-turn state: position, neighbours, visible bots, resources.
    /// Mirrors Python `Unit.run`.
    fn run(&mut self, ct: &mut Controller<'_>) {
        run_default(self, ct);
    }

    /// Position to flat index. Stride is `MAX_WIDTH=50` regardless of actual
    /// map size.
    fn idx(&self, pos: Position) -> usize {
        (pos.y as usize) * MAX_WIDTH + (pos.x as usize)
    }

    /// Is in bounds of the actual map.
    fn in_bounds(&self, pos: Position) -> bool {
        let s = self.state();
        in_bounds(pos, s.width, s.height)
    }

    /// Resolved symmetry iff exactly one candidate remains.
    fn symmetry(&self) -> Option<Symmetry> {
        let s = self.state();
        if s.symmetry_candidates.len() == 1 {
            s.symmetry_candidates.iter().next().copied()
        } else {
            None
        }
    }

    /// A `Symmetry` value usable for mirroring even when unresolved. Picks the
    /// first surviving candidate in priority order ROT → VER → HOR; falls
    /// back to ROT if all have been eliminated (shouldn't happen on a valid
    /// map). Mirrors the Python `symmetry_guess` ordering exactly.
    fn symmetry_guess(&self) -> Symmetry {
        let s = self.state();
        for sym in [Symmetry::Rot, Symmetry::Ver, Symmetry::Hor] {
            if s.symmetry_candidates.contains(&sym) {
                return sym;
            }
        }
        Symmetry::Rot
    }

    /// One-shot narrowing using only what we can see right now. For static
    /// units (core, turrets) this is the only chance — they don't move, so
    /// their vision never grows.
    fn narrow_symmetry_from_vision(&mut self, ct: &mut Controller<'_>) {
        if self.symmetry().is_some() {
            return;
        }
        let (width, height) = {
            let s = self.state();
            (s.width, s.height)
        };
        let mut vision: HashMap<Position, (Environment, bool)> = HashMap::new();
        for pos in ct.get_nearby_tiles(None).unwrap() {
            let bid = ct.get_tile_building_id(pos).unwrap();
            let is_core = match bid {
                Some(b) => ct.get_entity_type(Some(b)).unwrap() == EntityType::Core,
                None => false,
            };
            vision.insert(pos, (ct.get_tile_env(pos).unwrap(), is_core));
        }

        let mut invalid: HashSet<Symmetry> = HashSet::new();
        let candidates: Vec<Symmetry> = self.state().symmetry_candidates.iter().copied().collect();
        for sym in candidates {
            for (&pos, val) in &vision {
                let other = vision.get(&sym.action(pos, width, height));
                if let Some(o) = other
                    && o != val
                {
                    invalid.insert(sym);
                    break;
                }
            }
        }
        let s = self.state_mut();
        for sym in invalid {
            s.symmetry_candidates.remove(&sym);
        }
    }

    /// Mirrors Python `_check_symmetry_marker`: if symmetry is still
    /// unresolved, scan `nearby_tiles` for an allied symmetry marker and
    /// pin the candidate set to whatever it asserts.
    fn check_symmetry_marker(&mut self, ct: &mut Controller<'_>) {
        if self.symmetry().is_some() {
            return;
        }
        let (nearby, my_team) = {
            let s = self.state();
            (s.nearby_tiles.clone(), s.my_team)
        };
        if let Some(sym) = find_symmetry_marker(ct, &nearby, my_team) {
            let s = self.state_mut();
            s.symmetry_candidates.clear();
            s.symmetry_candidates.insert(sym);
        }
    }
}

/// In-bounds check shared with the trait's default `in_bounds` method. Free
/// function so trait impls can call it without going through `state()` twice.
#[must_use]
pub const fn in_bounds(pos: Position, width: i32, height: i32) -> bool {
    pos.x >= 0 && pos.x < width && pos.y >= 0 && pos.y < height
}

/// Body of `Unit::run`'s default impl, exposed as a free function so concrete
/// units that override `run` can still call the base logic (Rust's analogue
/// of Python's `super().run(ct)`).
/// Body of `Unit::post_init`'s default impl, exposed as a free function so
/// concrete units that override `post_init` can still call the base logic
/// (Rust's analogue of Python's `super().post_init(ct)`). Calling
/// `Unit::post_init` from a trait method would dispatch dynamically and
/// recurse back into the override.
pub fn post_init_default<U: Unit + ?Sized>(this: &mut U, ct: &mut Controller<'_>) {
    let s = this.state_mut();
    s.width = ct.get_map_width().unwrap();
    s.height = ct.get_map_height().unwrap();
    s.my_id = ct.get_id().unwrap();
    s.my_team = ct.get_team(None).unwrap();
    s.rng = Rng::from_seed(s.my_id);
    this.narrow_symmetry_from_vision(ct);
}

pub fn run_default<U: Unit + ?Sized>(this: &mut U, ct: &mut Controller<'_>) {
    let my_pos = ct.get_position(None).unwrap();
    let (width, height, my_team, my_id) = {
        let s = this.state();
        (s.width, s.height, s.my_team, s.my_id)
    };

    let mut dir_neighbours_4: Vec<(Direction, Position)> = Vec::with_capacity(4);
    for &d in &DIR4 {
        let p = my_pos.add(d);
        if in_bounds(p, width, height) {
            dir_neighbours_4.push((d, p));
        }
    }
    let mut dir_neighbours_8: Vec<(Direction, Position)> = Vec::with_capacity(8);
    for &d in &DIR8 {
        let p = my_pos.add(d);
        if in_bounds(p, width, height) {
            dir_neighbours_8.push((d, p));
        }
    }
    let neighbours_4: Vec<Position> = dir_neighbours_4.iter().map(|&(_, p)| p).collect();
    let neighbours_8: Vec<Position> = dir_neighbours_8.iter().map(|&(_, p)| p).collect();

    let round = ct.get_current_round().unwrap();
    let (ti, ax) = ct.get_global_resources().unwrap();
    let scale = ct.get_scale_percent().unwrap() / 100.0;
    let nearby_tiles = ct.get_nearby_tiles(None).unwrap();

    let mut enemy_bots: HashSet<Position> = HashSet::new();
    let mut friendly_bots: HashSet<Position> = HashSet::new();
    let mut all_bots: HashMap<Position, i32> = HashMap::new();
    for &pos in &nearby_tiles {
        let Some(uid) = ct.get_tile_builder_bot_id(pos).unwrap() else {
            continue;
        };
        all_bots.insert(pos, uid);
        if ct.get_team(Some(uid)).unwrap() == my_team {
            if uid != my_id {
                friendly_bots.insert(pos);
            }
        } else {
            enemy_bots.insert(pos);
        }
    }

    {
        let s = this.state_mut();
        s.my_pos = my_pos;
        s.dir_neighbours_4 = dir_neighbours_4;
        s.dir_neighbours_8 = dir_neighbours_8;
        s.neighbours_4 = neighbours_4;
        s.neighbours_8 = neighbours_8;
        s.round = round;
        s.ti = ti;
        s.ax = ax;
        s.scale = scale;
        s.nearby_tiles = nearby_tiles;
        s.enemy_bots = enemy_bots;
        s.friendly_bots = friendly_bots;
        s.all_bots = all_bots;
    }

    this.check_symmetry_marker(ct);
}

/// Unit that knows where its allied core is. Subclassed by `Core` (which IS
/// the core) and `Builder` (spawned next to it). Turrets stay as plain
/// `Unit` because they may be built far from the core.
pub trait CoreAwareUnit: Unit {
    /// Allied core position (top-left or centre per concrete subclass'
    /// convention — Python uses centre).
    fn my_core(&self) -> Position;
    /// Set the cached core position; called from `post_init_core_aware`.
    fn set_my_core(&mut self, pos: Position);
    /// Resolve the allied core's position. Called once at `post_init` to
    /// populate `my_core`. Core returns its own position; Builder scans
    /// vision via `find_core`.
    fn resolve_my_core(&mut self, ct: &mut Controller<'_>) -> Position;

    /// Override `Unit::post_init` chain for core-aware units. Concrete
    /// `Unit::post_init` impls on `CoreAwareUnit` types should delegate here.
    /// Calls `post_init_default` directly rather than `Unit::post_init` to
    /// avoid recursing back into the concrete unit's own `post_init` override.
    fn post_init_core_aware(&mut self, ct: &mut Controller<'_>) {
        post_init_default(self, ct);
        let core = self.resolve_my_core(ct);
        self.set_my_core(core);
    }

    /// Best guess at the enemy core position: mirrors `my_core` under
    /// `symmetry_guess`. Exact once symmetry is resolved.
    fn en_core_guess(&self) -> Position {
        let s = self.state();
        self.symmetry_guess()
            .action(self.my_core(), s.width, s.height)
    }
}
