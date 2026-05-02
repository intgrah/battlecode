use std::collections::HashSet;

use cambc::{Controller, ControllerApi, EntityType, Environment, Position, ResourceType};
use serde_json::{Map, Value};

use crate::builder::Builder;
use crate::builder::helpers::{
    can_afford_ax_claim, can_afford_ti_claim, is_inward_guard, ore_available,
    pick_offensive_ti_ore_target, pick_ore,
};
use crate::util::constants::{AX_ROUND_GATE, INF, MAX_WIDTH};
use crate::util::debug::debug as log;
use crate::util::directions::DIR4;
use crate::util::metrics::{chebyshev, claims_by_proximity};

pub fn update_map_econ(builder: &mut Builder, ct: &mut Controller<'_>) {
    let prev_unconn = pyrust::set::clone!(builder.adjacent_to_unconnected_harvester);
    builder.adjacent_to_unconnected_harvester = pyrust::set::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(builder.adjacent_to_unconnected_harvester)),
        |p| !pyrust::unwrap!(ct.is_in_vision(*p))
    ));
    builder.adjacent_to_harvester = pyrust::set::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(builder.adjacent_to_harvester)),
        |p| !pyrust::unwrap!(ct.is_in_vision(*p))
    ));

    // Pass 1: scan visible harvesters to maintain
    // `adjacent_to_unconnected_harvester` and `adjacent_to_harvester`.
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    let my_team = builder.state.my_team;
    for pos in &nearby {
        let pos = *pos;
        if builder.kind_at(pos) != Some(EntityType::Harvester) {
            continue;
        }
        let mut adjacent_conveyor = false;
        for d in DIR4 {
            let n = pos.add(d);
            if !builder.in_bounds(n) {
                continue;
            }
            let ni = builder.idx(n);
            let nk = builder.building_kind[ni];
            let nt = builder.building_team[ni];
            match nk {
                Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
                    if nt == Some(my_team) =>
                {
                    // Inward conveyors don't count as consumers (treated as
                    // if no building exists).
                    if !is_inward_guard(builder, n) {
                        adjacent_conveyor = true;
                        break;
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
            for d in DIR4 {
                let n = pos.add(d);
                if builder.in_bounds(n) {
                    pyrust::set::add!(builder.adjacent_to_unconnected_harvester, n);
                }
            }
        }
        for d in DIR4 {
            let n = pos.add(d);
            if builder.in_bounds(n) {
                pyrust::set::add!(builder.adjacent_to_harvester, n);
            }
        }
    }

    // Pass 2: movement cost_grid per-turn penalties for enemy turret rays
    // and launcher adjacency.
    for pos in &nearby {
        let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
        if builder.cost_grid[i] != INF {
            if pyrust::vec::contains!(builder.adjacent_to_enemy_launcher, pos) {
                builder.cost_grid[i] += 20;
            }
            if pyrust::vec::contains!(builder.enemy_turret_ray_tiles, pos) {
                builder.cost_grid[i] += 15;
            }
        }
    }

    // Reconcile dangling_set with harvester-adjacency changes. Sort by
    // (y, x) so any logs / side-effect ordering inside `_check_dangling`
    // are deterministic across hash-randomized iteration.
    let mut changed: Vec<Position> = pyrust::collect!(pyrust::copied!(
        prev_unconn.symmetric_difference(&builder.adjacent_to_unconnected_harvester)
    ));
    pyrust::sort_by_key!(changed, |p| (p.y, p.x));
    for p in changed {
        builder._check_dangling(p, "unconn_flip");
    }

    // Re-validate every visible tile. _check_dangling early-exits cheaply
    // on non-admitted tiles. This catches inward conveyors that just
    // became inward (a builder/harvester appeared on the target ore) and
    // any other classification drift that incremental triggers miss.
    let mut visible_tiles: Vec<Position> = pyrust::clone!(builder.state.nearby_tiles);
    pyrust::sort_by_key!(visible_tiles, |p| (p.y, p.x));
    for p in visible_tiles {
        builder._check_dangling(p, "visible_revalidate");
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
fn flood_forward(out_edges: &[Vec<Position>], seeds: &HashSet<Position>) -> HashSet<Position> {
    let mut target: HashSet<Position> = pyrust::set::new!();
    let mut stack: Vec<Position> = pyrust::vec::new!();
    for s in seeds {
        if pyrust::vec::contains!(target, s) {
            continue;
        }
        if pyrust::vec::is_empty!(out_edges[(s.y as usize) * MAX_WIDTH + (s.x as usize)]) {
            continue;
        }
        pyrust::set::add!(target, *s);
        pyrust::vec::push!(stack, *s);
    }
    while let Some(p) = pyrust::vec::pop!(stack) {
        for out in &out_edges[(p.y as usize) * MAX_WIDTH + (p.x as usize)] {
            if pyrust::vec::contains!(target, out) {
                continue;
            }
            pyrust::set::add!(target, *out);
            pyrust::vec::push!(stack, *out);
        }
    }
    target
}

/// Chebyshev distance from `pos` to its nearest `core_edge` (or `my_core`
/// if `core_edges` is empty — shouldn't happen post-init).
fn chebyshev_to_nearest_core_edge(builder: &Builder, pos: Position) -> i32 {
    let mut best_d = INF;
    for e in &builder.core_edges {
        let d = chebyshev(pos, *e);
        if d < best_d {
            best_d = d;
        }
    }
    if best_d == INF {
        chebyshev(pos, builder.my_core)
    } else {
        best_d
    }
}

#[must_use]
pub fn pick_dangling_output(builder: &Builder, ct: Option<&Controller<'_>>) -> Option<Position> {
    let friendly: Vec<(Position, i32)> = pyrust::collect!(pyrust::map!(
        pyrust::filter!(pyrust::dict::items!(builder.state.all_bots), |t| {
            *t.1 != builder.state.my_id && pyrust::vec::contains!(builder.state.friendly_bots, t.0)
        }),
        |t| (*t.0, *t.1)
    ));
    let en_core = if pyrust::is_some!(builder.symmetry) {
        Some(builder.en_core_guess)
    } else {
        None
    };
    let mut best: Option<Position> = None;
    // Tiebreak by (y, x) on top of (my_d, chain_d) so iteration order over
    // the hash collection isn't observable.
    let mut best_score: (i32, i32, i32, i32) = (1 << 30, 1 << 30, 1 << 30, 1 << 30);
    let dangling_iter: Vec<Position> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.dangling_set)));
    for pos in dangling_iter {
        if !builder.is_reachable(pos) {
            continue;
        }
        if let Some(c) = ct
            && !pyrust::unwrap!(c.is_in_vision(pos))
        {
            continue;
        }
        if !claims_by_proximity(
            builder.state.my_pos,
            builder.state.my_id,
            pos,
            pyrust::copied!(pyrust::iter!(friendly)),
        ) {
            continue;
        }
        let my_d = chebyshev(builder.state.my_pos, pos);
        let chain_d = match en_core {
            Some(ec) if pos.distance_squared(ec) < pos.distance_squared(builder.my_core) => {
                chebyshev(pos, ec)
            }
            _ => chebyshev_to_nearest_core_edge(builder, pos),
        };
        let score = (my_d, chain_d, pos.y, pos.x);
        if score < best_score {
            best_score = score;
            best = Some(pos);
        }
    }
    best
}

pub fn update_ti_ore_target(builder: &mut Builder, friendlies: &[(Position, i32)]) {
    let mut candidate_ore = pick_ore(builder, Environment::OreTitanium, friendlies);
    let needs_pick = pyrust::is_none!(builder.ore_target)
        || pyrust::is_some_and!(builder.ore_target, |t| !ore_available(builder, t))
        || pyrust::is_some_and!(builder.ore_target, |t| !builder.is_reachable(t))
        || (pyrust::is_some!(candidate_ore)
            && pyrust::unwrap!(candidate_ore).distance_squared(builder.state.my_pos) <= 2
            && pyrust::is_some_and!(builder.ore_target, |t| t
                .distance_squared(builder.state.my_pos)
                > 2));
    if needs_pick {
        builder.ore_target = candidate_ore;
    }
}

/// Enemy-side Ti ore claim. Same re-evaluation semantics as
/// `update_ore_target`: keep the current pick if still valid and not
/// trivially beaten by a much-closer alternative.
pub fn update_offensive_ore_target(builder: &mut Builder, friendlies: &[(Position, i32)]) {
    let mut candidate = pick_offensive_ti_ore_target(builder, friendlies);
    let needs_pick = pyrust::is_none!(builder.offensive_ore_target)
        || pyrust::is_some_and!(builder.offensive_ore_target, |t| !ore_available(builder, t))
        || pyrust::is_some_and!(builder.offensive_ore_target, |t| !builder.is_reachable(t))
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
            && !can_afford_ti_claim(builder, c, s)
        {
            candidate = None;
        }
        builder.offensive_ore_target = candidate;
    }
}

/// Occupancy count: non-None entries in the tile's `flow_history`.
fn _tile_volume(builder: &Builder, pos: Position) -> usize {
    pyrust::count!(pyrust::filter!(
        pyrust::iter!(builder.flow_history[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)]),
        |t| pyrust::is_some!(t.0)
    ))
}

/// True iff `pos`'s flow_history contains only Ti, no Ax.
/// Empty flow_history returns false.
fn _flow_is_pure_ti(builder: &Builder, pos: Position) -> bool {
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    let mut saw_ti = false;
    for (r, _) in &builder.flow_history[i] {
        match r {
            Some(ResourceType::Titanium) => saw_ti = true,
            Some(ResourceType::RawAxionite | ResourceType::RefinedAxionite) => return false,
            _ => {}
        }
    }
    saw_ti
}

/// True iff `pos`'s flow_history contains only Ax (raw or refined), no Ti.
/// Empty flow_history returns false.
fn _flow_is_pure_ax(builder: &Builder, pos: Position) -> bool {
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    let mut saw_ax = false;
    for (r, _) in &builder.flow_history[i] {
        match r {
            Some(ResourceType::RawAxionite | ResourceType::RefinedAxionite) => saw_ax = true,
            Some(ResourceType::Titanium) => return false,
            _ => {}
        }
    }
    saw_ax
}

/// True iff `pos`'s flow_history contains any Ax (raw or refined).
fn _flow_has_ax(builder: &Builder, pos: Position) -> bool {
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    for (r, _) in &builder.flow_history[i] {
        if matches!(
            r,
            Some(ResourceType::RawAxionite | ResourceType::RefinedAxionite)
        ) {
            return true;
        }
    }
    false
}

/// True iff `pos` is a friendly Conveyor/ArmouredConveyor cardinally
/// adjacent to a friendly Ti harvester, carrying pure Ti, not an inward
/// guard, reachable. The future foundry spot before any Ax arrives.
/// Existing built foundries are handled separately in
/// `update_foundry_target` and don't need this rule.
/// True iff every in-edge of `pos` has pure-Ti flow history. Used when
/// `pos` itself has mixed flow (a transient Ax packet), but all its
/// sources are Ti-only, so the foundry candidate is still valid.
fn _flow_is_mixed_with_pure_sources(builder: &Builder, pos: Position) -> bool {
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    if pyrust::vec::is_empty!(builder.in_edges[i]) {
        return false;
    }
    for src in &builder.in_edges[i] {
        if !_flow_is_pure_ti(builder, *src) {
            return false;
        }
    }
    true
}

fn _foundry_candidate_ok(builder: &Builder, pos: Position) -> bool {
    if !builder.is_reachable(pos) {
        return false;
    }
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    let kind = builder.building_kind[i];
    let team = builder.building_team[i];
    if !matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
    ) {
        return false;
    }
    if team != Some(builder.state.my_team) {
        return false;
    }
    if is_inward_guard(builder, pos) {
        return false;
    }
    let mut adj_ti_harv = false;
    for d in DIR4 {
        let n = pos.add(d);
        if !builder.in_bounds(n) {
            continue;
        }
        let ni = (n.y as usize) * MAX_WIDTH + (n.x as usize);
        if builder.building_kind[ni] == Some(EntityType::Harvester)
            && builder.building_team[ni] == Some(builder.state.my_team)
            && builder.env[ni] == Some(Environment::OreTitanium)
        {
            adj_ti_harv = true;
            break;
        }
    }
    if !adj_ti_harv {
        return false;
    }
    _flow_is_pure_ti(builder, pos) || _flow_is_mixed_with_pure_sources(builder, pos)
}

const fn _manhattan(a: Position, b: Position) -> i32 {
    pyrust::abs!((a.x - b.x)) + pyrust::abs!((a.y - b.y))
}

/// Oracle: recompute the incrementally-maintained sets from scratch
/// using the current `in_edges` / `out_edges` / harvester-adjacent state,
/// and assert equality with the live values.
pub fn check_invariants(builder: &Builder) {
    let out_edges = &builder.out_edges;
    let in_edges = &builder.in_edges;

    // --- A: harvester-adjacent set vs counter ---
    let idx_to_pos = &builder.idx_to_pos;
    let expected_ti_adj: HashSet<Position> = pyrust::collect!(pyrust::filter_map!(
        pyrust::enumerate!(pyrust::iter!(builder._ti_harv_at)),
        |t| {
            if *t.1 > 0 {
                Some(idx_to_pos[t.0])
            } else {
                None
            }
        }
    ));
    let expected_ax_adj: HashSet<Position> = pyrust::collect!(pyrust::filter_map!(
        pyrust::enumerate!(pyrust::iter!(builder._ax_harv_at)),
        |t| {
            if *t.1 > 0 {
                Some(idx_to_pos[t.0])
            } else {
                None
            }
        }
    ));
    if expected_ti_adj != builder.ti_harvester_adjacent {
        let mut args = Map::new();
        let mut missing: Vec<Position> = pyrust::collect!(pyrust::copied!(
            expected_ti_adj.difference(&builder.ti_harvester_adjacent)
        ));
        missing.sort();
        let mut extra: Vec<Position> = pyrust::collect!(pyrust::copied!(
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
        let mut missing: Vec<Position> = pyrust::collect!(pyrust::copied!(
            expected_ax_adj.difference(&builder.ax_harvester_adjacent)
        ));
        missing.sort();
        let mut extra: Vec<Position> = pyrust::collect!(pyrust::copied!(
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
        let mut miss: Vec<Position> =
            pyrust::collect!(pyrust::copied!(oracle_ti.difference(&builder.ti_upstream)));
        miss.sort();
        pyrust::vec::truncate!(miss, 8);
        let mut extra: Vec<Position> =
            pyrust::collect!(pyrust::copied!(builder.ti_upstream.difference(&oracle_ti)));
        extra.sort();
        pyrust::vec::truncate!(extra, 8);
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
        for t in pyrust::take!(pyrust::iter!(miss), 4) {
            let i = (t.y as usize) * MAX_WIDTH + (t.x as usize);
            let feeders: Vec<(Position, bool, bool)> =
                pyrust::collect!(pyrust::map!(pyrust::iter!(in_edges[i]), |f| (
                    *f,
                    pyrust::vec::contains!(builder.ti_upstream, f),
                    pyrust::vec::contains!(oracle_ti, f)
                )));
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("t"),
                Value::String(format!("{t:?}"))
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
    if oracle_ax != builder.ax_upstream {
        let mut miss: Vec<Position> =
            pyrust::collect!(pyrust::copied!(oracle_ax.difference(&builder.ax_upstream)));
        miss.sort();
        pyrust::vec::truncate!(miss, 8);
        let mut extra: Vec<Position> =
            pyrust::collect!(pyrust::copied!(builder.ax_upstream.difference(&oracle_ax)));
        extra.sort();
        pyrust::vec::truncate!(extra, 8);
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
        for t in pyrust::take!(pyrust::iter!(miss), 4) {
            let i = (t.y as usize) * MAX_WIDTH + (t.x as usize);
            let feeders: Vec<(Position, bool, bool)> =
                pyrust::collect!(pyrust::map!(pyrust::iter!(in_edges[i]), |f| (
                    *f,
                    pyrust::vec::contains!(builder.ax_upstream, f),
                    pyrust::vec::contains!(oracle_ax, f)
                )));
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("t"),
                Value::String(format!("{t:?}"))
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

    // --- C: in-count drift (independent of B's outcome) ---
    for i in 0..pyrust::len!(in_edges) {
        if pyrust::vec::is_empty!(in_edges[i]) {
            if builder._ti_in_count[i] != 0 || builder._ax_in_count[i] != 0 {
                let t = builder.idx_to_pos[i];
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
            continue;
        }
        let ti_expected = pyrust::count!(pyrust::filter!(
            pyrust::iter!(in_edges[i]),
            |f| pyrust::vec::contains!(builder.ti_upstream, f)
        )) as i32;
        let ax_expected = pyrust::count!(pyrust::filter!(
            pyrust::iter!(in_edges[i]),
            |f| pyrust::vec::contains!(builder.ax_upstream, f)
        )) as i32;
        if ti_expected != builder._ti_in_count[i] {
            let t = builder.idx_to_pos[i];
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
        if ax_expected != builder._ax_in_count[i] {
            let t = builder.idx_to_pos[i];
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

/// Pick `ax_sink` and `foundry_target` per the simplified rules:
///   1. nearest in-vision foundry candidate (friendly conveyor adj-Ti-harvester
///      with pure-Ax feeder, not inward-guard) — also sets `foundry_target`.
///   2. else nearest pure-Ax merge conveyor — `foundry_target` cleared.
pub fn update_foundry_target(builder: &mut Builder) {
    if pyrust::is_none!(builder.ax_ore_target)
        && pyrust::vec::is_empty!(builder.ax_harvester_adjacent)
    {
        builder.ax_sink = None;
        builder.foundry_target = None;
        return;
    }
    let origin = pyrust::unwrap_or!(builder.dangling_output, builder.state.my_pos);

    let mut found_best: Option<Position> = None;
    let mut found_key: (i32, i32, i32) = (i32::MAX, 0, 0);
    let nearby = pyrust::clone!(builder.nearby_buildings);
    for pos in &nearby {
        let key = (_manhattan(origin, *pos), pos.y, pos.x);
        if _foundry_candidate_ok(builder, *pos) && key < found_key {
            found_key = key;
            found_best = Some(*pos);
        }
    }
    builder.ax_sink = found_best;
    builder.foundry_target = found_best;
}

/// Basic Ti-sink candidate filter: friendly Conveyor / ArmouredConveyor /
/// Bridge, reachable, not an inward guard, no Ax in flow_history.
/// Congestion is checked separately by walking the downstream chain in
/// `update_ti_sink`.
fn _ti_sink_ok(builder: &Builder, pos: Position) -> bool {
    if !builder.is_reachable(pos) {
        return false;
    }
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    let kind = builder.building_kind[i];
    let team = builder.building_team[i];
    if !matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge)
    ) {
        return false;
    }
    if team != Some(builder.state.my_team) {
        return false;
    }
    if is_inward_guard(builder, pos) {
        return false;
    }
    !_flow_has_ax(builder, pos)
}

/// Walk the downstream chain from `t` via `out_edges`. Visits transport
/// tiles (Conveyor / ArmouredConveyor / Bridge / Splitter) and stops at
/// Core (excluded) or Foundry (included). Branches that terminate
/// elsewhere (dangling) are dead — they don't count as reaching a sink.
/// Returns `Some(max_volume)` over all visited transport tiles iff at
/// least one branch reaches a Core or Foundry; else `None`.
fn _downstream_chain_max_vol(builder: &Builder, t: Position) -> Option<i32> {
    let mut visited: HashSet<Position> = pyrust::set::new!();
    let mut stack: Vec<Position> = vec![t];
    let mut max_vol: i32 = 0;
    let mut reached_sink = false;
    while let Some(p) = pyrust::vec::pop!(stack) {
        if pyrust::vec::contains!(visited, &p) {
            continue;
        }
        pyrust::set::add!(visited, p);
        let i = (p.y as usize) * MAX_WIDTH + (p.x as usize);
        let kind = builder.building_kind[i];
        let team = builder.building_team[i];
        match kind {
            Some(EntityType::Core) if team == Some(builder.state.my_team) => {
                reached_sink = true;
            }
            Some(EntityType::Foundry) if team == Some(builder.state.my_team) => {
                reached_sink = true;
                let v = _tile_volume(builder, p) as i32;
                if v > max_vol {
                    max_vol = v;
                }
            }
            Some(
                EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Bridge
                | EntityType::Splitter,
            ) if team == Some(builder.state.my_team) => {
                let v = _tile_volume(builder, p) as i32;
                if v > max_vol {
                    max_vol = v;
                }
                for o in &builder.out_edges[i] {
                    pyrust::vec::push!(stack, *o);
                }
            }
            _ => {
                // Dangling / non-transport — branch dies.
            }
        }
    }
    if reached_sink { Some(max_vol) } else { None }
}

/// Pick where new Ti chains should terminate. Find the closest valid
/// candidate (friendly conveyor / armoured / bridge, not inward,
/// reachable, no Ax in flow_history). Run the downstream-chain check
/// once on it: walk via `out_edges` to core (excluded) or foundry
/// (included); require at least one branch reaches a real sink, AND
/// max tile volume <= 6. If congested, fall back to nearest reachable
/// core_edge — do not try other conveyor candidates.
pub fn update_ti_sink(builder: &mut Builder) {
    let anchor = pyrust::unwrap_or!(builder.dangling_output, builder.state.my_pos);

    let mut best_cand: Option<Position> = None;
    let mut best_d: i32 = 1 << 30;
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    for pos in &nearby {
        if !_ti_sink_ok(builder, *pos) {
            continue;
        }
        let d = pyrust::abs!((anchor.x - pos.x)) + pyrust::abs!((anchor.y - pos.y));
        if d < best_d {
            best_d = d;
            best_cand = Some(*pos);
        }
    }

    let mut chosen: Option<Position> = None;
    if let Some(cand) = best_cand
        && let Some(max_vol) = _downstream_chain_max_vol(builder, cand)
        && max_vol <= 6
    {
        chosen = Some(cand);
    }

    if pyrust::is_none!(chosen) {
        let mut bd: i32 = 1 << 30;
        for edge in &builder.core_edges {
            if !builder.is_reachable(*edge) {
                continue;
            }
            let d = pyrust::abs!((anchor.x - edge.x)) + pyrust::abs!((anchor.y - edge.y));
            if d < bd {
                bd = d;
                chosen = Some(*edge);
            }
        }
    }

    if chosen != builder.ti_sink {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("from"),
            Value::String(format!("{:?}", builder.ti_sink))
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("to"),
            Value::String(format!("{chosen:?}"))
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("anchor"),
            Value::String(format!("{anchor:?}"))
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("cand"),
            Value::String(format!("{best_cand:?}"))
        );
        log(
            "update_ti_sink: ti_sink changed from {from} to {to} (anchor={anchor}, cand={cand})",
            args,
        );
    }
    builder.ti_sink = chosen;
}

/// Pick the nearest unclaimed Ax-ore tile, gated on round only —
/// affordability is handled by `can_afford_ax_claim` below.
pub fn update_ax_ore_target(builder: &mut Builder, friendlies: &[(Position, i32)]) {
    if builder.state.round < AX_ROUND_GATE {
        builder.ax_ore_target = None;
        return;
    }
    let mut candidate = pick_ore(builder, Environment::OreAxionite, friendlies);
    let needs_pick = pyrust::is_none!(builder.ax_ore_target)
        || pyrust::is_some_and!(builder.ax_ore_target, |t| !ore_available(builder, t))
        || pyrust::is_some_and!(builder.ax_ore_target, |t| !builder.is_reachable(t))
        || (pyrust::is_some!(candidate)
            && pyrust::unwrap!(candidate).distance_squared(builder.state.my_pos) <= 2
            && pyrust::is_some_and!(builder.ax_ore_target, |t| t
                .distance_squared(builder.state.my_pos)
                > 2));
    if needs_pick {
        let sink = pyrust::unwrap_or!(builder.ax_sink, builder.my_core);
        if let Some(c) = candidate
            && !can_afford_ax_claim(builder, c, sink)
        {
            candidate = None;
        }
        builder.ax_ore_target = candidate;
    }
}
