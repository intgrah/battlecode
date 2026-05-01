//! Translation of `bots/intgrah/v54.7.9/util/metrics.py`.

use cambc::Position;

/// L-1 distance.
#[must_use]
pub const fn manhattan(p1: Position, p2: Position) -> i32 {
    pyrust::abs!((p1.x - p2.x)) + pyrust::abs!((p1.y - p2.y))
}

/// L-2 distance, squared.
#[must_use]
pub const fn euclidean_sq(p1: Position, p2: Position) -> i32 {
    let dx = p1.x - p2.x;
    let dy = p1.y - p2.y;
    dx * dx + dy * dy
}

/// L-infinity distance.
#[must_use]
pub const fn chebyshev(p1: Position, p2: Position) -> i32 {
    let dx = pyrust::abs!((p1.x - p2.x));
    let dy = pyrust::abs!((p1.y - p2.y));
    if dx > dy { dx } else { dy }
}

/// Walk `path` from the end and return the furthest position whose squared
/// distance from `current_pos` is `<= max_range^2`. Falls back to
/// `current_pos` if every path position is out of range.
#[must_use]
pub fn reachable_path_end(path: &[Position], current_pos: Position, max_range: i32) -> Position {
    let limit = max_range * max_range;
    for &pos in pyrust::rev!(pyrust::iter!(path)) {
        if euclidean_sq(current_pos, pos) <= limit {
            return pos;
        }
    }
    current_pos
}

/// Returns the position in `positions` closest to `target` (by squared
/// Euclidean distance). `None` for an empty iterator. Distance ties are
/// broken by `(y, x)` lex order so the result is deterministic
/// regardless of the iterator's source ordering.
pub fn closest<I>(target: Position, positions: I) -> Option<Position>
where
    I: IntoIterator<Item = Position>,
{
    pyrust::min_by!(pyrust::into_iter!(positions), |p| (
        euclidean_sq(target, *p),
        p.y,
        p.x
    ))
}

/// Returns `true` iff `my_id` at `my_pos` is the rightful claimant of `target`
/// over all `friendlies` (by Chebyshev distance, with smaller id as tiebreak).
///
/// `friendlies` should be an iterator of `(position, id)` pairs for OTHER
/// friendly builders. See the Python source for the full reasoning.
pub fn claims_by_proximity<I>(my_pos: Position, my_id: i32, target: Position, friendlies: I) -> bool
where
    I: IntoIterator<Item = (Position, i32)>,
{
    let my_d = chebyshev(my_pos, target);
    for (fb_pos, fb_id) in friendlies {
        let fb_d = chebyshev(fb_pos, target);
        if fb_d < my_d || (fb_d == my_d && fb_id < my_id) {
            return false;
        }
    }
    true
}
