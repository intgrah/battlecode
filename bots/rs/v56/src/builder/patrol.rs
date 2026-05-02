//! Cyclic-queue patrol with alert-graded expansion. The queue is
//! seeded at post_init with the 4 core-footprint corners; each new
//! harvester is incrementally inserted via `insert_into_queue`
//! (insertion-NN, O(N) per add). Per-turn `run_patrol` is O(1).
//!
//! The actual walk target is the cycle entry expanded radially
//! outward from `my_core` by `expansion = LOW * (1 - alert/MAX)`.
//! Alert is bumped on enemy sighting and decays. So at low alert
//! the bot patrols a fat ring 6 tiles outside the cycle (= exploration);
//! at high alert it patrols tight on infra.

use cambc::{Controller, Position};
use serde_json::{Map, Value};

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::util::constants::{INF, MAX_WIDTH};
use crate::util::debug::debug as log;
use crate::util::directions::DIR4;
use crate::util::visualiser::auto_wrap_position;

#[pyrust::inline]
const _ALERT_BOOST_TO: i32 = 30;
#[pyrust::inline]
const _ALERT_MAX: i32 = 30;
#[pyrust::inline]
const _EXPANSION_LOW: f64 = 6.0;

/// Bump alert if any enemy bot is in vision; else decay by 1 (floored
/// at 0). Capped at `_ALERT_MAX`.
pub fn update_alert(builder: &mut Builder) {
    let has_enemy = !pyrust::vec::is_empty!(builder.state.enemy_bots);
    if has_enemy {
        if builder.alert < _ALERT_BOOST_TO {
            builder.alert = _ALERT_BOOST_TO;
        }
    } else if builder.alert > 0 {
        builder.alert -= 1;
    }
    if builder.alert > _ALERT_MAX {
        builder.alert = _ALERT_MAX;
    }
}

/// Expansion magnitude in tiles: 0 at full alert, `_EXPANSION_LOW` at
/// zero alert. Linear in between.
fn _expansion(alert: i32) -> f64 {
    let t = pyrust::float!(alert) / pyrust::float!(_ALERT_MAX);
    _EXPANSION_LOW * (1.0 - t)
}

/// Push `T` outward from `core` by `expansion` tiles along the radial
/// vector. If `T == core`, return `T` unchanged.
fn _expand_outward(t: Position, core: Position, expansion: f64) -> Position {
    let dx = pyrust::float!((t.x - core.x));
    let dy = pyrust::float!((t.y - core.y));
    let len_sq = dx * dx + dy * dy;
    if len_sq <= 0.0 {
        return t;
    }
    let len = pyrust::sqrt!(len_sq);
    let factor = 1.0 + expansion / len;
    Position {
        x: pyrust::round!((dx * factor)) as i32 + core.x,
        y: pyrust::round!((dy * factor)) as i32 + core.y,
    }
}

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

/// Find the closest existing entry to `p` in the queue and insert `p`
/// right after it. If the queue is empty, just push. O(N) per call.
pub fn insert_into_queue(queue: &mut Vec<Position>, p: Position) {
    if pyrust::vec::is_empty!(queue) {
        pyrust::vec::push!(queue, p);
        return;
    }
    let mut best_i: usize = 0;
    let mut best_d = p.distance_squared(queue[0]);
    for i in 1..pyrust::len!(queue) {
        let d = p.distance_squared(queue[i]);
        if d < best_d {
            best_d = d;
            best_i = i;
        }
    }
    queue.insert(best_i + 1, p);
}

pub fn run_patrol(builder: &mut Builder, ct: &mut Controller<'_>) -> bool {
    let qlen = pyrust::len!(builder.patrol_queue);
    if qlen == 0 {
        return false;
    }
    let mut idx = builder.patrol_queue_idx;
    if idx >= qlen {
        idx = (builder.state.my_id as usize) % qlen;
    }
    let raw_target = builder.patrol_queue[idx];
    let core = builder.my_core;
    let expansion = _expansion(builder.alert);
    let mut expanded_target = _expand_outward(raw_target, core, expansion);
    if !builder.in_bounds(expanded_target) {
        expanded_target = raw_target;
    }
    let advance = builder.state.my_pos.distance_squared(expanded_target) <= 5;
    if advance {
        idx = (idx + 1) % qlen;
    }
    builder.patrol_queue_idx = idx;
    let raw_target = builder.patrol_queue[idx];
    let mut target = _expand_outward(raw_target, core, expansion);
    if !builder.in_bounds(target) {
        target = raw_target;
    }

    let mut args = Map::new();
    pyrust::dict::insert!(args, pyrust::to_string!("target"), auto_wrap_position(target));
    pyrust::dict::insert!(args, pyrust::to_string!("raw"), auto_wrap_position(raw_target));
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("alert"),
        Value::Number(pyrust::into!(builder.alert as i64))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("idx"),
        Value::Number(pyrust::into!(idx as i64))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("qlen"),
        Value::Number(pyrust::into!(qlen as i64))
    );
    log(
        "patrol: target {target} raw={raw} alert={alert} (idx={idx}/{qlen})",
        args,
    );

    let Some(anchor) = _walkable_anchor(builder, target) else {
        return false;
    };
    make_move(builder, ct, anchor);
    true
}
