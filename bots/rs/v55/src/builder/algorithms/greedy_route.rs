//! Cheap conveyor router: try a Bresenham-ish line, then two L-shaped
//! routes, falling back to A*-quality bridges only when a cardinal step
//! is blocked. No exploration, no priority queue — at worst three
//! linear walks of length `manhattan(start, target)`. Returns `None`
//! when every attempt hits a wall it can't bridge over.
//!
//! The returned path is in the same shape A* produces:
//! `[start, p1, p2, …, target]` where consecutive pairs are either
//! `r²==1` (cardinal conveyor) or `r²∈[3, 9]` (bridge).

use cambc::{Position, ResourceType};

use crate::builder::Builder;

/// Try Bresenham-ish first, then the two L-shapes in randomly-chosen
/// order. Returns the first that reaches `target`. None if all three
/// are blocked. RNG order is keyed on the bot's per-instance RNG so
/// it stays deterministic across native-Rust ⇄ pyrust-translated runs.
#[must_use]
pub fn greedy_route(
    builder: &mut Builder,
    start: Position,
    target: Position,
    resource: ResourceType,
) -> Option<Vec<Position>> {
    if start == target {
        return Some(vec![start]);
    }
    if let Some(p) = _walk_bresenham(builder, start, target, resource) {
        return Some(p);
    }
    let x_first_first = builder.state.rng.random() < 0.5;
    if let Some(p) = _walk_l(builder, start, target, resource, x_first_first) {
        return Some(p);
    }
    if let Some(p) = _walk_l(builder, start, target, resource, !x_first_first) {
        return Some(p);
    }
    None
}

#[must_use]
fn _routable(builder: &Builder, pos: Position, resource: ResourceType) -> bool {
    if !builder.in_bounds(pos) {
        return false;
    }
    let i = builder.idx(pos);
    if matches!(
        resource,
        ResourceType::RawAxionite | ResourceType::RefinedAxionite
    ) {
        builder.ax_routable[i]
    } else {
        builder.ti_routable[i]
    }
}

/// Pick a bridge destination (`r²∈[3, 9]`) that's both reachable and
/// strictly closer to `target` than `cur`. Tiebreak: smallest squared
/// distance to target, then lex on Position. Returns None if no bridge
/// makes progress.
#[must_use]
fn _greedy_bridge(
    builder: &Builder,
    cur: Position,
    target: Position,
    resource: ResourceType,
) -> Option<Position> {
    let cur_d = cur.distance_squared(target);
    let mut best: Option<Position> = None;
    let mut best_d: i32 = cur_d;
    let mut best_pos: Position = cur;
    for dx in -3..=3i32 {
        for dy in -3..=3i32 {
            let d2 = dx * dx + dy * dy;
            if d2 < 3 || d2 > 9 {
                continue;
            }
            let next = Position {
                x: cur.x + dx,
                y: cur.y + dy,
            };
            if next != target && !_routable(builder, next, resource) {
                continue;
            }
            if !builder.in_bounds(next) {
                continue;
            }
            let nd = next.distance_squared(target);
            if nd < best_d || (nd == best_d && next < best_pos) {
                best_d = nd;
                best_pos = next;
                best = Some(next);
            }
        }
    }
    best
}

/// Step one tile toward `target` in the dimension that's furthest
/// behind (Bresenham-ish: step the larger remaining axis first). On
/// block, try a greedy bridge. Returns the next position or None if
/// stuck.
#[must_use]
fn _step_toward(
    builder: &Builder,
    cur: Position,
    target: Position,
    resource: ResourceType,
) -> Option<Position> {
    let dx = target.x - cur.x;
    let dy = target.y - cur.y;
    let prefer_x = pyrust::abs!(dx) >= pyrust::abs!(dy);
    // Try the preferred axis first, then the other.
    for try_x in [prefer_x, !prefer_x] {
        if try_x && dx == 0 {
            continue;
        }
        if !try_x && dy == 0 {
            continue;
        }
        let step = if try_x {
            Position {
                x: cur.x + pyrust::signum!(dx),
                y: cur.y,
            }
        } else {
            Position {
                x: cur.x,
                y: cur.y + pyrust::signum!(dy),
            }
        };
        if step == target || _routable(builder, step, resource) {
            return Some(step);
        }
    }
    _greedy_bridge(builder, cur, target, resource)
}

#[must_use]
fn _walk_bresenham(
    builder: &Builder,
    start: Position,
    target: Position,
    resource: ResourceType,
) -> Option<Vec<Position>> {
    let mut path: Vec<Position> = vec![start];
    let mut cur = start;
    // Cap at manhattan + slack to guarantee termination on degenerate
    // cases (bridge-loops, etc.).
    let cap = pyrust::abs!(target.x - start.x) + pyrust::abs!(target.y - start.y) + 10;
    let mut iters = 0;
    while cur != target {
        if iters > cap {
            return None;
        }
        iters += 1;
        let Some(next) = _step_toward(builder, cur, target, resource) else {
            return None;
        };
        pyrust::vec::push!(path, next);
        cur = next;
    }
    Some(path)
}

/// Walk the L: do all `x` steps then all `y`, or the reverse.
#[must_use]
fn _walk_l(
    builder: &Builder,
    start: Position,
    target: Position,
    resource: ResourceType,
    x_first: bool,
) -> Option<Vec<Position>> {
    let mut path: Vec<Position> = vec![start];
    let mut cur = start;
    let phases: [(bool, i32); 2] = if x_first {
        [(true, target.x), (false, target.y)]
    } else {
        [(false, target.y), (true, target.x)]
    };
    let cap = pyrust::abs!(target.x - start.x) + pyrust::abs!(target.y - start.y) + 10;
    let mut iters = 0;
    for (is_x, target_coord) in phases {
        loop {
            let cur_coord = if is_x { cur.x } else { cur.y };
            if cur_coord == target_coord {
                break;
            }
            if iters > cap {
                return None;
            }
            iters += 1;
            let step = if is_x {
                Position {
                    x: cur.x + pyrust::signum!(target.x - cur.x),
                    y: cur.y,
                }
            } else {
                Position {
                    x: cur.x,
                    y: cur.y + pyrust::signum!(target.y - cur.y),
                }
            };
            let next;
            if step == target || _routable(builder, step, resource) {
                next = step;
            } else if let Some(b) = _greedy_bridge(builder, cur, target, resource) {
                next = b;
            } else {
                return None;
            }
            pyrust::vec::push!(path, next);
            cur = next;
        }
    }
    if cur != target {
        return None;
    }
    Some(path)
}
