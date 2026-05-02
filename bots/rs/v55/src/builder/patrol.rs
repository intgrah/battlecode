//! Cycle-based patrol. Builders walk a deterministic Hamiltonian-ish
//! cycle through every known piece of friendly infra, starting at an
//! id-derived offset so multiple builders cover disjoint arcs of the
//! cycle in parallel. Worst-case revisit time is `cycle_len / K` for
//! `K` live patrollers.

use cambc::{Controller, Position};
use serde_json::{Map, Value};

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::util::constants::{INF, MAX_WIDTH};
use crate::util::debug::debug as log;
use crate::util::directions::DIR4;
use crate::util::visualiser::auto_wrap_position;

/// Bugnav rejects impassable goals. Return `pos` if walkable,
/// otherwise the cheapest passable cardinal neighbour.
fn _walkable_anchor(builder: &Builder, pos: Position) -> Option<Position> {
    let cost_grid = &builder.cost_grid;
    if cost_grid[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)] != INF {
        return Some(pos);
    }
    let mut best: Option<Position> = None;
    let mut best_cost = INF;
    for d in DIR4 {
        let n = pos.add(d);
        if !builder.in_bounds(n) {
            continue;
        }
        let c = cost_grid[(n.y as usize) * MAX_WIDTH + (n.x as usize)];
        if c != INF && c < best_cost {
            best_cost = c;
            best = Some(n);
        }
    }
    best
}

/// Important tiles to patrol: harvesters, foundries, the core, plus
/// every friendly transport carrying Ti or Ax (the union of
/// `ti_upstream` and `ax_upstream` covers conveyor / armoured /
/// bridge / splitter tiles that are downstream of a harvester).
fn _candidate_iter(builder: &Builder) -> Vec<Position> {
    let mut out: Vec<Position> = pyrust::vec::new!();
    pyrust::vec::extend!(out, pyrust::copied!(pyrust::iter!(builder.my_harvesters)));
    pyrust::vec::extend!(out, pyrust::copied!(pyrust::iter!(builder.my_foundries)));
    pyrust::vec::extend!(out, pyrust::copied!(pyrust::iter!(builder.ti_upstream)));
    pyrust::vec::extend!(out, pyrust::copied!(pyrust::iter!(builder.ax_upstream)));
    pyrust::vec::push!(out, builder.my_core);
    out
}

/// Build a route through every known infra tile. Nearest-neighbour
/// TSP heuristic seeded at `my_core` so the cycle starts (and loops
/// back to) the core. The seeded vec is sorted lex first so ties in
/// distance break deterministically — same cycle in native Rust and
/// pyrust-translated Python.
///
/// O(N²) for N infra tiles. Real games sit at N ≈ 30–60, so this is
/// a few thousand ops per turn — cheap relative to the per-turn
/// budget. Recomputed every call so chain growth / building loss is
/// reflected immediately.
fn _build_cycle(candidates: &Vec<Position>, seed: Position) -> Vec<Position> {
    let mut remaining: Vec<Position> = pyrust::clone!(candidates);
    pyrust::sort!(remaining);
    let mut cycle: Vec<Position> = pyrust::vec::new!();
    let mut cur = seed;
    while !pyrust::vec::is_empty!(remaining) {
        let mut best_i: usize = 0;
        let mut best_d = cur.distance_squared(remaining[0]);
        let mut best_p = remaining[0];
        for i in 1..pyrust::len!(remaining) {
            let p = remaining[i];
            let d = cur.distance_squared(p);
            if d < best_d || (d == best_d && p < best_p) {
                best_d = d;
                best_i = i;
                best_p = p;
            }
        }
        pyrust::vec::push!(cycle, best_p);
        pyrust::vec::swap_remove!(remaining, best_i);
        cur = best_p;
    }
    cycle
}

/// Walk a fixed cycle through known infra. Each builder's index into
/// the cycle is offset by `(my_id mod cycle_len)` so multiple
/// builders cover disjoint arcs without coordination. Reaching a
/// tile (`dist² <= 2`) advances the index; the next target is
/// always the next cycle entry, never the "oldest" — that's what
/// gives convergence (every tile visited every `cycle_len / K`
/// rounds) instead of greedy oldest-pick which can starve corners.
pub fn run_patrol(builder: &mut Builder, ct: &mut Controller<'_>) -> bool {
    let candidates = _candidate_iter(builder);
    if pyrust::vec::is_empty!(candidates) {
        return false;
    }
    let my_core = builder.my_core;
    let cycle = _build_cycle(&candidates, my_core);
    if pyrust::vec::is_empty!(cycle) {
        return false;
    }
    let cycle_len = pyrust::len!(cycle);

    // Seed cycle_idx by id on first call, or whenever it falls outside
    // the current cycle bounds (e.g. after infra was destroyed and the
    // cycle shrank). Modulo by cycle_len keeps it valid; the id
    // dependence spreads multiple builders around the cycle.
    let mut idx = builder.patrol_cycle_idx;
    if idx >= cycle_len {
        idx = (builder.state.my_id as usize) % cycle_len;
    }

    // Advance through any already-reached entries this turn — handles
    // the case where two consecutive cycle tiles are within dist² ≤ 2
    // of `my_pos`, so we don't waste a turn standing still.
    for _ in 0..cycle_len {
        let target = cycle[idx];
        if builder.state.my_pos.distance_squared(target) > 2 {
            break;
        }
        idx = (idx + 1) % cycle_len;
    }
    builder.patrol_cycle_idx = idx;
    let target = cycle[idx];
    builder.patrol_head = Some(target);

    let mut args = Map::new();
    pyrust::dict::insert!(args, pyrust::to_string!("target"), auto_wrap_position(target));
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("idx"),
        Value::Number(pyrust::into!(idx as i64))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("len"),
        Value::Number(pyrust::into!(cycle_len as i64))
    );
    log("patrol: cycle target {target} (idx={idx}/{len})", args);

    let Some(anchor) = _walkable_anchor(builder, target) else {
        return false;
    };
    make_move(builder, ct, anchor);
    true
}
