use crate::config::DEBUG_LOG;
use std::collections::HashSet;

use cambc::{Controller, ControllerApi, EntityType, Environment, Position, ResourceType};
use serde_json::{Map, Value};

use crate::builder::Builder;
use crate::builder::algorithms::reachability::find;
use crate::builder::helpers::{
    ax_feeds_target, can_afford_ore_claim, harvester_would_contaminate, is_inward_guard,
    ore_available, pick_ax_ore_target, pick_offensive_ti_ore_target, pick_ore_target,
};
use crate::util::constants::{FLOW_HISTORY_LEN, INF, MAX_WIDTH, STRIDE, base_cost};
use crate::util::debug::Scope;
use crate::util::debug::debug as log;
use crate::util::directions::DIR4_DELTA;
use crate::util::metrics::{chebyshev_p, claims_by_proximity_p};
use crate::util::posint::{DIR4_INT, PosInt, dist_sq, idx_of, manhat, pos_of};
use crate::util::visualiser::auto_wrap_position;

#[must_use]
pub fn can_place_junction(builder: &Builder, pos: Position) -> bool {
    let my_team = builder.state.my_team;
    let p = idx_of(pos);
    let kind = builder.kind_at_p(p);
    let team = builder.team_at_p(p);
    let ok = match kind {
        None => true,
        Some(EntityType::Conveyor | EntityType::Road) => team == Some(my_team),
        _ => false,
    };
    if !ok {
        return false;
    }

    let conv = builder.get_in_edges(pos);
    let conv_adj: Vec<Position> =
        pyrust::collect!(pyrust::filter!(pyrust::copied!(pyrust::iter!(conv)), |c| c
            .distance_squared(pos)
            <= 2));
    if pyrust::len!(conv_adj) >= 2 || pyrust::vec::is_empty!(conv) {
        return false;
    }
    let posint_valid = &builder.posint_valid;
    let mut buildable_count = 0;
    for &d in &DIR4_INT {
        let np = p + d;
        if np < 0 || posint_valid[np as usize] == 0 {
            continue;
        }
        if builder.get_env_p(np) != Some(Environment::Empty) {
            continue;
        }
        let nk = builder.kind_at_p(np);
        let nt = builder.team_at_p(np);
        match nk {
            None => buildable_count += 1,
            Some(EntityType::Conveyor | EntityType::Bridge | EntityType::Splitter) => {}
            Some(_) if nt == Some(my_team) => buildable_count += 1,
            Some(_) => {}
        }
    }
    buildable_count >= 1
}

pub fn update_map_econ(builder: &mut Builder, ct: &mut Controller<'_>) {
    let prev_unconn = pyrust::set::clone!(builder.adjacent_to_unconnected_harvester);
    let tmp_unconn = pyrust::set::clone!(builder.adjacent_to_unconnected_harvester);
    pyrust::set::clear!(builder.adjacent_to_unconnected_harvester);
    let mask_e = pyrust::clone!(builder.vision_mask);
    for &p in pyrust::iter!(&tmp_unconn) {
        if mask_e[p as usize] == 0 {
            pyrust::set::add!(builder.adjacent_to_unconnected_harvester, p);
        }
    }
    let tmp_harv = pyrust::set::clone!(builder.adjacent_to_harvester);
    pyrust::set::clear!(builder.adjacent_to_harvester);
    for &p in pyrust::iter!(&tmp_harv) {
        if mask_e[p as usize] == 0 {
            pyrust::set::add!(builder.adjacent_to_harvester, p);
        }
    }

    // Pass 1: scan visible harvesters to maintain
    // `adjacent_to_unconnected_harvester` and `adjacent_to_harvester`.
    // Iterate the typed visible_harvesters list (typically 1-5 tiles)
    // instead of all 60 nearby_tiles + per-tile kind filter.
    let my_team = builder.state.my_team;
    let w = builder.state.width;
    let h = builder.state.height;
    let bk = &builder.building_kind;
    let bt = &builder.building_team;
    let out_edges = &builder.out_edges;
    let harvesters = pyrust::clone!(builder.visible_harvesters);
    let posint_valid = &builder.posint_valid;
    for &pi in &harvesters {
        let pos = pos_of(pi);
        let mut adjacent_conveyor = false;
        for &d in &DIR4_INT {
            let np = pi + d;
            if np < 0 || posint_valid[np as usize] == 0 {
                continue;
            }
            let ni = np as usize;
            let nk = bk[ni];
            let nt = bt[ni];
            match nk {
                Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
                    if nt == Some(my_team) =>
                {
                    if !pyrust::vec::is_empty!(out_edges[ni]) {
                        let out = out_edges[ni][0];
                        if out != pos {
                            let out_in_bounds = out.x >= 0 && out.x < w && out.y >= 0 && out.y < h;
                            let out_idx = idx_of(out) as usize;
                            if !(out_in_bounds && bk[out_idx] == Some(EntityType::Harvester)) {
                                adjacent_conveyor = true;
                                break;
                            }
                        }
                    }
                }
                Some(
                    EntityType::Bridge
                    | EntityType::Splitter
                    | EntityType::Foundry
                    | EntityType::Core
                    | EntityType::Gunner
                    | EntityType::Sentinel
                    | EntityType::Breach
                    | EntityType::Launcher,
                ) if nt == Some(my_team) => {
                    adjacent_conveyor = true;
                    break;
                }
                _ => {}
            }
        }
        if !adjacent_conveyor {
            for &d in &DIR4_INT {
                let np = pi + d;
                if np >= 0 && posint_valid[np as usize] != 0 {
                    pyrust::set::add!(builder.adjacent_to_unconnected_harvester, np);
                }
            }
        }
        for &d in &DIR4_INT {
            let np = pi + d;
            if np >= 0 && posint_valid[np as usize] != 0 {
                pyrust::set::add!(builder.adjacent_to_harvester, np);
            }
        }
    }

    // Pass 2: movement cost_grid per-turn penalties for enemy turret rays
    // and launcher adjacency.
    let cost_grid = &mut builder.cost_grid;
    let adj_launcher = &builder.adjacent_to_enemy_launcher;
    let enemy_rays = &builder.enemy_turret_ray_tiles;
    for pos in &builder.state.nearby_tiles {
        let pi = idx_of(*pos);
        let i = pi as usize;
        if cost_grid[i] != INF {
            if pyrust::set::contains!(adj_launcher, &pi) {
                cost_grid[i] += 20;
            }
            if pyrust::set::contains!(enemy_rays, &pi) {
                cost_grid[i] += 15;
            }
        }
    }

    // Reconcile dangling_set with harvester-adjacency changes. Sort
    // by PosInt (y-major) so iteration order is deterministic across
    // hash-randomized iteration.
    let mut changed: Vec<i32> = pyrust::collect!(pyrust::copied!(
        prev_unconn.symmetric_difference(&builder.adjacent_to_unconnected_harvester)
    ));
    pyrust::sort!(changed);
    for p in changed {
        builder._check_dangling(pos_of(p), "unconn_flip");
    }
}

/// Migrate tiles between `dangling_set` and `unreachable_dangling`
/// according to map-level reachability (incremental UF, not BFS).
pub fn update_unreachable_dangling(builder: &mut Builder) {
    let my_i = idx_of(builder.state.my_pos) as usize;
    if builder.reach_parent[my_i] == -1 {
        return;
    }
    let my_root = find(&mut builder.reach_parent, my_i as i32);
    // Sort by (y, x) so the log output and any downstream observable side
    // effects are deterministic across hash-randomized iteration.
    let mut dangling: Vec<i32> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.dangling_set)));
    pyrust::sort!(dangling);
    for t in dangling {
        let i = t as usize;
        if builder.reach_parent[i] == -1 || find(&mut builder.reach_parent, t) != my_root {
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(args, pyrust::to_string!("t"), auto_wrap_position(pos_of(t)));
                log("DANGLING discard(unreachable) t={t}", args);
            }
            pyrust::set::remove!(builder.dangling_set, &t);
            pyrust::set::add!(builder.unreachable_dangling, t);
        }
    }
    let mut unreach: Vec<PosInt> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.unreachable_dangling)));
    pyrust::sort!(unreach);
    for t in unreach {
        let i = t as usize;
        let tp = pos_of(t);
        if builder.reach_parent[i] != -1 && find(&mut builder.reach_parent, i as i32) == my_root {
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(args, pyrust::to_string!("t"), auto_wrap_position(tp));
                log("DANGLING add(reachable-migrate) t={t}", args);
            }
            pyrust::set::remove!(builder.unreachable_dangling, &t);
            pyrust::set::add!(builder.dangling_set, t);
        }
    }
}

/// Refresh the cached `dangling_output` once per turn — no
/// stickiness. Tasks (`extend_chain_*`, `push_extend`) and update
/// helpers (`update_foundry_target`, `update_ti_sink`) read the cached
/// value rather than re-running the selection.
pub fn update_dangling(builder: &mut Builder) {
    let result = pick_dangling_output(&*builder, None);
    builder.dangling_output = result;
}

/// Pick the dangling end this builder should work on right now —
/// no commitment, recomputed on demand. The proximity gate
/// (`claims_by_proximity`) ensures at most one builder claims each end
/// even though every builder runs the same selection independently.
///
/// If `ct` is provided, candidates are filtered to currently-visible
/// tiles (used by `extend_chain_in_range`). Without `ct`, all dangling
/// tiles are considered.
/// Forward flood from seed tiles through `out_edges`. Helper for the
/// debug-only `check_invariants` oracle. Pulled out of an inline closure
/// so the translator's single-expr-lambda restriction doesn't apply.
fn flood_forward(out_edges: &[Vec<Position>], seeds: &HashSet<PosInt>) -> HashSet<PosInt> {
    let mut target: HashSet<PosInt> = pyrust::set::new!();
    let mut stack: Vec<PosInt> = pyrust::vec::new!();
    for &s in seeds {
        if pyrust::set::contains!(target, &s) {
            continue;
        }
        if pyrust::vec::is_empty!(out_edges[s as usize]) {
            continue;
        }
        pyrust::set::add!(target, s);
        pyrust::vec::push!(stack, s);
    }
    while let Some(p) = pyrust::vec::pop!(stack) {
        for out in &out_edges[p as usize] {
            let out_i = idx_of(*out);
            if pyrust::set::contains!(target, &out_i) {
                continue;
            }
            pyrust::set::add!(target, out_i);
            pyrust::vec::push!(stack, out_i);
        }
    }
    target
}

/// Chebyshev distance from `pos` to its nearest `core_edge` (or `my_core`
/// if `core_edges` is empty — shouldn't happen post-init).
fn chebyshev_to_nearest_core_edge(builder: &Builder, pos: Position) -> i32 {
    chebyshev_to_nearest_core_edge_p(builder, idx_of(pos))
}

fn chebyshev_to_nearest_core_edge_p(builder: &Builder, p: PosInt) -> i32 {
    let mut best_d = INF;
    for e in &builder.core_edges {
        let d = chebyshev_p(p, idx_of(*e));
        if d < best_d {
            best_d = d;
        }
    }
    if best_d == INF {
        chebyshev_p(p, idx_of(builder.my_core))
    } else {
        best_d
    }
}

#[must_use]
pub fn pick_dangling_output(builder: &Builder, ct: Option<&Controller<'_>>) -> Option<Position> {
    let friendly: Vec<(PosInt, i32)> = pyrust::collect!(pyrust::map!(
        pyrust::filter!(pyrust::iter!(builder.state.all_bots), |t| {
            *t.1 != builder.state.my_id && pyrust::vec::contains!(builder.state.friendly_bots, t.0)
        }),
        |t| (idx_of(*t.0), *t.1)
    ));
    let en_core_p = if pyrust::is_some!(builder.symmetry) {
        Some(idx_of(builder.en_core_guess))
    } else {
        None
    };
    let core_p = idx_of(builder.my_core);
    let my_p = idx_of(builder.state.my_pos);
    let mut best: Option<Position> = None;
    // Tiebreak by (y, x) on top of (my_d, chain_d) so iteration order over
    // the hash collection isn't observable.
    let mut best_score: (i32, i32, i32, i32) = (1 << 30, 1 << 30, 1 << 30, 1 << 30);
    let dangling_iter: Vec<Position> =
        pyrust::collect!(pyrust::map!(pyrust::iter!(builder.dangling_set), |p| {
            pos_of(*p)
        }));
    for pos in dangling_iter {
        if let Some(c) = ct
            && !pyrust::unwrap!(c.is_in_vision(pos))
        {
            continue;
        }
        let pi = idx_of(pos);
        if !claims_by_proximity_p(
            my_p,
            builder.state.my_id,
            pi,
            pyrust::copied!(pyrust::iter!(friendly)),
        ) {
            continue;
        }
        let my_d = chebyshev_p(my_p, pi);
        let chain_d = match en_core_p {
            Some(ecp) if dist_sq(pi, ecp) < dist_sq(pi, core_p) => chebyshev_p(pi, ecp),
            _ => chebyshev_to_nearest_core_edge_p(builder, pi),
        };
        let score = (my_d, chain_d, pos.y, pos.x);
        if score < best_score {
            best_score = score;
            best = Some(pos);
        }
    }
    best
}

pub fn update_ore_target(builder: &mut Builder) {
    let mut candidate_ore = pick_ore_target(builder);
    let needs_pick = pyrust::is_none!(builder.ore_target)
        || pyrust::is_some_and!(builder.ore_target, |t| !ore_available(builder, t))
        || pyrust::is_some_and!(builder.ore_target, |t| !builder.is_reachable(t))
        || pyrust::is_some_and!(builder.ore_target, |t| harvester_would_contaminate(
            builder, t
        ))
        || (pyrust::is_some!(candidate_ore)
            && pyrust::unwrap!(candidate_ore).distance_squared(builder.state.my_pos) <= 2
            && pyrust::is_some_and!(builder.ore_target, |t| t
                .distance_squared(builder.state.my_pos)
                > 2));
    if needs_pick {
        let sink = pyrust::unwrap_or!(builder.ti_sink, builder.my_core);
        if let Some(c) = candidate_ore
            && !can_afford_ore_claim(builder, c, sink)
        {
            candidate_ore = None;
        }
        builder.ore_target = candidate_ore;
    }
}

/// Enemy-side Ti ore claim. Same re-evaluation semantics as
/// `update_ore_target`: keep the current pick if still valid and not
/// trivially beaten by a much-closer alternative.
pub fn update_offensive_ore_target(builder: &mut Builder) {
    let mut candidate = pick_offensive_ti_ore_target(builder);
    let needs_pick = pyrust::is_none!(builder.offensive_ore_target)
        || pyrust::is_some_and!(builder.offensive_ore_target, |t| !ore_available(builder, t))
        || pyrust::is_some_and!(builder.offensive_ore_target, |t| !builder.is_reachable(t))
        || pyrust::is_some_and!(builder.offensive_ore_target, |t| {
            harvester_would_contaminate(builder, t)
        })
        || (pyrust::is_some!(candidate)
            && pyrust::unwrap!(candidate).distance_squared(builder.state.my_pos) <= 2
            && pyrust::is_some_and!(builder.offensive_ore_target, |t| t
                .distance_squared(builder.state.my_pos)
                > 2));
    if needs_pick {
        let sink = if pyrust::is_some!(builder.symmetry) {
            Some(builder.en_core_guess)
        } else {
            None
        };
        if let Some(c) = candidate
            && let Some(s) = sink
            && !can_afford_ore_claim(builder, c, s)
        {
            candidate = None;
        }
        builder.offensive_ore_target = candidate;
    }
}

/// Derived from Blue Dragon / Kessoku Band: no Ax harvester before turn 500.
const _AX_HARVESTER_ROUND_GATE: i32 = 500;

/// Pure friendly `BuildingConveyor` with exactly one cardinal friendly
/// Ax harvester. This is the designated foundry spot for a zero-length
/// Ax chain — `harvester_would_contaminate` has already admitted the Ax
/// harvester under the same geometric rule.
fn _is_zero_length_foundry_spot(builder: &Builder, pos: Position) -> bool {
    _is_zero_length_foundry_spot_p(builder, idx_of(pos))
}

fn _is_zero_length_foundry_spot_p(builder: &Builder, p: PosInt) -> bool {
    let i = p as usize;
    if builder.building_kind[i] != Some(EntityType::Conveyor) {
        return false;
    }
    if builder.building_team[i] != Some(builder.state.my_team) {
        return false;
    }
    let posint_valid = &builder.posint_valid;
    let mut ax_harv_count = 0;
    for &d in &DIR4_INT {
        let np = p + d;
        if np < 0 || posint_valid[np as usize] == 0 {
            continue;
        }
        let ni = np as usize;
        if builder.building_kind[ni] == Some(EntityType::Harvester)
            && builder.building_team[ni] == Some(builder.state.my_team)
            && builder.env[ni] == Some(Environment::OreAxionite)
        {
            ax_harv_count += 1;
            if ax_harv_count > 1 {
                return false;
            }
        }
    }
    ax_harv_count == 1
}

/// Foundry candidate: friendly Ti conveyor that reaches the core, is NOT
/// on a chain already feeding a foundry, and is NOT structurally downstream
/// of any known Ax harvester.
fn _foundry_local_ok(builder: &Builder, pos: Position) -> bool {
    let i = idx_of(pos) as usize;
    let kind = builder.building_kind[i];
    let team = builder.building_team[i];
    let is_conv = matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
    );
    if !is_conv {
        return false;
    }
    if team != Some(builder.state.my_team) {
        return false;
    }
    if pyrust::vec::contains!(builder.upstream_of_dangling, &idx_of(pos)) {
        return false;
    }
    if pyrust::vec::contains!(builder.reaches_foundry, &idx_of(pos)) {
        return false;
    }
    // Reject tiles structurally downstream of an existing foundry — they'd
    // receive refined Ax from F1 and clog if we placed F2 here.
    if pyrust::vec::contains!(builder.downstream_of_foundry, &idx_of(pos)) {
        return false;
    }
    let is_foundry_spot = _is_zero_length_foundry_spot(builder, pos);
    if !is_foundry_spot {
        if pyrust::vec::contains!(builder.ax_harvester_adjacent, &idx_of(pos)) {
            return false;
        }
        if pyrust::vec::contains!(builder.ax_upstream, &idx_of(pos)) {
            return false;
        }
    }
    let hist = &builder.flow_history[i];
    let mut saw_ti = false;
    let mut has_ax = false;
    for (r, _rid) in hist {
        let Some(r) = r else {
            continue;
        };
        match r {
            ResourceType::RawAxionite | ResourceType::RefinedAxionite => has_ax = true,
            ResourceType::Titanium => saw_ti = true,
        }
    }
    if has_ax && !is_foundry_spot && !ax_feeds_target(builder, pos) {
        return false;
    }
    saw_ti
}

/// Occupancy count: non-None entries in the tile's `flow_history`.
fn _tile_volume(builder: &Builder, pos: Position) -> usize {
    pyrust::count!(pyrust::filter!(
        pyrust::iter!(builder.flow_history[idx_of(pos) as usize]),
        |t| pyrust::is_some!(t.0)
    ))
}

/// `pos` is a pure-Ax transport tile worth merging a new Ax chain into.
fn _pure_ax_merge_ok(builder: &Builder, pos: Position) -> bool {
    if _tile_volume(builder, pos) >= FLOW_HISTORY_LEN {
        return false;
    }
    pyrust::vec::contains!(builder.ax_upstream, &idx_of(pos))
        && !pyrust::vec::contains!(builder.ti_upstream, &idx_of(pos))
        && !pyrust::vec::contains!(builder.upstream_of_dangling, &idx_of(pos))
}

/// Manhattan-distance threshold: a pre-existing foundry or Ax chain is only
/// preferred over building a new foundry on a nearby Ti conveyor if the pre-
/// existing option isn't more than this many tiles further. Otherwise creating
/// a new foundry locally is the better choice.
const _FOUNDRY_REUSE_THRESHOLD: i32 = 10;

const fn _manhattan(a: Position, b: Position) -> i32 {
    pyrust::abs!((a.x - b.x)) + pyrust::abs!((a.y - b.y))
}

/// Find junctions (multi-feeder tiles) where the feeders' total
/// observed inflow exceeds the junction's `FLOW_HISTORY_LEN` window — i.e.
/// stacks arrive faster than a single-tile pass-through can forward.
fn _detect_congested_junctions(builder: &Builder) -> Vec<Position> {
    let mut result: Vec<Position> = pyrust::vec::new!();
    for t in &builder.nearby_buildings {
        let i = idx_of(*t) as usize;
        if !matches!(
            builder.building_kind[i],
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge)
        ) {
            continue;
        }
        let feeders = &builder.in_edges[i];
        if pyrust::len!(feeders) < 2 {
            continue;
        }
        let hist = &builder.flow_history[i];
        if pyrust::len!(hist) < FLOW_HISTORY_LEN {
            continue;
        }
        if pyrust::count!(pyrust::filter!(pyrust::iter!(hist), |t| pyrust::is_some!(
            t.0
        ))) < FLOW_HISTORY_LEN
        {
            continue;
        }
        let mut total: usize = 0;
        let mut complete = true;
        for f in feeders {
            let fh = &builder.flow_history[idx_of(*f) as usize];
            if pyrust::len!(fh) < FLOW_HISTORY_LEN {
                complete = false;
                break;
            }
            total += pyrust::count!(pyrust::filter!(pyrust::iter!(fh), |t| pyrust::is_some!(
                t.0
            )));
        }
        if complete && total > FLOW_HISTORY_LEN {
            pyrust::vec::push!(result, *t);
        }
    }
    result
}

/// Transport tiles running empirically at full throughput.
#[allow(dead_code)]
fn _detect_saturated_tiles(builder: &Builder) -> Vec<Position> {
    let mut result: Vec<Position> = pyrust::vec::new!();
    for t in &builder.nearby_buildings {
        let i = idx_of(*t) as usize;
        if !matches!(
            builder.building_kind[i],
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge)
        ) {
            continue;
        }
        let hist = &builder.flow_history[i];
        if pyrust::len!(hist) < FLOW_HISTORY_LEN {
            continue;
        }
        if pyrust::count!(pyrust::filter!(pyrust::iter!(hist), |t| pyrust::is_some!(
            t.0
        ))) >= FLOW_HISTORY_LEN
        {
            pyrust::vec::push!(result, *t);
        }
    }
    result
}

/// Per-turn backward flood over the structural transport graph.
/// Marks `reaches_core`, `reaches_foundry`, `upstream_of_dangling`,
/// `upstream_of_congestion` (backward over `in_edges`).
pub fn update_economy_reachability(builder: &mut Builder) {
    builder.reaches_core = pyrust::set::new!();
    builder.reaches_foundry = pyrust::set::new!();
    builder.downstream_of_foundry = pyrust::set::new!();
    builder.upstream_of_dangling = pyrust::set::new!();
    builder.upstream_of_congestion = pyrust::set::new!();

    {
        let my_core = builder.my_core;
        let mut roots: Vec<PosInt> = vec![idx_of(my_core)];
        pyrust::vec::extend!(
            roots,
            pyrust::map!(pyrust::iter!(builder.core_edges), |e| idx_of(*e))
        );
        flood_back(&builder.in_edges, &roots, &mut builder.reaches_core);
    }

    if !pyrust::vec::is_empty!(builder.my_foundries) {
        let roots: Vec<PosInt> =
            pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.my_foundries)));
        flood_back(&builder.in_edges, &roots, &mut builder.reaches_foundry);
        // Forward flood over `out_edges` from foundry roots: any conveyor
        // that would receive the foundry's refined Ax output. Placing a
        // new foundry here would clog. The roots themselves are
        // foundries, which never qualify as Ti-conveyor candidates anyway.
        let roots2: Vec<PosInt> =
            pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.my_foundries)));
        flood_back(
            &builder.out_edges,
            &roots2,
            &mut builder.downstream_of_foundry,
        );
    }

    let dangling_roots: Vec<PosInt> = pyrust::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(builder.dangling_set)),
        |p| !pyrust::vec::is_empty!(builder.in_edges[*p as usize])
    ));
    flood_back(
        &builder.in_edges,
        &dangling_roots,
        &mut builder.upstream_of_dangling,
    );

    builder.congested_junctions = pyrust::collect!(pyrust::map!(
        pyrust::into_iter!(_detect_congested_junctions(builder)),
        |p| idx_of(p)
    ));
    let cong_roots: Vec<PosInt> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.congested_junctions)));
    flood_back(
        &builder.in_edges,
        &cong_roots,
        &mut builder.upstream_of_congestion,
    );
}

fn flood_back(in_edges: &[Vec<Position>], roots: &[PosInt], target: &mut HashSet<PosInt>) {
    let mut stack: Vec<PosInt> = pyrust::vec::new!();
    for &r in roots {
        if !pyrust::set::contains!(target, &r) {
            pyrust::set::add!(target, r);
            pyrust::vec::push!(stack, r);
        }
    }
    while let Some(p) = pyrust::vec::pop!(stack) {
        let i = p as usize;
        for u in &in_edges[i] {
            let ui = idx_of(*u);
            if pyrust::set::contains!(target, &ui) {
                continue;
            }
            pyrust::set::add!(target, ui);
            pyrust::vec::push!(stack, ui);
        }
    }
}

/// Oracle: recompute the incrementally-maintained sets from scratch
/// using the current `in_edges` / `out_edges` / harvester-adjacent state,
/// and assert equality with the live values.
pub fn check_invariants(builder: &Builder) {
    let out_edges = &builder.out_edges;
    let in_edges = &builder.in_edges;

    // --- A: harvester-adjacent set vs counter ---
    let expected_ti_adj: HashSet<PosInt> = pyrust::collect!(pyrust::filter_map!(
        pyrust::enumerate!(pyrust::iter!(builder._ti_harv_at)),
        |t| {
            if *t.1 > 0 {
                Some(((t.0 / STRIDE) as i32) * (STRIDE as i32) + (t.0 % STRIDE) as i32)
            } else {
                None
            }
        }
    ));
    let expected_ax_adj: HashSet<PosInt> = pyrust::collect!(pyrust::filter_map!(
        pyrust::enumerate!(pyrust::iter!(builder._ax_harv_at)),
        |t| {
            if *t.1 > 0 {
                Some(((t.0 / STRIDE) as i32) * (STRIDE as i32) + (t.0 % STRIDE) as i32)
            } else {
                None
            }
        }
    ));
    if expected_ti_adj != builder.ti_harvester_adjacent {
        let mut args = Map::new();
        let mut missing: Vec<PosInt> = pyrust::collect!(pyrust::copied!(
            expected_ti_adj.difference(&builder.ti_harvester_adjacent)
        ));
        missing.sort();
        let mut extra: Vec<PosInt> = pyrust::collect!(pyrust::copied!(
            builder.ti_harvester_adjacent.difference(&expected_ti_adj)
        ));
        extra.sort();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("missing"),
            Value::String(format!("{missing:?}"))
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("extra"),
            Value::String(format!("{extra:?}"))
        );
        log(
            "INVARIANT_FAIL ti_harvester_adjacent missing={missing} extra={extra}",
            args,
        );
    }
    if expected_ax_adj != builder.ax_harvester_adjacent {
        let mut args = Map::new();
        let mut missing: Vec<PosInt> = pyrust::collect!(pyrust::copied!(
            expected_ax_adj.difference(&builder.ax_harvester_adjacent)
        ));
        missing.sort();
        let mut extra: Vec<PosInt> = pyrust::collect!(pyrust::copied!(
            builder.ax_harvester_adjacent.difference(&expected_ax_adj)
        ));
        extra.sort();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("missing"),
            Value::String(format!("{missing:?}"))
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("extra"),
            Value::String(format!("{extra:?}"))
        );
        log(
            "INVARIANT_FAIL ax_harvester_adjacent missing={missing} extra={extra}",
            args,
        );
    }

    // --- B: forward flood from harvester-adjacent seeds ---
    let oracle_ti = flood_forward(out_edges, &builder.ti_harvester_adjacent);
    let oracle_ax = flood_forward(out_edges, &builder.ax_harvester_adjacent);

    if oracle_ti != builder.ti_upstream {
        let mut miss: Vec<PosInt> =
            pyrust::collect!(pyrust::copied!(oracle_ti.difference(&builder.ti_upstream)));
        miss.sort();
        miss.truncate(8);
        let mut extra: Vec<PosInt> =
            pyrust::collect!(pyrust::copied!(builder.ti_upstream.difference(&oracle_ti)));
        extra.sort();
        extra.truncate(8);
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("missing"),
                Value::String(format!("{miss:?}"))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("extra"),
                Value::String(format!("{extra:?}"))
            );
            log(
                "INVARIANT_FAIL ti_upstream missing={missing} extra={extra}",
                args,
            );
        }
        for t in pyrust::take!(pyrust::iter!(miss), 4) {
            let i = *t as usize;
            let tp = pos_of(*t);
            let feeders: Vec<(Position, bool, bool)> =
                pyrust::collect!(pyrust::map!(pyrust::iter!(in_edges[i]), |f| (
                    *f,
                    pyrust::set::contains!(builder.ti_upstream, &idx_of(*f)),
                    pyrust::set::contains!(oracle_ti, &idx_of(*f))
                )));
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("t"),
                    Value::String(format!("{tp:?}"))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("ti_in_count"),
                    Value::Number(pyrust::into!(builder._ti_in_count[i]))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("ti_harv_at"),
                    Value::Number(pyrust::into!(builder._ti_harv_at[i]))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("feeders"),
                    Value::String(format!("{feeders:?}"))
                );
                log(
                    "  miss t={t} ti_in_count={ti_in_count} ti_harv_at={ti_harv_at} feeders={feeders}",
                    args,
                );
            }
        }
    }
    if oracle_ax != builder.ax_upstream {
        let mut miss: Vec<PosInt> =
            pyrust::collect!(pyrust::copied!(oracle_ax.difference(&builder.ax_upstream)));
        miss.sort();
        miss.truncate(8);
        let mut extra: Vec<PosInt> =
            pyrust::collect!(pyrust::copied!(builder.ax_upstream.difference(&oracle_ax)));
        extra.sort();
        extra.truncate(8);
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("missing"),
                Value::String(format!("{miss:?}"))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("extra"),
                Value::String(format!("{extra:?}"))
            );
            log(
                "INVARIANT_FAIL ax_upstream missing={missing} extra={extra}",
                args,
            );
        }
        for t in pyrust::take!(pyrust::iter!(miss), 4) {
            let i = *t as usize;
            let tp = pos_of(*t);
            let feeders: Vec<(Position, bool, bool)> =
                pyrust::collect!(pyrust::map!(pyrust::iter!(in_edges[i]), |f| (
                    *f,
                    pyrust::set::contains!(builder.ax_upstream, &idx_of(*f)),
                    pyrust::set::contains!(oracle_ax, &idx_of(*f))
                )));
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("t"),
                    Value::String(format!("{tp:?}"))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("ax_in_count"),
                    Value::Number(pyrust::into!(builder._ax_in_count[i]))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("ax_harv_at"),
                    Value::Number(pyrust::into!(builder._ax_harv_at[i]))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("feeders"),
                    Value::String(format!("{feeders:?}"))
                );
                log(
                    "  miss t={t} ax_in_count={ax_in_count} ax_harv_at={ax_harv_at} feeders={feeders}",
                    args,
                );
            }
        }
    }

    // --- C: in-count drift (independent of B's outcome) ---
    for i in 0..pyrust::len!(in_edges) {
        if pyrust::vec::is_empty!(in_edges[i]) {
            if builder._ti_in_count[i] != 0 || builder._ax_in_count[i] != 0 {
                let t = Position {
                    x: (i % STRIDE) as i32,
                    y: (i / STRIDE) as i32,
                };
                if DEBUG_LOG {
                    let mut args = Map::new();
                    pyrust::dict::insert!(
                        args,
                        pyrust::to_string!("t"),
                        Value::String(format!("{t:?}"))
                    );
                    pyrust::dict::insert!(
                        args,
                        pyrust::to_string!("ti"),
                        Value::Number(pyrust::into!(builder._ti_in_count[i]))
                    );
                    pyrust::dict::insert!(
                        args,
                        pyrust::to_string!("ax"),
                        Value::Number(pyrust::into!(builder._ax_in_count[i]))
                    );
                    log(
                        "INVARIANT_FAIL in_count nonzero with empty in_edges t={t} ti={ti} ax={ax}",
                        args,
                    );
                }
            }
            continue;
        }
        let ti_expected = pyrust::count!(pyrust::filter!(
            pyrust::iter!(in_edges[i]),
            |f| pyrust::set::contains!(builder.ti_upstream, &idx_of(**f))
        )) as i32;
        let ax_expected = pyrust::count!(pyrust::filter!(
            pyrust::iter!(in_edges[i]),
            |f| pyrust::set::contains!(builder.ax_upstream, &idx_of(**f))
        )) as i32;
        if ti_expected != builder._ti_in_count[i] {
            let t = Position {
                x: (i % STRIDE) as i32,
                y: (i / STRIDE) as i32,
            };
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("t"),
                    Value::String(format!("{t:?}"))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("have"),
                    Value::Number(pyrust::into!(builder._ti_in_count[i]))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("expected"),
                    Value::Number(pyrust::into!(ti_expected))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("in_edges"),
                    Value::String(format!("{:?}", in_edges[i]))
                );
                log(
                    "INVARIANT_FAIL ti_in_count drift t={t} have={have} expected={expected} in_edges={in_edges}",
                    args,
                );
            }
        }
        if ax_expected != builder._ax_in_count[i] {
            let t = Position {
                x: (i % STRIDE) as i32,
                y: (i / STRIDE) as i32,
            };
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("t"),
                    Value::String(format!("{t:?}"))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("have"),
                    Value::Number(pyrust::into!(builder._ax_in_count[i]))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("expected"),
                    Value::Number(pyrust::into!(ax_expected))
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("in_edges"),
                    Value::String(format!("{:?}", in_edges[i]))
                );
                log(
                    "INVARIANT_FAIL ax_in_count drift t={t} have={have} expected={expected} in_edges={in_edges}",
                    args,
                );
            }
        }
    }
}

/// Classify a feeder tile by its observed flow-history: 'ti' if only
/// Ti stacks seen, 'ax' if only Ax stacks seen, None if no flow observed
/// or mixed.
fn _feeder_flow_kind(builder: &Builder, f: Position) -> Option<&'static str> {
    let i = idx_of(f) as usize;
    let mut seen_ti = false;
    let mut seen_ax = false;
    for (r, _rid) in &builder.flow_history[i] {
        let Some(r) = r else {
            continue;
        };
        match r {
            ResourceType::Titanium => seen_ti = true,
            ResourceType::RawAxionite | ResourceType::RefinedAxionite => seen_ax = true,
        }
    }
    if seen_ti && !seen_ax {
        return Some("ti");
    }
    if seen_ax && !seen_ti {
        return Some("ax");
    }
    None
}

/// True iff `pos` is a viable foundry site: a friendly conveyor or
/// armoured conveyor with >= 1 feeder delivering Ti only AND >= 1 feeder
/// delivering Ax only.
fn _is_junction(builder: &Builder, pos: Position) -> bool {
    let i = idx_of(pos) as usize;
    let kind = builder.building_kind[i];
    let team = builder.building_team[i];
    let is_conv = matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
    );
    if !is_conv {
        return false;
    }
    if team != Some(builder.state.my_team) {
        return false;
    }
    let feeders = &builder.in_edges[i];
    if pyrust::len!(feeders) < 2 {
        return false;
    }

    let mut has_ti = false;
    let mut has_ax = false;
    for f in feeders {
        let fi = idx_of(*f);
        let in_ti = pyrust::set::contains!(builder.ti_upstream, &fi);
        let in_ax = pyrust::set::contains!(builder.ax_upstream, &fi);
        if in_ti && !in_ax {
            has_ti = true;
        } else if in_ax && !in_ti {
            has_ax = true;
        }
    }
    if has_ti && has_ax {
        return true;
    }

    for f in feeders {
        match _feeder_flow_kind(builder, *f) {
            Some("ti") => has_ti = true,
            Some("ax") => has_ax = true,
            _ => {}
        }
    }
    has_ti && has_ax
}

/// Derive `self.junctions` from `is_multi_input` using `_is_junction`.
pub fn update_junctions(builder: &mut Builder) {
    builder.junctions.clear();
    let candidates: Vec<Position> =
        pyrust::collect!(pyrust::map!(pyrust::iter!(builder.is_multi_input), |p| {
            pos_of(*p)
        }));
    for pos in candidates {
        if _is_junction(builder, pos) {
            pyrust::set::add!(builder.junctions, idx_of(pos));
        }
    }
}

/// Re-derive `ax_sink` every turn from three option classes.
pub fn update_foundry_target(builder: &mut Builder) {
    if pyrust::is_none!(builder.ax_ore_target)
        && pyrust::vec::is_empty!(builder.ax_harvester_adjacent)
    {
        builder.ax_sink = None;
        builder.foundry_target = None;
        return;
    }

    let origin = pyrust::unwrap_or!(builder.dangling_output, builder.state.my_pos);

    let mut junction_best: Option<Position> = None;
    let mut junction_d: i32 = 1 << 30;
    let mut ax_chain_best: Option<Position> = None;
    let mut ax_chain_d: i32 = 1 << 30;
    let mut foundry_best: Option<Position> = None;
    let mut foundry_d: i32 = 1 << 30;
    let mut ti_cand_best: Option<Position> = None;
    let mut ti_cand_d: i32 = 1 << 30;

    // Tiebreak by (y, x) so iteration order over the hash collections is
    // not observable: when two positions share the same Manhattan distance
    // from `origin`, the one with the smaller (y, x) wins deterministically.
    {
        let _g = Scope::new_timed("junctions");
        for &pi in &builder.junctions {
            let pos = pos_of(pi);
            let key = (_manhattan(origin, pos), pos.y, pos.x);
            if pyrust::is_none!(junction_best)
                || pyrust::is_some_and!(junction_best, |p| key < (junction_d, p.y, p.x))
            {
                junction_d = key.0;
                junction_best = Some(pos);
            }
        }
    }

    {
        let _g = Scope::new_timed("foundries");
        for &pi in &builder.my_foundries {
            let pos = pos_of(pi);
            let key = (_manhattan(origin, pos), pos.y, pos.x);
            if pyrust::is_none!(foundry_best)
                || pyrust::is_some_and!(foundry_best, |p| key < (foundry_d, p.y, p.x))
            {
                foundry_d = key.0;
                foundry_best = Some(pos);
            }
        }
    }

    {
        let _g = Scope::new_timed("ax_upstream");
        for &pi in &builder.ax_upstream {
            let pos = pos_of(pi);
            if !_pure_ax_merge_ok(builder, pos) {
                continue;
            }
            let key = (_manhattan(origin, pos), pos.y, pos.x);
            if pyrust::is_none!(ax_chain_best)
                || pyrust::is_some_and!(ax_chain_best, |p| key < (ax_chain_d, p.y, p.x))
            {
                ax_chain_d = key.0;
                ax_chain_best = Some(pos);
            }
        }
    }

    {
        let _g = Scope::new_timed("ti_candidates");
        for &pi in builder.reaches_core.difference(&builder.reaches_foundry) {
            let pos = pos_of(pi);
            if !_foundry_local_ok(builder, pos) {
                continue;
            }
            let key = (_manhattan(origin, pos), pos.y, pos.x);
            if pyrust::is_none!(ti_cand_best)
                || pyrust::is_some_and!(ti_cand_best, |p| key < (ti_cand_d, p.y, p.x))
            {
                ti_cand_d = key.0;
                ti_cand_best = Some(pos);
            }
        }
    }

    let mut options: Vec<(i32, Position, &'static str)> = pyrust::vec::new!();
    if let Some(p) = junction_best {
        pyrust::vec::push!(options, (junction_d, p, "junction"));
    }
    if let Some(p) = ax_chain_best {
        pyrust::vec::push!(options, (ax_chain_d, p, "ax_chain"));
    }
    if let Some(p) = foundry_best {
        pyrust::vec::push!(options, (foundry_d, p, "foundry"));
    }
    if let Some(p) = ti_cand_best {
        pyrust::vec::push!(
            options,
            (ti_cand_d + _FOUNDRY_REUSE_THRESHOLD, p, "ti_candidate")
        );
    }
    if pyrust::vec::is_empty!(options) {
        builder.ax_sink = None;
    } else {
        pyrust::sort_by_key!(options, |o| o.0);
        builder.ax_sink = Some(options[0].1);
    }

    let ft = builder.foundry_target;
    if let Some(ft) = ft {
        let fi = idx_of(ft) as usize;
        let is_transport = matches!(
            builder.building_kind[fi],
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
        ) && builder.building_team[fi] == Some(builder.state.my_team);
        let still_valid_junction =
            is_transport && pyrust::set::contains!(builder.junctions, &idx_of(ft));
        let still_valid_kind_c = is_transport
            && pyrust::set::contains!(builder.reaches_core, &idx_of(ft))
            && !pyrust::set::contains!(builder.reaches_foundry, &idx_of(ft));
        if !(still_valid_junction || still_valid_kind_c) {
            builder.foundry_target = None;
        }
    }
    if pyrust::is_none!(builder.foundry_target)
        && let Some(chosen) = builder.ax_sink
        && (pyrust::set::contains!(builder.junctions, &idx_of(chosen))
            || (_foundry_local_ok(builder, chosen) && ax_feeds_target(builder, chosen)))
    {
        builder.foundry_target = Some(chosen);
    }
}

/// Empirical Ti-sink candidate.
fn _ti_sink_ok(builder: &Builder, pos: Position) -> bool {
    let i = idx_of(pos) as usize;
    let kind = builder.building_kind[i];
    let team = builder.building_team[i];
    let is_conv = matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge)
    );
    if !is_conv {
        return false;
    }
    if team != Some(builder.state.my_team) {
        return false;
    }
    if is_inward_guard(builder, pos) {
        return false;
    }
    if pyrust::set::contains!(builder.upstream_of_dangling, &idx_of(pos))
        && pyrust::set::contains!(builder.ti_upstream, &idx_of(pos))
    {
        return false;
    }
    if pyrust::set::contains!(builder.upstream_of_congestion, &idx_of(pos)) {
        return false;
    }
    if pyrust::set::contains!(builder.ax_harvester_adjacent, &idx_of(pos)) {
        return false;
    }
    if _tile_volume(builder, pos) >= FLOW_HISTORY_LEN {
        return false;
    }
    let hist = &builder.flow_history[i];
    let mut saw_ti = false;
    for (r, _rid) in hist {
        match r {
            Some(ResourceType::RawAxionite | ResourceType::RefinedAxionite) => return false,
            Some(ResourceType::Titanium) => saw_ti = true,
            _ => {}
        }
    }
    saw_ti
}

/// Tier-1 (branch merge) requires this many Manhattan tiles saved vs.
/// routing to core.
const fn _near_core_saving_threshold(builder: &Builder) -> i32 {
    let r = builder.state.round;
    if r < 100 {
        1 + r / 20
    } else {
        6 + (r - 100) / 100
    }
}

/// Pick where new Ti chains should terminate. Three-tier preference.
pub fn update_ti_sink(builder: &mut Builder) {
    let anchor = pyrust::unwrap_or!(builder.dangling_output, builder.state.my_pos);
    let c = builder.my_core;
    let d_builder_to_core =
        pyrust::abs!((builder.state.my_pos.x - c.x)) + pyrust::abs!((builder.state.my_pos.y - c.y));
    let saving_threshold = _near_core_saving_threshold(builder);

    let mut tier1_best: Option<Position> = None;
    let mut tier1_d: i32 = 1 << 30;
    let mut tier3_best: Option<Position> = None;
    let mut tier3_d: i32 = 1 << 30;
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    let anchor_p = idx_of(anchor);
    let my_p = idx_of(builder.state.my_pos);
    for pos in &nearby {
        if !_ti_sink_ok(builder, *pos) {
            continue;
        }
        let pi = idx_of(*pos);
        let d_anchor_sq = dist_sq(anchor_p, pi);
        let d_builder_to_cand = manhat(my_p, pi);
        let saving = d_builder_to_core - d_builder_to_cand;
        if saving <= saving_threshold {
            if d_anchor_sq < tier3_d {
                tier3_d = d_anchor_sq;
                tier3_best = Some(*pos);
            }
        } else if d_anchor_sq < tier1_d {
            tier1_d = d_anchor_sq;
            tier1_best = Some(*pos);
        }
    }

    let mut tier2_best: Option<Position> = None;
    let mut tier2_d: i32 = 1 << 30;
    for edge in &builder.core_edges {
        let d = dist_sq(anchor_p, idx_of(*edge));
        if d < tier2_d {
            tier2_d = d;
            tier2_best = Some(*edge);
        }
    }

    let (best, best_d, tier): (Option<Position>, i32, i32) = if let Some(p) = tier1_best {
        (Some(p), tier1_d, 1)
    } else if let Some(p) = tier2_best {
        (Some(p), tier2_d, 2)
    } else {
        (tier3_best, tier3_d, 3)
    };

    if best != builder.ti_sink {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("from"),
                Value::String(format!("{:?}", builder.ti_sink))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("to"),
                Value::String(format!("{best:?}"))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("tier"),
                Value::Number(pyrust::into!(tier))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("anchor"),
                Value::String(format!("{anchor:?}"))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("dist_sq"),
                Value::Number(pyrust::into!(best_d))
            );
            log(
                "update_ti_sink: ti_sink changed from {from} to {to} (tier {tier}, anchor={anchor}, dist_sq={dist_sq})",
                args,
            );
        }
    }
    builder.ti_sink = best;
}

/// Pick the nearest unclaimed Ax-ore tile, gated on round AND Ti buffer.
pub fn update_ax_ore_target(builder: &mut Builder) {
    if builder.state.round < _AX_HARVESTER_ROUND_GATE {
        builder.ax_ore_target = None;
        return;
    }
    let Some((ti_base, _ax_base)) = base_cost(EntityType::Harvester) else {
        builder.ax_ore_target = None;
        return;
    };
    if builder.state.ti < 2 * ((pyrust::float!(ti_base) * builder.state.scale) as i32) {
        builder.ax_ore_target = None;
        return;
    }
    let mut candidate = pick_ax_ore_target(builder);
    let needs_pick = pyrust::is_none!(builder.ax_ore_target)
        || pyrust::is_some_and!(builder.ax_ore_target, |t| !ore_available(builder, t))
        || pyrust::is_some_and!(builder.ax_ore_target, |t| !builder.is_reachable(t))
        || pyrust::is_some_and!(builder.ax_ore_target, |t| harvester_would_contaminate(
            builder, t
        ))
        || (pyrust::is_some!(candidate)
            && pyrust::unwrap!(candidate).distance_squared(builder.state.my_pos) <= 2
            && pyrust::is_some_and!(builder.ax_ore_target, |t| t
                .distance_squared(builder.state.my_pos)
                > 2));
    if needs_pick {
        let sink = pyrust::unwrap_or!(builder.ax_sink, builder.my_core);
        if let Some(c) = candidate
            && !can_afford_ore_claim(builder, c, sink)
        {
            candidate = None;
        }
        builder.ax_ore_target = candidate;
    }
}
