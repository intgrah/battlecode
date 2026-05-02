//! Translation of `bots/intgrah/v54.7.9/builder/patrol.py`.

use crate::config::DEBUG_LOG;
use cambc::{Controller, Position};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::util::constants::INF;
use crate::util::debug::debug as log;
use crate::util::posint::{DIR4_INT, dist_sq, idx_of, pos_of};
use crate::util::visualiser::auto_wrap_position;

/// Bugnav rejects impassable goals. Return `pos` if walkable,
/// otherwise the cheapest passable cardinal neighbour.
fn _walkable_anchor(builder: &Builder, pos: Position) -> Option<Position> {
    let cost_grid = &builder.cost_grid;
    let p = idx_of(pos);
    if cost_grid[p as usize] != INF {
        return Some(pos);
    }
    let posint_valid = &builder.posint_valid;
    let mut best: Option<Position> = None;
    let mut best_cost = INF;
    for &d in &DIR4_INT {
        let np = p + d;
        if np < 0 || posint_valid[np as usize] == 0 {
            continue;
        }
        let c = cost_grid[np as usize];
        if c != INF && c < best_cost {
            best_cost = c;
            best = Some(pos_of(np));
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
    pyrust::vec::extend!(
        out,
        pyrust::map!(pyrust::iter!(builder.my_harvesters), |p| pos_of(*p))
    );
    pyrust::vec::extend!(
        out,
        pyrust::map!(pyrust::iter!(builder.my_foundries), |p| pos_of(*p))
    );
    pyrust::vec::extend!(
        out,
        pyrust::map!(pyrust::iter!(builder.ti_upstream), |p| pos_of(*p))
    );
    pyrust::vec::extend!(
        out,
        pyrust::map!(pyrust::iter!(builder.ax_upstream), |p| pos_of(*p))
    );
    pyrust::vec::push!(out, builder.my_core);
    out
}

fn _pick_head(builder: &Builder) -> Option<Position> {
    let last_seen = &builder.last_seen;
    let rnd = builder.state.round;
    let my_p = idx_of(builder.state.my_pos);
    // Score: maximise age, then minimise distance, then prefer smaller (y, x).
    // Encoded as a tuple to be minimised: (-age, dist, y, x).
    let mut best_key: (i32, i32, i32, i32) = (1, 1 << 30, 1 << 30, 1 << 30);
    let mut best_pos: Option<Position> = None;
    for pos in _candidate_iter(builder) {
        let pp = idx_of(pos);
        let age = rnd - last_seen[pp as usize];
        let d = dist_sq(my_p, pp);
        let key = (-age, d, pos.y, pos.x);
        if key < best_key {
            best_key = key;
            best_pos = Some(pos);
        }
    }
    best_pos
}

/// Walk toward the oldest important tile. Sticky: keeps the
/// previously-chosen `patrol_head` until we reach it (`dist² <= 2`)
/// or its `last_seen` advances past a margin, so the bot doesn't
/// flip-flop between two harvesters when ages tick at similar rates.
///
/// Important tiles: friendly harvesters, foundries, core, plus all
/// friendly transports carrying Ti or Ax. `last_seen` is refreshed in
/// `update_patrol` (own vision + one trusted friend's vision).
pub fn run_patrol(builder: &mut Builder, ct: &mut Controller<'_>) -> bool {
    let rnd = builder.state.round;
    let my_p = idx_of(builder.state.my_pos);

    let mut head = builder.patrol_head;
    if let Some(h) = head {
        let hp = idx_of(h);
        let head_age = rnd - builder.last_seen[hp as usize];
        let reached = dist_sq(my_p, hp) <= 2;
        if reached || head_age <= 0 {
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(args, pyrust::to_string!("head"), auto_wrap_position(h));
                log("patrol: head {head} reached / refreshed, repicking", args);
            }
            head = None;
        }
    }

    if pyrust::is_none!(head) {
        head = _pick_head(builder);
        if let Some(h) = head {
            let age = rnd - builder.last_seen[idx_of(h) as usize];
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(args, pyrust::to_string!("head"), auto_wrap_position(h));
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("age"),
                    serde_json::Value::Number(serde_json::Number::from(age))
                );
                log("patrol: new head {head} (age={age})", args);
            }
        }
    }

    builder.patrol_head = head;
    let Some(head) = head else {
        return false;
    };
    let Some(anchor) = _walkable_anchor(builder, head) else {
        return false;
    };
    make_move(builder, ct, anchor);
    true
}
