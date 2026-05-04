//! Translation of `bots/intgrah/v54.7.9/builder/__init__.py`.
//!
//! `Builder` is the bot's most complex unit — it owns map belief, conveyor
//! routing graphs, navigation state, role/task scheduling, and per-turn
//! ephemeral sets. Submodules implement the algorithms (`algorithms/`),
//! per-turn updates (`update/`), end-of-turn hooks (`hooks/`), and the
//! task-policy tree (`tasks/`); this file wires them together.

pub mod algorithms;
pub mod chain_routing;
pub mod dump;
pub mod explore;
pub mod harvest;
pub mod helpers;
pub mod hooks;
pub mod patrol;
pub mod role;
pub mod tasks;
pub mod update;

use std::collections::{HashMap, HashSet, VecDeque};
use std::ops::{Deref, DerefMut};

use cambc::{
    Controller, ControllerApi, EntityType, Environment, GameConstants, Position, ResourceType,
};
use serde_json::Map;

use crate::builder::algorithms::econ_astar::AStarSearch;
use crate::builder::algorithms::econ_astar::AstarStep;
use crate::builder::algorithms::econ_astar::EconAstarCtx;
use crate::builder::algorithms::nav::{BugNav, NavCtx};
use crate::builder::algorithms::nav_bfs::NavBfs;
use crate::builder::algorithms::reachability::{find_ro, update_reachability};
use crate::builder::dump::dump as dump_state;
use crate::builder::hooks::heal::end_of_turn_heal;
use crate::builder::hooks::indicators::indicators;
use crate::builder::hooks::propagate_symmetry::end_of_turn_propagate_symmetry;
use crate::builder::role::Role;
use crate::builder::tasks::_policy::run_policy;
use crate::builder::tasks::offense::helpers::begin_turn_offense;
use crate::builder::tasks::policy_for_role;
use crate::builder::update::budget::BudgetTelemetry;
use crate::builder::update::update;
use crate::builder::update::vision::apply_local_destroy as vision_apply_local_destroy;
use crate::config::DEBUG_DUMP;
use crate::config::DEBUG_LOG;
use crate::core::opening::{OpeningTemplate, classify as classify_opening};
use crate::unit::{CoreAwareUnit, Unit, UnitState};
use crate::util::constants::{BOUND_RANGE, INF, MAX_WIDTH, POSINT_VALID_LEN, ROAD_COST, STRIDE};
use crate::util::debug::{Scope, debug as log};
use crate::util::directions::{DIR4, DIR8};
use crate::util::posint::{PosInt, idx_of};
use crate::util::symmetry::Symmetry;
use crate::util::trace;
use crate::util::visualiser::auto_wrap_position;
use cambc::Team;

/// The Builder unit. Embeds `UnitState` (auto-Deref'd so `builder.my_pos`
/// resolves transparently) plus per-builder map belief, navigation state,
/// economy bookkeeping, role state, and offense/heal trackers.
pub struct Builder {
    /// Generic per-turn unit state (position, neighbours, visible bots,
    /// resources, symmetry candidates). Deref'd so peer code can write
    /// `builder.my_pos` instead of `builder.state.my_pos`.
    pub state: UnitState,

    /// Allied core position (3x3 centre). Mirrors Python `self.my_core`.
    pub my_core: Position,
    /// Flat PosInt index of `my_core`. Cached to avoid repeated `idx_of` calls
    /// in hot functions like `harvester_feed_cardinal_p`.
    pub my_core_p: PosInt,
    /// Mirror of `my_core` under the chosen `symmetry_guess` — cached at
    /// the start of each turn so `builder.en_core_guess` (no parens) and
    /// `builder.en_core_guess()` (the trait method) are interchangeable.
    pub en_core_guess: Position,
    /// Flat PosInt index of `en_core_guess`. Cached to avoid repeated `idx_of`
    /// calls in hot functions like `harvester_feed_cardinal_p`.
    pub en_core_guess_p: PosInt,
    /// `Some(s)` once a single symmetry remains in `state.symmetry_candidates`,
    /// else `None`. Cached field for peer code that uses `if builder.symmetry`.
    pub symmetry: Option<Symmetry>,

    /// Wall / Empty / `OreTitanium` / `OreAxionite` per tile (None = unobserved).
    pub env: [Option<Environment>; BOUND_RANGE],
    /// Cached entity ids per tile, for change detection.
    pub building_ids: [Option<i32>; BOUND_RANGE],
    /// Building kind per tile (None when no building / not in vision).
    pub building_kind: [Option<EntityType>; BOUND_RANGE],
    /// Owning team per tile, parallel to `building_kind`.
    pub building_team: [Option<Team>; BOUND_RANGE],
    /// HP of building on each tile.
    pub hp: [i32; BOUND_RANGE],
    /// Max HP of building on each tile.
    pub max_hp: [i32; BOUND_RANGE],

    /// Movement cost per tile.
    pub cost_grid: [i32; BOUND_RANGE],
    /// Flat indices currently carrying a threat penalty in `cost_grid`.
    pub _threat_bumped: HashSet<usize>,
    /// Flat indices that are inside an enemy launcher's throw range. Bug2
    /// nav masks these as INF on its first attempt and falls back without
    /// mask if no path exists.
    pub unsafe_tiles: HashSet<usize>,

    /// True iff a routable building could be placed on this tile.
    pub buildable: [bool; BOUND_RANGE],
    /// True iff Ti routing through this tile would mix with Ax.
    pub ti_leakage: [bool; BOUND_RANGE],
    /// True iff Ax routing through this tile would mix with Ti.
    pub ax_leakage: [bool; BOUND_RANGE],
    /// `buildable[i] && !ti_leakage[i]`.
    pub ti_routable: [bool; BOUND_RANGE],
    /// `buildable[i] && !ax_leakage[i]`.
    pub ax_routable: [bool; BOUND_RANGE],
    /// Per-tile additive A* relaxation cost (0 normally, 4 for enemy roads).
    pub routing_extra: [u8; BOUND_RANGE],

    pub _ti_harv_at: [i32; BOUND_RANGE],
    pub _ax_harv_at: [i32; BOUND_RANGE],
    pub _foundry_at: [i32; BOUND_RANGE],

    pub _ti_in_count: [i32; BOUND_RANGE],
    pub _ax_in_count: [i32; BOUND_RANGE],

    /// `posint_valid[p] == 1` iff `p` is in-bounds for the actual map.
    /// Length `BOUND_RANGE + STRIDE = 5100`: the trailing `STRIDE` bytes
    /// stay 0 forever, padding so neighbour lookups `p + DIR8_INT[i]`
    /// (max +101 from p ≤ 4949) never OOB. Callers still need to check
    /// `np >= 0` for the lower-edge case. Populated in `post_init`.
    pub posint_valid: Vec<u8>,

    /// `vision_mask[p] != 0` iff PosInt `p` was in vision this turn.
    /// Repopulated each turn at the start of `update_vision` from
    /// `state.nearby_tiles`. Avoids 580k `ct.is_in_vision` engine calls
    /// per game (~172ms total: 130ns×580k direct + engine overhead).
    pub vision_mask: Vec<u8>,
    /// PosInts that had `vision_mask == 1` last turn — lets us reset
    /// the mask in O(prev-vision-size) instead of memsetting BOUND_RANGE.
    pub last_vision: Vec<i32>,

    /// Passable-neighbour list per tile (flat indices). Pre-built for full
    /// `MAX_WIDTH × MAX_WIDTH`; trimmed in `post_init` for the actual map.
    /// Union-find parent pointer for incremental reachability.
    pub reach_parent: [i32; BOUND_RANGE],
    /// Frontier of admitted-but-unexpanded tiles. Persists across turns.
    pub reach_frontier: Vec<i32>,

    /// A* search instance for Ti chain routing.
    pub conv_search: AStarSearch,
    /// A* search instance for Ax chain routing.
    pub ax_conv_search: AStarSearch,

    /// Bug2-bounded planner + `dp_step` path-follower. Persists across turns.
    pub bugnav: BugNav,

    /// Backwards-BFS navigation. Maintains a dist field from the current
    /// goal; `step_bfs` reads it via gradient descent. Lives parallel to
    /// `bugnav` — `next_step_toward` tries BFS first and falls back to
    /// bug2 if BFS hasn't found a path.
    pub nav_bfs: NavBfs,

    /// WS-6: memoized bug2 results across turns. Key is `(start, target)` of a
    /// completed plan, value is the ordered tile sequence (start ... target).
    /// Entries are validated against `cost_grid` before reuse — any tile that
    /// became impassable (INF) since cache invalidates the entry. Bounded
    /// to `BUG2_PATH_CACHE_CAP` entries via FIFO eviction.
    pub budget_telemetry: BudgetTelemetry,
    pub bug2_path_cache: HashMap<(Position, Position), Vec<Position>>,
    /// FIFO of cache keys for bounded eviction.
    pub bug2_path_cache_order: VecDeque<(Position, Position)>,

    /// Per-tile rolling window of `(resource, stack_id)` observations.
    pub flow_history: [VecDeque<(Option<ResourceType>, Option<i32>)>; BOUND_RANGE],

    /// Structural feeders: `in_edges[i]` lists positions that output onto tile i.
    pub in_edges: [Vec<Position>; BOUND_RANGE],
    /// Structural consumers: `out_edges[i]` lists positions that tile i outputs to.
    pub out_edges: [Vec<Position>; BOUND_RANGE],

    /// Tiles to mirror via symmetry once it's resolved (rate-limited).
    pub reflect_queue: VecDeque<usize>,

    // Ephemeral (recomputed each turn, but stored to avoid re-allocation cost).
    pub nearby_buildings: Vec<Position>,
    pub healable_buildings: Vec<Position>,
    /// Ore tiles in vision this turn, partitioned by resource type. Filled
    /// during `update_vision` as `PosInt = y * STRIDE + x`; consumers
    /// (_pick_ore, ore_denial, offensive_ore_target, deny_enemy_ore) iterate
    /// these instead of the full ~60-element nearby_tiles to skip the
    /// per-call env-filter pass. Stored as `PosInt` so the inner-loop
    /// `bk[p]`, `bt[p]`, `env[p]` lookups need no `y * STRIDE + x`
    /// arithmetic per call. Convert back via `pos_of(p)` only when calling
    /// helpers that need a `Position`. Cleared in `prune::prune_stale`.
    pub visible_ti_ore: Vec<PosInt>,
    pub visible_ax_ore: Vec<PosInt>,
    /// All harvesters (any team) seen in vision this turn, as `PosInt`.
    /// Filled during `update_vision`; consumed by `update_map_econ` Pass 1
    /// instead of scanning all 60 nearby_tiles. Cleared in `prune::prune_stale`.
    pub visible_harvesters: Vec<PosInt>,
    // Phase 4: per-tile sets store `PosInt`. Hashing an int is ~5x faster
    // than hashing a Position in CPython, and lookups don't need to allocate
    // a Position struct for the comparison key.
    pub adjacent_to_unconnected_harvester: HashSet<PosInt>,
    /// Cardinal-adjacent in-bounds tiles to a friendly foundry that has
    /// no non-inward output consumer. Mirrors the harvester-unconn shape
    /// — these tiles enter `dangling_set` so a builder can extend the
    /// foundry's Rax output side.
    pub adjacent_to_unconnected_foundry: HashSet<PosInt>,
    pub adjacent_to_harvester: HashSet<PosInt>,
    pub ti_harvester_adjacent: HashSet<PosInt>,
    pub ax_harvester_adjacent: HashSet<PosInt>,
    pub reaches_core: HashSet<PosInt>,
    pub reaches_foundry: HashSet<PosInt>,
    /// Tiles structurally downstream of a friendly foundry's output —
    /// computed by forward-flooding `out_edges` from `my_foundries`. A Ti
    /// conveyor here would receive refined Ax from the foundry and clog,
    /// so it must not become a new `foundry_target`.
    pub downstream_of_foundry: HashSet<PosInt>,
    pub ti_upstream: HashSet<PosInt>,
    pub ax_upstream: HashSet<PosInt>,
    pub upstream_of_dangling: HashSet<PosInt>,
    pub congested_junctions: HashSet<PosInt>,
    pub upstream_of_congestion: HashSet<PosInt>,
    pub my_foundries: HashSet<PosInt>,
    pub my_harvesters: HashSet<PosInt>,
    pub is_multi_input: HashSet<PosInt>,
    pub junctions: HashSet<PosInt>,
    pub adjacent_to_enemy_launcher: HashSet<PosInt>,
    pub enemy_turret_ray_tiles: HashSet<PosInt>,
    pub friendly_turret_ray_tiles: HashSet<PosInt>,
    pub deny_ore_neighbours: HashSet<PosInt>,
    pub nearest_enemy_turret: Option<Position>,

    // Role: binary Defender / Free, set at spawn time. See `role.rs`.
    pub role: Option<Role>,
    pub role_age: i32,

    // Economy
    pub ore_target: Option<Position>,
    pub ax_ore_target: Option<Position>,
    pub offensive_ore_target: Option<Position>,
    pub foundry_target: Option<Position>,
    pub ax_sink: Option<Position>,
    pub ti_sink: Option<Position>,
    pub dangling_set: HashSet<PosInt>,
    pub unreachable_dangling: HashSet<PosInt>,
    pub dangling_output: Option<Position>,

    // Repair
    pub repair_pos: Option<Position>,
    pub repaired_prev: bool,

    // Offense
    pub en_core_seen: bool,
    pub offense_target: Option<Position>,
    pub offense_turns: i32,
    pub offense_launcher: Option<Position>,
    pub last_fire: Option<(Position, i32)>,
    pub attack_tile_blacklist: HashMap<PosInt, i32>,

    // Patrol
    pub patrol_head: Option<Position>,
    pub last_seen: [i32; BOUND_RANGE],
    pub _vision_offsets: Vec<(i32, i32, i32)>,
    pub patrol_clusters: Vec<Vec<Position>>,
    pub patrol_cluster_centroids: Vec<(f64, f64)>,
    pub patrol_cluster_weights: Vec<f64>,
    pub patrol_cluster_idx: usize,
    pub patrol_pos_idx: usize,
    pub patrol_last_reroll_round: i32,
    pub patrol_dir: i32,
    pub alert: i32,
    pub econ_explore_radius_sq: i32,
    pub last_harvester_add_round: i32,

    // Scouting
    pub explore_target: Option<Position>,
    pub explore_heading: Option<(i32, i32)>,

    // Marker scan results (WS-1). Refreshed each turn by
    // `update::markers::update_markers`. See `crate::marker::Marker` for
    // the wire format. `round_lo` fields hold `round & 0xFF`; consumers
    // reconstruct freshness via `(state.round - round_lo).rem_euclid(256)`.
    pub saw_ore_claim: HashMap<PosInt, (i32, i32)>,
    pub saw_threat_at: HashMap<PosInt, (u8, u8, i32)>,
    pub saw_rendezvous_at: Option<(Position, i32)>,
    pub saw_kill_commit: Option<(Position, i32)>,

    // post_init-derived
    pub econ_radius_sq: i32,
    /// 8 perimeter tiles of the core's 3x3 block.
    pub core_edges: [Position; 8],
    /// WS-3: opening template, classified once at `post_init` from the same
    /// map features the Core uses, so all friendly bots derive the same
    /// template without inter-unit comms.
    pub opening: OpeningTemplate,
}

impl Default for Builder {
    fn default() -> Self {
        Self::new()
    }
}

impl Deref for Builder {
    type Target = UnitState;
    fn deref(&self) -> &Self::Target {
        &self.state
    }
}

impl DerefMut for Builder {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.state
    }
}

impl Builder {
    /// ct-independent allocation. Mirrors Python `Builder.__init__`.
    #[must_use]
    pub fn new() -> Self {
        let flow_history: [VecDeque<(Option<ResourceType>, Option<i32>)>; BOUND_RANGE] =
            [const { VecDeque::new() }; BOUND_RANGE];
        let in_edges: [Vec<Position>; BOUND_RANGE] = [const { Vec::new() }; BOUND_RANGE];
        let out_edges: [Vec<Position>; BOUND_RANGE] = [const { Vec::new() }; BOUND_RANGE];
        let mut vision_offsets: Vec<(i32, i32, i32)> = pyrust::vec::new!();
        for dx in -4..=4i32 {
            for dy in -4..=4i32 {
                if dx * dx + dy * dy <= GameConstants::BUILDER_BOT_VISION_RADIUS_SQ {
                    pyrust::vec::push!(vision_offsets, (dx, dy, dy * (STRIDE as i32) + dx));
                }
            }
        }
        Self {
            state: UnitState::new(),
            my_core: Position { x: 0, y: 0 },
            my_core_p: 0,
            en_core_guess: Position { x: 0, y: 0 },
            en_core_guess_p: 0,
            symmetry: None,
            env: [None; BOUND_RANGE],
            building_ids: [None; BOUND_RANGE],
            building_kind: [None; BOUND_RANGE],
            building_team: [None; BOUND_RANGE],
            hp: [0; BOUND_RANGE],
            max_hp: [0; BOUND_RANGE],
            cost_grid: [ROAD_COST; BOUND_RANGE],
            _threat_bumped: pyrust::set::new!(),
            unsafe_tiles: pyrust::set::new!(),
            buildable: [false; BOUND_RANGE],
            ti_leakage: [false; BOUND_RANGE],
            ax_leakage: [false; BOUND_RANGE],
            ti_routable: [false; BOUND_RANGE],
            ax_routable: [false; BOUND_RANGE],
            routing_extra: [0u8; BOUND_RANGE],
            _ti_harv_at: [0; BOUND_RANGE],
            _ax_harv_at: [0; BOUND_RANGE],
            _foundry_at: [0; BOUND_RANGE],
            _ti_in_count: [0; BOUND_RANGE],
            _ax_in_count: [0; BOUND_RANGE],
            posint_valid: vec![0u8; POSINT_VALID_LEN],
            vision_mask: vec![0u8; BOUND_RANGE],
            last_vision: pyrust::vec::new!(),
            reach_parent: [-1; BOUND_RANGE],
            reach_frontier: pyrust::vec::new!(),
            conv_search: AStarSearch::new(),
            ax_conv_search: AStarSearch::new(),
            bugnav: BugNav::new(),
            nav_bfs: NavBfs::new(1, 1),
            budget_telemetry: BudgetTelemetry::new(),
            bug2_path_cache: HashMap::new(),
            bug2_path_cache_order: VecDeque::new(),
            flow_history,
            in_edges,
            out_edges,
            reflect_queue: VecDeque::new(),
            nearby_buildings: pyrust::vec::new!(),
            healable_buildings: pyrust::vec::new!(),
            visible_ti_ore: pyrust::vec::new!(),
            visible_ax_ore: pyrust::vec::new!(),
            visible_harvesters: pyrust::vec::new!(),
            adjacent_to_unconnected_harvester: pyrust::set::new!(),
            adjacent_to_unconnected_foundry: pyrust::set::new!(),
            adjacent_to_harvester: pyrust::set::new!(),
            ti_harvester_adjacent: pyrust::set::new!(),
            ax_harvester_adjacent: pyrust::set::new!(),
            reaches_core: pyrust::set::new!(),
            reaches_foundry: pyrust::set::new!(),
            downstream_of_foundry: pyrust::set::new!(),
            ti_upstream: pyrust::set::new!(),
            ax_upstream: pyrust::set::new!(),
            upstream_of_dangling: pyrust::set::new!(),
            congested_junctions: pyrust::set::new!(),
            upstream_of_congestion: pyrust::set::new!(),
            my_foundries: pyrust::set::new!(),
            my_harvesters: pyrust::set::new!(),
            is_multi_input: pyrust::set::new!(),
            junctions: pyrust::set::new!(),
            adjacent_to_enemy_launcher: pyrust::set::new!(),
            enemy_turret_ray_tiles: pyrust::set::new!(),
            friendly_turret_ray_tiles: pyrust::set::new!(),
            deny_ore_neighbours: pyrust::set::new!(),
            nearest_enemy_turret: None,
            role: None,
            role_age: 0,
            ore_target: None,
            ax_ore_target: None,
            offensive_ore_target: None,
            foundry_target: None,
            ax_sink: None,
            ti_sink: None,
            dangling_set: pyrust::set::new!(),
            unreachable_dangling: pyrust::set::new!(),
            dangling_output: None,
            repair_pos: None,
            repaired_prev: true,
            en_core_seen: false,
            offense_target: None,
            offense_turns: 0,
            offense_launcher: None,
            last_fire: None,
            attack_tile_blacklist: pyrust::dict::new!(),
            patrol_head: None,
            last_seen: [0; BOUND_RANGE],
            _vision_offsets: vision_offsets,
            patrol_clusters: pyrust::vec::new!(),
            patrol_cluster_centroids: pyrust::vec::new!(),
            patrol_cluster_weights: pyrust::vec::new!(),
            patrol_cluster_idx: usize::MAX,
            patrol_pos_idx: usize::MAX,
            patrol_last_reroll_round: -1,
            patrol_dir: 1,
            alert: 0,
            econ_explore_radius_sq: 64,
            last_harvester_add_round: 0,
            explore_target: None,
            explore_heading: None,
            saw_ore_claim: HashMap::new(),
            saw_threat_at: HashMap::new(),
            saw_rendezvous_at: None,
            saw_kill_commit: None,
            econ_radius_sq: 0,
            core_edges: [Position { x: 0, y: 0 }; 8],
            opening: OpeningTemplate::DefaultBalanced,
        }
    }

    /// DEAD: `pnb` field was built but never consumed. Stub kept so the
    /// existing call site in `_apply_post_transition` doesn't need editing.
    /// No-op; eligible for full removal once call sites are cleaned up.
    pub fn update_pnb(&mut self, _i: usize) {}

    /// Position to flat index (inherent shadow of `Unit::idx` so peer code
    /// in `crate::builder::*` doesn't need to import the trait).
    #[inline]
    #[must_use]
    pub const fn idx(&self, pos: Position) -> usize {
        (pos.y as usize) * STRIDE + (pos.x as usize)
    }

    /// In-bounds check (inherent shadow of `Unit::in_bounds`).
    #[inline]
    #[must_use]
    pub const fn in_bounds(&self, pos: Position) -> bool {
        pos.x >= 0 && pos.x < self.state.width && pos.y >= 0 && pos.y < self.state.height
    }

    /// Resolved symmetry (inherent shadow of `Unit::symmetry` so peer code
    /// can use `builder.symmetry()` without importing the trait).
    #[inline]
    #[must_use]
    pub const fn symmetry(&self) -> Option<Symmetry> {
        self.symmetry
    }

    /// Inherent shadow of `Unit::symmetry_guess`.
    #[must_use]
    pub fn symmetry_guess(&self) -> Symmetry {
        for sym in [Symmetry::Rot, Symmetry::Ver, Symmetry::Hor] {
            if pyrust::vec::contains!(self.state.symmetry_candidates, &sym) {
                return sym;
            }
        }
        Symmetry::Rot
    }

    /// Cached enemy core guess.
    #[inline]
    #[must_use]
    pub const fn en_core_guess(&self) -> Position {
        self.en_core_guess
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn get_env(&self, pos: Position) -> Option<Environment> {
        self.env[self.idx(pos)]
    }

    /// PosInt-native variant of `get_env`. Skips `idx_of` conversion.
    #[pyrust::inline]
    #[must_use]
    #[inline]
    pub const fn get_env_p(&self, p: PosInt) -> Option<Environment> {
        self.env[p as usize]
    }

    /// Kind + team at `pos`, or `None` if no building / not in vision.
    #[must_use]
    pub fn get_building(&self, pos: Position) -> Option<(EntityType, Team)> {
        let i = self.idx(pos);
        // Explicit unwrap-or-return-None — pyrust-translate drops the `?`
        // operator inside `Some((a?, b?))` and emits the tuple unconditionally.
        let kind = self.building_kind[i];
        let team = self.building_team[i];
        if pyrust::is_none!(kind) || pyrust::is_none!(team) {
            return None;
        }
        Some((pyrust::unwrap!(kind), pyrust::unwrap!(team)))
    }

    /// PosInt-native variant of `get_building`.
    #[must_use]
    #[inline]
    pub fn get_building_p(&self, p: PosInt) -> Option<(EntityType, Team)> {
        let i = p as usize;
        let kind = self.building_kind[i];
        let team = self.building_team[i];
        if pyrust::is_none!(kind) || pyrust::is_none!(team) {
            return None;
        }
        Some((pyrust::unwrap!(kind), pyrust::unwrap!(team)))
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn kind_at(&self, pos: Position) -> Option<EntityType> {
        self.building_kind[self.idx(pos)]
    }

    /// PosInt-native variant of `kind_at`.
    #[pyrust::inline]
    #[must_use]
    #[inline]
    pub const fn kind_at_p(&self, p: PosInt) -> Option<EntityType> {
        self.building_kind[p as usize]
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn team_at(&self, pos: Position) -> Option<Team> {
        self.building_team[self.idx(pos)]
    }

    /// PosInt-native variant of `team_at`.
    #[pyrust::inline]
    #[must_use]
    #[inline]
    pub const fn team_at_p(&self, p: PosInt) -> Option<Team> {
        self.building_team[p as usize]
    }

    #[must_use]
    pub const fn get_cost(&self, pos: Position) -> i32 {
        self.cost_grid[self.idx(pos)]
    }

    /// PosInt-native variant of `get_cost`.
    #[pyrust::inline]
    #[must_use]
    #[inline]
    pub const fn get_cost_p(&self, p: PosInt) -> i32 {
        self.cost_grid[p as usize]
    }

    #[must_use]
    pub const fn is_passable(&self, pos: Position) -> bool {
        if pos.x < 0 || pos.x >= self.state.width || pos.y < 0 || pos.y >= self.state.height {
            return false;
        }
        self.cost_grid[self.idx(pos)] != INF
    }

    /// PosInt-native variant of `is_passable`.
    #[pyrust::inline]
    #[must_use]
    #[inline]
    pub const fn is_passable_p(&self, p: PosInt) -> bool {
        self.cost_grid[p as usize] != INF
    }

    /// `vision_mask`-backed in-vision check. O(1) array lookup, avoids
    /// calling `ct.is_in_vision` (a Python→engine boundary crossing).
    #[pyrust::inline]
    #[must_use]
    pub fn is_in_vision_p(&self, p: PosInt) -> bool {
        self.vision_mask[p as usize] != 0
    }

    /// Position-form wrapper around `is_in_vision_p`.
    #[must_use]
    pub fn is_in_vision(&self, pos: Position) -> bool {
        self.is_in_vision_p(idx_of(pos))
    }

    #[must_use]
    pub fn is_reachable(&self, pos: Position) -> bool {
        self.is_reachable_p(idx_of(pos))
    }

    /// PosInt-native variant of `is_reachable`.
    #[must_use]
    pub fn is_reachable_p(&self, p: PosInt) -> bool {
        let my_i = (self.state.my_pos.y * (STRIDE as i32)) + self.state.my_pos.x;
        if self.reach_parent[p as usize] == -1 || self.reach_parent[my_i as usize] == -1 {
            return false;
        }
        find_ro(&self.reach_parent, p) == find_ro(&self.reach_parent, my_i)
    }

    #[must_use]
    pub const fn is_walkable(&self, pos: Position) -> bool {
        if !self.is_passable(pos) {
            return false;
        }
        matches!(
            self.building_kind[self.idx(pos)],
            Some(
                EntityType::Conveyor
                    | EntityType::Road
                    | EntityType::Splitter
                    | EntityType::ArmouredConveyor
                    | EntityType::Bridge
            )
        )
    }

    /// PosInt-native variant of `is_walkable`.
    #[must_use]
    #[inline]
    pub const fn is_walkable_p(&self, p: PosInt) -> bool {
        if self.cost_grid[p as usize] == INF {
            return false;
        }
        matches!(
            self.building_kind[p as usize],
            Some(
                EntityType::Conveyor
                    | EntityType::Road
                    | EntityType::Splitter
                    | EntityType::ArmouredConveyor
                    | EntityType::Bridge
            )
        )
    }

    #[must_use]
    #[inline]
    pub fn is_buildable_p(&self, p: PosInt) -> bool {
        let i = p as usize;
        self.env[i] != Some(Environment::Wall)
            && (pyrust::is_none!(self.building_team[i])
                || self.building_team[i] == Some(self.state.my_team))
    }

    #[must_use]
    pub fn get_in_edges(&self, pos: Position) -> Vec<Position> {
        pyrust::clone!(self.in_edges[self.idx(pos)])
    }

    #[must_use]
    pub fn get_out_edges(&self, pos: Position) -> Vec<Position> {
        pyrust::clone!(self.out_edges[self.idx(pos)])
    }

    #[must_use]
    pub fn is_buildable(&self, pos: Position) -> bool {
        self.is_buildable_p(idx_of(pos))
    }

    #[must_use]
    pub fn is_friendly_turret(&self, pos: Position) -> bool {
        self.is_friendly_turret_p(idx_of(pos))
    }

    #[must_use]
    #[inline]
    pub fn is_friendly_turret_p(&self, p: PosInt) -> bool {
        let i = p as usize;
        let Some(kind) = self.building_kind[i] else {
            return false;
        };
        if matches!(
            kind,
            EntityType::Conveyor
                | EntityType::Road
                | EntityType::Splitter
                | EntityType::ArmouredConveyor
                | EntityType::Bridge
        ) {
            return false;
        }
        self.building_team[i] == Some(self.state.my_team)
    }

    #[must_use]
    pub fn is_enemy_building(&self, pos: Position) -> bool {
        self.is_enemy_building_p(idx_of(pos))
    }

    #[must_use]
    #[inline]
    pub fn is_enemy_building_p(&self, p: PosInt) -> bool {
        match self.building_team[p as usize] {
            Some(t) => t != self.state.my_team,
            None => false,
        }
    }

    #[must_use]
    pub fn leads_to_enemy_building(&self, pos: Position) -> bool {
        let i = self.idx(pos);
        if self.building_team[i] != Some(self.state.my_team) {
            return false;
        }
        // Routing buildings (Conveyor / ArmouredConveyor / Bridge) have a
        // single output edge; non-routing kinds have empty `out_edges`.
        // Splitters have 3 outputs and are deliberately excluded — only
        // single-target routers count as "leading to" downstream.
        let kind = self.building_kind[i];
        if !matches!(
            kind,
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge)
        ) {
            return false;
        }
        if pyrust::vec::is_empty!(self.out_edges[i]) {
            return false;
        }
        let output_location = self.out_edges[i][0];
        if !self.in_bounds(output_location) {
            return false;
        }
        // Ignore enemy markers — 1HP placeholders, not real infrastructure.
        // Our stack destroys the marker on arrival and the tile clears.
        let oi = self.idx(output_location);
        if self.building_kind[oi] == Some(EntityType::Marker) {
            return false;
        }
        self.is_enemy_building(output_location)
    }

    /// Drain the reachability frontier, expanding admitted tiles into their
    /// 8-connected non-WALL neighbours up to `K_PER_TURN` pops.
    pub fn update_reachability(&mut self) {
        update_reachability(
            &mut self.reach_parent,
            &mut self.reach_frontier,
            &self.env,
            self.state.width,
            self.state.height,
        );
    }

    /// Mid-turn invariant fix-up after `ct.destroy(pos)`.
    pub fn apply_local_destroy(&mut self, pos: Position) {
        vision_apply_local_destroy(self, pos);
    }

    /// Run the Ti A* search. Constructs an `EconAstarCtx` from this
    /// builder's borrowed state and forwards to `conv_search.search`.
    /// `budget_us` is the absolute turn-elapsed CPU threshold (μs); the
    /// search returns `Pending` if exceeded mid-loop and resumes on the
    /// next call with the same `(start, target, resource)`.
    pub fn ti_conv_astar(
        &mut self,
        ct: &mut Controller<'_>,
        start: Position,
        target: Position,
        resource: ResourceType,
        budget_us: u64,
    ) -> AstarStep {
        let mut ctx = self.make_econ_ctx();
        let step = self
            .conv_search
            .search(ct, start, target, resource, budget_us, &mut ctx);
        self.absorb_econ_ctx(ctx);
        step
    }

    /// Run the Ax A* search. Same shape as `ti_conv_astar` but goes
    /// through `ax_conv_search`.
    pub fn ax_conv_astar(
        &mut self,
        ct: &mut Controller<'_>,
        start: Position,
        target: Position,
        resource: ResourceType,
        budget_us: u64,
    ) -> AstarStep {
        let mut ctx = self.make_econ_ctx();
        let step = self
            .ax_conv_search
            .search(ct, start, target, resource, budget_us, &mut ctx);
        self.absorb_econ_ctx(ctx);
        step
    }

    fn make_econ_ctx(&self) -> EconAstarCtx {
        EconAstarCtx {
            ax_routable: pyrust::clone!(self.ax_routable),
            ti_routable: pyrust::clone!(self.ti_routable),
            routing_extra: pyrust::clone!(self.routing_extra),
            reach_parent: pyrust::clone!(self.reach_parent),
            my_pos: self.state.my_pos,
            nearby_tiles: pyrust::clone!(self.state.nearby_tiles),
            all_bots: pyrust::clone!(self.state.all_bots),
        }
    }

    fn absorb_econ_ctx(&mut self, ctx: EconAstarCtx) {
        // The search may have run path-halving in `reach_parent`; sync back so
        // future UF calls see the compressed paths.
        self.reach_parent = ctx.reach_parent;
    }

    /// Sync NavBfs passability from cost_grid for tiles in
    /// `state.nearby_tiles`. cost_grid `!= INF` means walkable.
    /// Cheap: O(60) per turn, set_passable no-ops when unchanged.
    pub fn sync_nav_bfs_passable(&mut self) {
        let w = self.state.width;
        let my_team = self.state.my_team;
        let nearby = pyrust::clone!(self.state.nearby_tiles);
        for pos in &nearby {
            let real_i = pos.y * w + pos.x;
            let pi = idx_of(*pos) as usize;
            let walkable = self.cost_grid[pi] != INF;
            self.nav_bfs.set_passable(real_i, walkable);
            // Tiebreak preference: friendly Road tiles. Empty tiles and
            // other passable buildings won't be flagged.
            let is_road = self.building_kind[pi] == Some(EntityType::Road)
                && self.building_team[pi] == Some(my_team);
            self.nav_bfs.set_road(real_i, is_road);
        }
    }

    /// One step toward `target` via bug2 + dp_step. BFS pre-pass disabled
    /// (was costing ~30% of bot time / 1070ms per builder over 1600 turns;
    /// gameplay quality on labyrinth was modest, but TLE on the actual
    /// server made it net-negative). v56 plays on the ladder bug2-only.
    pub fn bugnav_step(&mut self, target: Position) -> Option<Position> {
        let Self {
            bugnav,
            cost_grid,
            state,
            bug2_path_cache,
            bug2_path_cache_order,
            unsafe_tiles,
            ..
        } = self;
        let mut ctx = NavCtx {
            my_pos: state.my_pos,
            cost_grid,
            w: state.width,
            h: state.height,
            nearby_tiles: &state.nearby_tiles,
            all_bots: &state.all_bots,
            path_cache: bug2_path_cache,
            path_cache_order: bug2_path_cache_order,
            unsafe_tiles,
        };
        bugnav.step_safe(&mut ctx, target)
    }

    const fn _refresh_ti_leakage(&mut self, i: usize) {
        let new = self._ax_harv_at[i] > 0 || self._foundry_at[i] > 0;
        if new != self.ti_leakage[i] {
            self.ti_leakage[i] = new;
            self.ti_routable[i] = self.buildable[i] && !new;
        }
    }

    const fn _refresh_ax_leakage(&mut self, i: usize) {
        let new = self._ti_harv_at[i] > 0;
        if new != self.ax_leakage[i] {
            self.ax_leakage[i] = new;
            self.ax_routable[i] = self.buildable[i] && !new;
        }
    }

    pub fn _bump_ti_harv(&mut self, pos: Position, delta: i32) {
        for d in DIR4 {
            let n = pos.add(d);
            if !self.in_bounds(n) {
                continue;
            }
            let ni = self.idx(n);
            let old = self._ti_harv_at[ni];
            self._ti_harv_at[ni] += delta;
            let new = self._ti_harv_at[ni];
            self._refresh_ax_leakage(ni);
            if old == 0 && new > 0 {
                pyrust::set::add!(self.ti_harvester_adjacent, idx_of(n));
                self._reeval_ti_upstream(n);
            } else if old > 0 && new == 0 {
                pyrust::set::remove!(self.ti_harvester_adjacent, &idx_of(n));
                self._reeval_ti_upstream(n);
            }
        }
    }

    pub fn _bump_ax_harv(&mut self, pos: Position, delta: i32) {
        for d in DIR4 {
            let n = pos.add(d);
            if !self.in_bounds(n) {
                continue;
            }
            let ni = self.idx(n);
            let old = self._ax_harv_at[ni];
            self._ax_harv_at[ni] += delta;
            let new = self._ax_harv_at[ni];
            self._refresh_ti_leakage(ni);
            if old == 0 && new > 0 {
                pyrust::set::add!(self.ax_harvester_adjacent, idx_of(n));
                self._reeval_ax_upstream(n);
            } else if old > 0 && new == 0 {
                pyrust::set::remove!(self.ax_harvester_adjacent, &idx_of(n));
                self._reeval_ax_upstream(n);
            }
        }
    }

    pub fn _reeval_ti_upstream(&mut self, t: Position) {
        let i = self.idx(t);
        let has_seed = self._ti_harv_at[i] > 0 && !pyrust::vec::is_empty!(self.out_edges[i]);
        let target = has_seed || self._ti_in_count[i] > 0;
        self._set_ti_upstream(t, target);
    }

    pub fn _reeval_ax_upstream(&mut self, t: Position) {
        let i = self.idx(t);
        let has_seed = self._ax_harv_at[i] > 0 && !pyrust::vec::is_empty!(self.out_edges[i]);
        let target = has_seed || self._ax_in_count[i] > 0;
        self._set_ax_upstream(t, target);
    }

    fn _set_ti_upstream(&mut self, t: Position, want: bool) {
        let is_in = pyrust::vec::contains!(self.ti_upstream, &idx_of(t));
        if want == is_in {
            return;
        }
        let i = self.idx(t);
        let delta: i32;
        if want {
            pyrust::set::add!(self.ti_upstream, idx_of(t));
            delta = 1;
        } else {
            pyrust::set::remove!(self.ti_upstream, &idx_of(t));
            delta = -1;
        }
        let outs: Vec<Position> = pyrust::clone!(self.out_edges[i]);
        for out in &outs {
            let oi = self.idx(*out);
            self._ti_in_count[oi] += delta;
            self._reeval_ti_upstream(*out);
        }
        for out in &outs {
            self._check_dangling(*out, "ti_upstream_change");
        }
    }

    fn _set_ax_upstream(&mut self, t: Position, want: bool) {
        let is_in = pyrust::vec::contains!(self.ax_upstream, &idx_of(t));
        if want == is_in {
            return;
        }
        let i = self.idx(t);
        let delta: i32;
        if want {
            pyrust::set::add!(self.ax_upstream, idx_of(t));
            delta = 1;
        } else {
            pyrust::set::remove!(self.ax_upstream, &idx_of(t));
            delta = -1;
        }
        let outs: Vec<Position> = pyrust::clone!(self.out_edges[i]);
        for out in &outs {
            let oi = self.idx(*out);
            self._ax_in_count[oi] += delta;
            self._reeval_ax_upstream(*out);
        }
        for out in &outs {
            self._check_dangling(*out, "ax_upstream_change");
        }
    }

    pub fn _on_in_edge_added(&mut self, t: Position, f: Position) {
        let i = self.idx(t);
        if pyrust::vec::contains!(self.ti_upstream, &idx_of(f)) {
            self._ti_in_count[i] += 1;
            self._reeval_ti_upstream(t);
        }
        if pyrust::vec::contains!(self.ax_upstream, &idx_of(f)) {
            self._ax_in_count[i] += 1;
            self._reeval_ax_upstream(t);
        }
    }

    pub fn _on_in_edge_removed(&mut self, t: Position, f: Position) {
        let i = self.idx(t);
        if pyrust::vec::contains!(self.ti_upstream, &idx_of(f)) {
            self._ti_in_count[i] -= 1;
            self._reeval_ti_upstream(t);
        }
        if pyrust::vec::contains!(self.ax_upstream, &idx_of(f)) {
            self._ax_in_count[i] -= 1;
            self._reeval_ax_upstream(t);
        }
    }

    pub fn _on_out_edges_changed(&mut self, pos: Position) {
        self._reeval_ti_upstream(pos);
        self._reeval_ax_upstream(pos);
    }

    pub fn _bump_foundry(&mut self, pos: Position, delta: i32) {
        for d in DIR4 {
            let n = pos.add(d);
            if self.in_bounds(n) {
                let ni = self.idx(n);
                self._foundry_at[ni] += delta;
                self._refresh_ti_leakage(ni);
            }
        }
    }

    pub fn _check_multi_input(&mut self, t: Position) {
        let idx = self.idx(t);
        if pyrust::len!(self.in_edges[idx]) >= 2 {
            pyrust::set::add!(self.is_multi_input, idx_of(t));
        } else {
            pyrust::set::remove!(self.is_multi_input, &idx_of(t));
        }
    }

    fn _is_flow_consumer(&self, pos: Position) -> bool {
        let i = self.idx(pos);
        let Some(kind) = self.building_kind[i] else {
            return false;
        };
        if self.building_team[i] != Some(self.state.my_team) {
            return false;
        }
        matches!(
            kind,
            EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Bridge
                | EntityType::Splitter
                | EntityType::Foundry
                | EntityType::Core
                | EntityType::Gunner
                | EntityType::Sentinel
                | EntityType::Breach
                | EntityType::Launcher
        )
    }

    fn _splitter_satisfied(&self, splitter_pos: Position) -> bool {
        let mut count = 0;
        for out in &self.out_edges[self.idx(splitter_pos)] {
            if self._is_flow_consumer(*out) {
                count += 1;
                if count >= 2 {
                    return true;
                }
            }
        }
        false
    }

    pub fn _check_dangling(&mut self, t: Position, _trigger: &str) {
        let i = self.idx(t);
        let kind = self.building_kind[i];
        let team = self.building_team[i];
        let env_i = self.env[i];
        let my_team = self.state.my_team;
        let admit_terrain = match kind {
            None if env_i != Some(Environment::Wall) => true,
            Some(EntityType::Road) if team == Some(my_team) => true,
            Some(EntityType::Marker) => true,
            _ => false,
        };
        if !admit_terrain {
            pyrust::set::remove!(self.dangling_set, &idx_of(t));
            pyrust::set::remove!(self.unreachable_dangling, &idx_of(t));
            return;
        }

        let unconn_adj = pyrust::vec::contains!(self.adjacent_to_unconnected_harvester, &idx_of(t))
            || pyrust::vec::contains!(self.adjacent_to_unconnected_foundry, &idx_of(t));
        let mut feeders_unsatisfied = false;
        let in_edges_t: Vec<Position> = pyrust::clone!(self.in_edges[i]);
        for f in &in_edges_t {
            let fi_check = idx_of(*f);
            let in_ti = pyrust::set::contains!(self.ti_upstream, &fi_check);
            let in_ax = pyrust::set::contains!(self.ax_upstream, &fi_check);
            if !in_ti && !in_ax {
                continue;
            }
            let fi = self.idx(*f);
            let is_satisfied_splitter = self.building_kind[fi] == Some(EntityType::Splitter)
                && self._splitter_satisfied(*f);
            if !is_satisfied_splitter {
                feeders_unsatisfied = true;
                break;
            }
        }
        let is_dangling = unconn_adj || feeders_unsatisfied;

        if is_dangling {
            if !pyrust::vec::contains!(self.unreachable_dangling, &idx_of(t)) {
                pyrust::set::add!(self.dangling_set, idx_of(t));
            }
        } else {
            pyrust::set::remove!(self.dangling_set, &idx_of(t));
            pyrust::set::remove!(self.unreachable_dangling, &idx_of(t));
        }
    }

    /// DEAD: pnb field removed; no-op stub kept for caller convenience.
    fn pnb_fix_boundary(&mut self, _cx: i32, _cy: i32, _w: i32, _h: i32) {}

    /// Mirror `my_core` under `symmetry_guess`.
    fn refresh_symmetry_cache(&mut self) {
        let count = pyrust::len!(self.state.symmetry_candidates);
        self.symmetry = if count == 1 {
            pyrust::copied!(pyrust::next!(pyrust::iter!(self.state.symmetry_candidates)))
        } else {
            None
        };
        let guess = self.symmetry_guess();
        self.en_core_guess = guess.action(self.my_core, self.state.width, self.state.height);
        self.en_core_guess_p = idx_of(self.en_core_guess);
    }
}

impl Unit for Builder {
    fn unit_state(&self) -> &UnitState {
        &self.state
    }

    fn unit_state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn post_init(&mut self, ct: &mut Controller<'_>) {
        // Builder's per-turn `update_vision` does the symmetry narrowing
        // incrementally against its persistent grid, so the post_init pass
        // skips `narrow_symmetry_from_vision` (otherwise both run on the
        // same turn-1 observations).
        self.state.init_static_state(ct);
        let core = self.resolve_my_core(ct);
        self.set_my_core(core);

        let r2 = self.state.rng.random();
        self.patrol_dir = if r2 < 0.5 { 1 } else { -1 };

        // Seed initial patrol cluster with the 4 corners of the core 3x3 footprint.
        for (dx, dy) in [(-1, -1), (1, -1), (-1, 1), (1, 1)] {
            let p = Position {
                x: self.my_core.x + dx,
                y: self.my_core.y + dy,
            };
            crate::builder::patrol::insert_into_clusters(
                &mut self.patrol_clusters,
                &mut self.patrol_cluster_centroids,
                &mut self.patrol_cluster_weights,
                p,
                crate::builder::patrol::HARVESTER_WEIGHT,
            );
        }

        let s = pyrust::float!(pyrust::max!(self.state.width, self.state.height));
        self.econ_radius_sq = pyrust::round!(((0.7 * s) * (0.7 * s))) as i32;

        // BFS pre-pass disabled in bugnav_step — skip the expensive
        // pnb-table init that fed it. On a 50×50 map this was ~22k inner-
        // loop ops in Python on round 1, contributing to the first-turn
        // TLE that killed builders before they could update_ore_target.
        // The NavBfs field still exists (cheap 1×1 stub) for API compat.

        // Mark off-map cells as INF (so bug2 won't route through them) and
        // populate `posint_valid` for in-bounds tiles. Both loops use
        // slice-fill rather than per-element writes — Python list[a:b] =
        // [v]*n is a single C-level memcpy instead of (h*w) PyLong-boxed
        // setitem calls. ~250x speedup, ~1ms saved on a 50x50 map.
        let w = self.state.width;
        let h = self.state.height;
        let w_us = w as usize;
        let h_us = h as usize;
        // cost_grid: tail of each in-bounds row (cols w..STRIDE) → INF;
        // every column in fully off-map rows (y..MAX_WIDTH) → INF.
        for y in 0..h_us {
            let base = y * STRIDE;
            pyrust::vec::fill_range!(self.cost_grid, base + w_us, base + STRIDE, INF);
        }
        for y in h_us..MAX_WIDTH {
            let base = y * STRIDE;
            pyrust::vec::fill_range!(self.cost_grid, base, base + STRIDE, INF);
        }
        // posint_valid: 1 for cols 0..w of rows 0..h.
        for y in 0..h_us {
            let row_base = y * STRIDE;
            pyrust::bytearray::fill_range!(self.posint_valid, row_base, row_base + w_us, 1);
        }

        // (drewfett v1000: hardcoded openings dropped — `known_map` removed.)

        // Core perimeter — 8 tiles in DIR8 order.
        for (i, d) in pyrust::enumerate!(pyrust::iter!(DIR8)) {
            self.core_edges[i] = self.my_core.add(*d);
        }

        // pnb_fix_boundary loops dropped — pnb is dead state, the function
        // is a no-op stub; the ~99 Python calls per builder were sunk
        // overhead.

        self.refresh_symmetry_cache();

        // WS-3: classify opening template using the same map features the
        // Core uses. Deterministic across all friendly bots, no comms needed.
        let _scope = Scope::new_timed("opening_classify");
        self.opening = classify_opening(
            self.state.width,
            self.state.height,
            self.my_core,
            self.en_core_guess,
            ct,
        );
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        self.budget_telemetry.start_turn();
        self.state.cache_per_turn_state(ct);
        self.state.check_symmetry_marker(ct);
        self.refresh_symmetry_cache();

        let _g = Scope::new_timed("body");
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("id"),
                serde_json::Value::Number(serde_json::Number::from(self.state.my_id))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("pos"),
                auto_wrap_position(self.state.my_pos)
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("round"),
                serde_json::Value::Number(serde_json::Number::from(self.state.round))
            );
            log("Builder {id} pos={pos} round={round}", args);
        }

        trace::enter(ct, "update");
        update(self, ct);
        trace::exit(ct, "update");
        trace::enter(ct, "begin_offense");
        begin_turn_offense(self, ct);
        trace::exit(ct, "begin_offense");

        if DEBUG_DUMP {
            dump_state(self, ct);
        }

        // Time-budget bail. update() must complete (its derived caches feed
        // every task gate next turn), but tasks are skippable. If we burned
        // most of the 2ms turn budget on update (turn 1 / mid-game spawn /
        // chain-busy update_vision), skip task dispatch this turn rather
        // than risk hitting the engine's hard cap mid-bug2 and losing the
        // commit. Bot stays alive, makes no action this turn.
        let elapsed = pyrust::unwrap_or!(ct.get_cpu_time_elapsed(), 0);
        if elapsed > 2000 {
            return;
        }

        let role = pyrust::expect!(self.role, "role must be set after update");
        {
            let _g = Scope::new_timed("tasks");
            trace::enter(ct, "tasks");
            let policy = policy_for_role(role);
            run_policy(self, ct, policy);
            trace::exit(ct, "tasks");
        }
        {
            let _g = Scope::new_timed("hooks");
            {
                let _g = Scope::new_timed("indicators");
                indicators(self, ct);
            }
            // End-of-turn heal pass for Defender bots only — Free bots
            // are likely deep in enemy territory and shouldn't burn Ti
            // healing local stuff at the cost of their offensive route.
            if role == Role::Defender {
                let _g = Scope::new_timed("heal");
                trace::enter(ct, "heal");
                end_of_turn_heal(self, ct);
                trace::exit(ct, "heal");
            }
            {
                let _g = Scope::new_timed("symmetry");
                trace::enter(ct, "symmetry");
                end_of_turn_propagate_symmetry(self, ct);
                trace::exit(ct, "symmetry");
            }
        }
        self.budget_telemetry.record(ct);
    }
}

impl CoreAwareUnit for Builder {
    fn my_core_pos(&self) -> Position {
        self.my_core
    }

    fn set_my_core(&mut self, pos: Position) {
        self.my_core = pos;
        self.my_core_p = idx_of(pos);
    }

    fn resolve_my_core(&mut self, ct: &mut Controller<'_>) -> Position {
        // Scan vision for an allied core building.
        let my_team = self.state.my_team;
        for bid in pyrust::unwrap!(ct.get_nearby_buildings(None)) {
            if pyrust::unwrap!(ct.get_team(Some(bid))) == my_team
                && pyrust::unwrap!(ct.get_entity_type(Some(bid))) == EntityType::Core
            {
                return pyrust::unwrap!(ct.get_position(Some(bid)));
            }
        }
        pyrust::unwrap!(ct.get_position(None))
    }
}
