//! Translation of `bots/intgrah/v54.7.9/builder/patrol.py`.

use cambc::{Controller, Position};
use serde_json::Map;

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

fn _pick_head(builder: &Builder) -> Option<Position> {
    let last_seen = &builder.last_seen;
    let rnd = builder.state.round;
    let mx = builder.state.my_pos.x;
    let my_y = builder.state.my_pos.y;
    // Score: maximise age, then minimise distance, then prefer smaller (y, x).
    // Encoded as a tuple to be minimised: (-age, dist, y, x).
    let mut best_key: (i32, i32, i32, i32) = (1, 1 << 30, 1 << 30, 1 << 30);
    let mut best_pos: Option<Position> = None;
    for pos in _candidate_iter(builder) {
        let age = rnd - last_seen[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)];
        let dx = pos.x - mx;
        let dy = pos.y - my_y;
        let d = dx * dx + dy * dy;
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

    let mut head = builder.patrol_head;
    if let Some(h) = head {
        let head_age = rnd - builder.last_seen[(h.y as usize) * MAX_WIDTH + (h.x as usize)];
        let reached = builder.state.my_pos.distance_squared(h) <= 2;
        if reached || head_age <= 0 {
            let mut args = Map::new();
            pyrust::dict::insert!(args, pyrust::to_string!("head"), auto_wrap_position(h));
            log("patrol: head {head} reached / refreshed, repicking", args);
            head = None;
        }
    }

    if pyrust::is_none!(head) {
        head = _pick_head(builder);
        if let Some(h) = head {
            let age = rnd - builder.last_seen[(h.y as usize) * MAX_WIDTH + (h.x as usize)];
            let mut args = Map::new();
            pyrust::dict::insert!(args, pyrust::to_string!("head"), auto_wrap_position(h));
            pyrust::dict::insert!(args, pyrust::to_string!("age"), serde_json::Value::Number(serde_json::Number::from(age)));
            log("patrol: new head {head} (age={age})", args);
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
