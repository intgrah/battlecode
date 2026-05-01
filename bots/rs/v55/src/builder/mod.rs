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
use crate::builder::algorithms::econ_astar::EconAstarCtx;
use crate::builder::algorithms::nav::{BugNav, NavCtx};
use crate::builder::algorithms::reachability::{find_ro, update_reachability};
use crate::builder::hooks::heal::end_of_turn_heal;
use crate::builder::hooks::indicators::indicators;
use crate::builder::hooks::propagate_symmetry::end_of_turn_propagate_symmetry;
use crate::builder::role::Role;
use crate::builder::tasks::_policy::run_policy;
use crate::builder::tasks::offense::helpers::begin_turn_offense;
use crate::builder::tasks::policy_for_role;
use crate::builder::update::update;
use crate::builder::update::vision::apply_local_destroy as vision_apply_local_destroy;
use crate::config::{DEBUG_DUMP, HARDCODE};
use crate::hardcode::identify::{KnownMap, identify_map};
use crate::unit::{CoreAwareUnit, Unit, UnitState};
use crate::util::constants::{INF, MAX_N, MAX_WIDTH, ROAD_COST};
use crate::util::debug::{Scope, debug as log};
use crate::util::directions::{DIR4, DIR8, DIR8_DELTA};
use crate::util::symmetry::Symmetry;
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
    /// Mirror of `my_core` under the chosen `symmetry_guess` — cached at
    /// the start of each turn so `builder.en_core_guess` (no parens) and
    /// `builder.en_core_guess` (the trait method) are interchangeable.
    pub en_core_guess: Position,
    /// `Some(s)` once a single symmetry remains in `state.symmetry_candidates`,
    /// else `None`. Cached field for peer code that uses `if builder.symmetry`.
    pub symmetry: Option<Symmetry>,

    /// Wall / Empty / `OreTitanium` / `OreAxionite` per tile (None = unobserved).
    pub env: [Option<Environment>; MAX_N],
    /// Cached entity ids per tile, for change detection.
    pub building_ids: [Option<i32>; MAX_N],
    /// Building kind per tile (None when no building / not in vision).
    pub building_kind: [Option<EntityType>; MAX_N],
    /// Owning team per tile, parallel to `building_kind`.
    pub building_team: [Option<Team>; MAX_N],
    /// HP of building on each tile.
    pub hp: [i32; MAX_N],
    /// Max HP of building on each tile.
    pub max_hp: [i32; MAX_N],

    /// Movement cost per tile.
    pub cost_grid: [i32; MAX_N],
    /// Flat indices currently carrying a threat penalty in `cost_grid`.
    pub _threat_bumped: HashSet<usize>,

    /// True iff a routable building could be placed on this tile.
    pub buildable: [bool; MAX_N],
    /// True iff Ti routing through this tile would mix with Ax.
    pub ti_leakage: [bool; MAX_N],
    /// True iff Ax routing through this tile would mix with Ti.
    pub ax_leakage: [bool; MAX_N],
    /// `buildable[i] && !ti_leakage[i]`.
    pub ti_routable: [bool; MAX_N],
    /// `buildable[i] && !ax_leakage[i]`.
    pub ax_routable: [bool; MAX_N],
    /// Per-tile additive A* relaxation cost (0 normally, 4 for enemy roads).
    pub routing_extra: [u8; MAX_N],

    pub _ti_harv_at: [i32; MAX_N],
    pub _ax_harv_at: [i32; MAX_N],
    pub _foundry_at: [i32; MAX_N],

    pub _ti_in_count: [i32; MAX_N],
    pub _ax_in_count: [i32; MAX_N],

    /// Passable-neighbour list per tile (flat indices). Pre-built for full
    /// `MAX_WIDTH × MAX_WIDTH`; trimmed in `post_init` for the actual map.
    pub pnb: [Vec<i32>; MAX_N],

    /// Union-find parent pointer for incremental reachability.
    pub reach_parent: [i32; MAX_N],
    /// Frontier of admitted-but-unexpanded tiles. Persists across turns.
    pub reach_frontier: Vec<i32>,

    /// A* search instance for Ti chain routing.
    pub conv_search: AStarSearch,
    /// A* search instance for Ax chain routing.
    pub ax_conv_search: AStarSearch,

    /// Bug2-bounded planner + `dp_step` path-follower. Persists across turns.
    pub bugnav: BugNav,

    /// Per-tile rolling window of `(resource, stack_id)` observations.
    pub flow_history: [VecDeque<(Option<ResourceType>, Option<i32>)>; MAX_N],

    /// Structural feeders: `in_edges[i]` lists positions that output onto tile i.
    pub in_edges: [Vec<Position>; MAX_N],
    /// Structural consumers: `out_edges[i]` lists positions that tile i outputs to.
    pub out_edges: [Vec<Position>; MAX_N],

    /// Tiles to mirror via symmetry once it's resolved (rate-limited).
    pub reflect_queue: VecDeque<usize>,

    // Ephemeral (recomputed each turn, but stored to avoid re-allocation cost).
    pub nearby_buildings: Vec<Position>,
    pub healable_buildings: Vec<Position>,
    pub adjacent_to_unconnected_harvester: HashSet<Position>,
    pub adjacent_to_harvester: HashSet<Position>,
    pub ti_harvester_adjacent: HashSet<Position>,
    pub ax_harvester_adjacent: HashSet<Position>,
    pub reaches_core: HashSet<Position>,
    pub reaches_foundry: HashSet<Position>,
    pub ti_upstream: HashSet<Position>,
    pub ax_upstream: HashSet<Position>,
    pub upstream_of_dangling: HashSet<Position>,
    pub congested_junctions: HashSet<Position>,
    pub upstream_of_congestion: HashSet<Position>,
    pub my_foundries: HashSet<Position>,
    pub my_harvesters: HashSet<Position>,
    pub is_multi_input: HashSet<Position>,
    pub junctions: HashSet<Position>,
    pub adjacent_to_enemy_launcher: HashSet<Position>,
    pub enemy_turret_ray_tiles: HashSet<Position>,
    pub friendly_turret_ray_tiles: HashSet<Position>,
    pub deny_ore_neighbours: HashSet<Position>,
    pub nearest_enemy_turret: Option<Position>,

    // Role
    pub role: Option<Role>,
    pub role_age: i32,

    // Economy
    pub ore_target: Option<Position>,
    pub ax_ore_target: Option<Position>,
    pub offensive_ore_target: Option<Position>,
    pub foundry_target: Option<Position>,
    pub ax_sink: Option<Position>,
    pub ti_sink: Option<Position>,
    pub dangling_set: HashSet<Position>,
    pub unreachable_dangling: HashSet<Position>,
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
    pub attack_tile_blacklist: HashMap<Position, i32>,

    // Patrol
    pub patrol_head: Option<Position>,
    pub last_seen: [i32; MAX_N],
    pub _vision_offsets: Vec<(i32, i32, i32)>,

    // Scouting
    pub explore_target: Option<Position>,
    pub explore_heading: Option<(i32, i32)>,

    // post_init-derived
    pub opportunistic: bool,
    pub econ_radius_sq: i32,
    pub known_map: Option<KnownMap>,
    /// 8 perimeter tiles of the core's 3x3 block.
    pub core_edges: [Position; 8],
}

impl Default for Builder {
    fn default() -> Self {
        Self::new()
    }
}

impl Deref for Builder {
    type Target = UnitState;
    #[pyrust::inline]
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
        let pnb = Self::build_initial_pnb();
        let flow_history: [VecDeque<(Option<ResourceType>, Option<i32>)>; MAX_N] =
            [const { VecDeque::new() }; MAX_N];
        let in_edges: [Vec<Position>; MAX_N] = [const { Vec::new() }; MAX_N];
        let out_edges: [Vec<Position>; MAX_N] = [const { Vec::new() }; MAX_N];
        let mut vision_offsets: Vec<(i32, i32, i32)> = pyrust::vec::new!();
        for dx in -4..=4i32 {
            for dy in -4..=4i32 {
                if dx * dx + dy * dy <= GameConstants::BUILDER_BOT_VISION_RADIUS_SQ {
                    pyrust::vec::push!(vision_offsets, (dx, dy, dy * (MAX_WIDTH as i32) + dx));
                }
            }
        }
        Self {
            state: UnitState::new(),
            my_core: Position { x: 0, y: 0 },
            en_core_guess: Position { x: 0, y: 0 },
            symmetry: None,
            env: [None; MAX_N],
            building_ids: [None; MAX_N],
            building_kind: [None; MAX_N],
            building_team: [None; MAX_N],
            hp: [0; MAX_N],
            max_hp: [0; MAX_N],
            cost_grid: [ROAD_COST; MAX_N],
            _threat_bumped: pyrust::set::new!(),
            buildable: [false; MAX_N],
            ti_leakage: [false; MAX_N],
            ax_leakage: [false; MAX_N],
            ti_routable: [false; MAX_N],
            ax_routable: [false; MAX_N],
            routing_extra: [0u8; MAX_N],
            _ti_harv_at: [0; MAX_N],
            _ax_harv_at: [0; MAX_N],
            _foundry_at: [0; MAX_N],
            _ti_in_count: [0; MAX_N],
            _ax_in_count: [0; MAX_N],
            pnb,
            reach_parent: [-1; MAX_N],
            reach_frontier: pyrust::vec::new!(),
            conv_search: AStarSearch::new(),
            ax_conv_search: AStarSearch::new(),
            bugnav: BugNav::new(),
            flow_history,
            in_edges,
            out_edges,
            reflect_queue: VecDeque::new(),
            nearby_buildings: pyrust::vec::new!(),
            healable_buildings: pyrust::vec::new!(),
            adjacent_to_unconnected_harvester: pyrust::set::new!(),
            adjacent_to_harvester: pyrust::set::new!(),
            ti_harvester_adjacent: pyrust::set::new!(),
            ax_harvester_adjacent: pyrust::set::new!(),
            reaches_core: pyrust::set::new!(),
            reaches_foundry: pyrust::set::new!(),
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
            last_seen: [0; MAX_N],
            _vision_offsets: vision_offsets,
            explore_target: None,
            explore_heading: None,
            opportunistic: false,
            econ_radius_sq: 0,
            known_map: None,
            core_edges: [Position { x: 0, y: 0 }; 8],
        }
    }

    fn build_initial_pnb() -> [Vec<i32>; MAX_N] {
        let mut pnb: [Vec<i32>; MAX_N] = [const { Vec::new() }; MAX_N];
        let stride = MAX_WIDTH as i32;
        let offsets: Vec<i32> =
            pyrust::collect!(pyrust::map!(pyrust::iter!(DIR8_DELTA), |t| t.1 * stride + t.0));
        for cy in 1..(MAX_WIDTH as i32 - 1) {
            let row = cy * stride;
            for cx in 1..(MAX_WIDTH as i32 - 1) {
                let i = (row + cx) as usize;
                pnb[i] =
                    pyrust::collect!(pyrust::map!(pyrust::iter!(offsets), |&o| (i as i32) + o));
            }
        }
        for cy in 0..MAX_WIDTH as i32 {
            let row = cy * stride;
            for cx in 0..MAX_WIDTH as i32 {
                if pyrust::vec::contains!((1..(MAX_WIDTH as i32 - 1)), &cx)
                    && pyrust::vec::contains!((1..(MAX_WIDTH as i32 - 1)), &cy)
                {
                    continue;
                }
                let i = (row + cx) as usize;
                let mut nbs: Vec<i32> = pyrust::vec::new!();
                for &(dx, dy) in &DIR8_DELTA {
                    let nx = cx + dx;
                    let ny = cy + dy;
                    if pyrust::vec::contains!((0..MAX_WIDTH as i32), &nx)
                        && pyrust::vec::contains!((0..MAX_WIDTH as i32), &ny)
                    {
                        pyrust::vec::push!(nbs, ny * stride + nx);
                    }
                }
                pnb[i] = nbs;
            }
        }
        pnb
    }

    /// Recompute `pnb[i]` and the relevant entries of every neighbour after
    /// tile i's passability changed. Mirrors Python `Builder.update_pnb`.
    pub fn update_pnb(&mut self, i: usize) {
        let w = self.state.width;
        let h = self.state.height;
        let cx = (i % MAX_WIDTH) as i32;
        let cy = (i / MAX_WIDTH) as i32;
        let passable = self.cost_grid[i] != INF;
        self.pnb[i].clear();
        if passable {
            for &(dx, dy) in &DIR8_DELTA {
                let nx = cx + dx;
                let ny = cy + dy;
                if pyrust::vec::contains!((0..w), &nx) && pyrust::vec::contains!((0..h), &ny) {
                    let ni = (ny as usize) * MAX_WIDTH + (nx as usize);
                    if self.cost_grid[ni] != INF {
                        pyrust::vec::push!(self.pnb[i], ni as i32);
                    }
                }
            }
        }
        for &(dx, dy) in &DIR8_DELTA {
            let nx = cx + dx;
            let ny = cy + dy;
            if !(pyrust::vec::contains!((0..w), &nx) && pyrust::vec::contains!((0..h), &ny)) {
                continue;
            }
            let ni = (ny as usize) * MAX_WIDTH + (nx as usize);
            if self.cost_grid[ni] == INF {
                continue;
            }
            let nb_list = &mut self.pnb[ni];
            if passable {
                if !pyrust::vec::contains!(nb_list, &(i as i32)) {
                    pyrust::vec::push!(nb_list, i as i32);
                }
            } else if let Some(p) = pyrust::position!(pyrust::iter!(nb_list), |&x| x == i as i32) {
                pyrust::vec::swap_remove!(nb_list, p);
            }
        }
    }

    /// Position to flat index (inherent shadow of `Unit::idx` so peer code
    /// in `crate::builder::*` doesn't need to import the trait).
    #[inline]
    #[must_use]
    #[pyrust::inline]
    pub const fn idx(&self, pos: Position) -> usize {
        (pos.y as usize) * MAX_WIDTH + (pos.x as usize)
    }

    #[pyrust::inline]
    /// In-bounds check (inherent shadow of `Unit::in_bounds`).
    #[inline]
    #[must_use]
    pub const fn in_bounds(&self, pos: Position) -> bool {
        pos.x >= 0 && pos.x < self.state.width && pos.y >= 0 && pos.y < self.state.height
    }

    #[pyrust::inline]
    /// Resolved symmetry (inherent shadow of `Unit::symmetry` so peer code
    /// can use `builder.symmetry` without importing the trait).
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

    #[pyrust::inline]
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

    /// Kind + team at `pos`, or `None` if no building / not in vision.
    #[must_use]
    pub const fn get_building(&self, pos: Position) -> Option<(EntityType, Team)> {
        let i = self.idx(pos);
        let kind = self.building_kind[i];
        let team = self.building_team[i];
        if pyrust::is_some!(kind) && pyrust::is_some!(team) {
            Some((pyrust::unwrap!(kind), pyrust::unwrap!(team)))
        } else {
            None
        }
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn kind_at(&self, pos: Position) -> Option<EntityType> {
        self.building_kind[self.idx(pos)]
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn team_at(&self, pos: Position) -> Option<Team> {
        self.building_team[self.idx(pos)]
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn get_cost(&self, pos: Position) -> i32 {
        self.cost_grid[self.idx(pos)]
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn is_passable(&self, pos: Position) -> bool {
        self.cost_grid[self.idx(pos)] != INF
    }

    #[must_use]
    pub fn is_reachable(&self, pos: Position) -> bool {
        let i = self.idx(pos) as i32;
        let my_i = (self.state.my_pos.y * (MAX_WIDTH as i32)) + self.state.my_pos.x;
        if self.reach_parent[i as usize] == -1 || self.reach_parent[my_i as usize] == -1 {
            return false;
        }
        find_ro(&self.reach_parent, i) == find_ro(&self.reach_parent, my_i)
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
        let i = self.idx(pos);
        self.env[i] != Some(Environment::Wall)
            && (pyrust::is_none!(self.building_team[i])
                || self.building_team[i] == Some(self.state.my_team))
    }

    #[must_use]
    pub fn is_friendly_turret(&self, pos: Position) -> bool {
        let i = self.idx(pos);
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
        let i = self.idx(pos);
        match self.building_team[i] {
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
    pub fn ti_conv_astar(
        &mut self,
        start: Position,
        target: Position,
        resource: ResourceType,
    ) -> Option<Vec<Position>> {
        let mut ctx = self.make_econ_ctx();
        let path = self
            .conv_search
            .search(start, target, resource, &mut ctx);
        self.absorb_econ_ctx(ctx);
        path
    }

    /// Run the Ax A* search. Same shape as `ti_conv_astar` but goes
    /// through `ax_conv_search`.
    pub fn ax_conv_astar(
        &mut self,
        start: Position,
        target: Position,
        resource: ResourceType,
    ) -> Option<Vec<Position>> {
        let mut ctx = self.make_econ_ctx();
        let path = self
            .ax_conv_search
            .search(start, target, resource, &mut ctx);
        self.absorb_econ_ctx(ctx);
        path
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

    /// One A* step toward `target`. Returns the next position to step to,
    /// or `None` if the goal is unreachable / already at goal. Borrow-splits
    /// internally so the bugnav state and the cost grid can be passed
    /// simultaneously.
    pub fn bugnav_step(&mut self, target: Position) -> Option<Position> {
        let Self {
            bugnav,
            cost_grid,
            state,
            ..
        } = self;
        let mut ctx = NavCtx {
            my_pos: state.my_pos,
            cost_grid,
            w: state.width,
            h: state.height,
            nearby_tiles: &state.nearby_tiles,
            all_bots: &state.all_bots,
        };
        bugnav.step(&mut ctx, target)
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
                pyrust::set::add!(self.ti_harvester_adjacent, n);
                self._reeval_ti_upstream(n);
            } else if old > 0 && new == 0 {
                pyrust::set::remove!(self.ti_harvester_adjacent, &n);
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
                pyrust::set::add!(self.ax_harvester_adjacent, n);
                self._reeval_ax_upstream(n);
            } else if old > 0 && new == 0 {
                pyrust::set::remove!(self.ax_harvester_adjacent, &n);
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
        let is_in = pyrust::vec::contains!(self.ti_upstream, &t);
        if want == is_in {
            return;
        }
        let i = self.idx(t);
        let delta: i32;
        if want {
            pyrust::set::add!(self.ti_upstream, t);
            delta = 1;
        } else {
            pyrust::set::remove!(self.ti_upstream, &t);
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
        let is_in = pyrust::vec::contains!(self.ax_upstream, &t);
        if want == is_in {
            return;
        }
        let i = self.idx(t);
        let delta: i32;
        if want {
            pyrust::set::add!(self.ax_upstream, t);
            delta = 1;
        } else {
            pyrust::set::remove!(self.ax_upstream, &t);
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
        if pyrust::vec::contains!(self.ti_upstream, &f) {
            self._ti_in_count[i] += 1;
            self._reeval_ti_upstream(t);
        }
        if pyrust::vec::contains!(self.ax_upstream, &f) {
            self._ax_in_count[i] += 1;
            self._reeval_ax_upstream(t);
        }
    }

    pub fn _on_in_edge_removed(&mut self, t: Position, f: Position) {
        let i = self.idx(t);
        if pyrust::vec::contains!(self.ti_upstream, &f) {
            self._ti_in_count[i] -= 1;
            self._reeval_ti_upstream(t);
        }
        if pyrust::vec::contains!(self.ax_upstream, &f) {
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
            pyrust::set::add!(self.is_multi_input, t);
        } else {
            pyrust::set::remove!(self.is_multi_input, &t);
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
            pyrust::set::remove!(self.dangling_set, &t);
            pyrust::set::remove!(self.unreachable_dangling, &t);
            return;
        }

        let unconn_adj = pyrust::vec::contains!(self.adjacent_to_unconnected_harvester, &t);
        let mut feeders_unsatisfied = false;
        let in_edges_t: Vec<Position> = pyrust::clone!(self.in_edges[i]);
        for f in &in_edges_t {
            let in_ti = pyrust::vec::contains!(self.ti_upstream, f);
            let in_ax = pyrust::vec::contains!(self.ax_upstream, f);
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
            if !pyrust::vec::contains!(self.unreachable_dangling, &t) {
                pyrust::set::add!(self.dangling_set, t);
            }
        } else {
            pyrust::set::remove!(self.dangling_set, &t);
            pyrust::set::remove!(self.unreachable_dangling, &t);
        }
    }

    /// Set `pnb[(cy, cx)]` to its 8-king-move neighbours within `(w, h)`.
    /// Pulled out of `post_init` so the body is a single statement and the
    /// translator doesn't need multi-statement-closure support.
    fn pnb_fix_boundary(&mut self, cx: i32, cy: i32, w: i32, h: i32) {
        let stride = MAX_WIDTH as i32;
        let mut nbs: Vec<i32> = pyrust::vec::new!();
        for &(dx, dy) in &DIR8_DELTA {
            let nx = cx + dx;
            let ny = cy + dy;
            if pyrust::vec::contains!((0..w), &nx) && pyrust::vec::contains!((0..h), &ny) {
                pyrust::vec::push!(nbs, ny * stride + nx);
            }
        }
        self.pnb[(cy * stride + cx) as usize] = nbs;
    }

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
    }
}

impl Unit for Builder {
    #[pyrust::inline]
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

        let r = self.state.rng.random();
        self.opportunistic = r < 0.5;

        let s = pyrust::float!(pyrust::max!(self.state.width, self.state.height));
        self.econ_radius_sq = pyrust::round!(((0.7 * s) * (0.7 * s))) as i32;

        // Mark off-map cells as INF.
        let w = self.state.width;
        let h = self.state.height;
        for y in 0..MAX_WIDTH as i32 {
            let base = (y as usize) * MAX_WIDTH;
            for x in 0..MAX_WIDTH as i32 {
                if x >= w || y >= h {
                    self.cost_grid[base + (x as usize)] = INF;
                }
            }
        }

        self.known_map = if HARDCODE {
            identify_map(self.state.width, self.state.height, self.my_core)
        } else {
            None
        };

        // Core perimeter — 8 tiles in DIR8 order.
        for (i, d) in pyrust::enumerate!(pyrust::iter!(DIR8)) {
            self.core_edges[i] = self.my_core.add(*d);
        }

        // Trim pnb at the actual map boundary (right column + bottom row).
        {
            let _scope = Scope::new_timed("pnb");
            for cx in 0..w {
                self.pnb_fix_boundary(cx, h - 1, w, h);
            }
            for cy in 0..(h - 1) {
                self.pnb_fix_boundary(w - 1, cy, w, h);
            }
        }

        self.refresh_symmetry_cache();
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        self.state.cache_per_turn_state(ct);
        self.state.check_symmetry_marker(ct);
        self.refresh_symmetry_cache();

        let _g = Scope::new_timed("body");
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

        update(self, ct);
        begin_turn_offense(self, ct);

        if DEBUG_DUMP {
            crate::builder::dump::dump(self, ct);
        }

        let role = pyrust::expect!(self.role, "role must be set after update");
        {
            let _g = Scope::new_timed("tasks");
            let policy = policy_for_role(role);
            run_policy(self, ct, policy);
        }
        {
            let _g = Scope::new_timed("hooks");
            {
                let _g = Scope::new_timed("indicators");
                indicators(self, ct);
            }
            if !role.is_offensive() {
                let _g = Scope::new_timed("heal");
                end_of_turn_heal(self, ct);
            }
            {
                let _g = Scope::new_timed("symmetry");
                end_of_turn_propagate_symmetry(self, ct);
            }
        }
    }
}

impl CoreAwareUnit for Builder {
    #[pyrust::inline]
    fn my_core_pos(&self) -> Position {
        self.my_core
    }

    fn set_my_core(&mut self, pos: Position) {
        self.my_core = pos;
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
