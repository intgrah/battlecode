// Indexed 0..8: N, NE, E, SE, S, SW, W, NW — 45° increments clockwise.
pub const DIRS: [(i32, i32); 8] = [
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
];
pub const DIR_NAMES: [&str; 8] = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

/// Wall-follow priority relative to `follow_dir`: offsets -90°, -45°, 0°,
/// +45°, +90°, +135°, +180°, -135°. Combined with the convention that
/// `follow_dir` is initialised to `rot_cw_90(blocked_dir)`, the first offset
/// (-90°) evaluates the blocked direction itself, and the sequence matches
/// bc22-style "try direction-to-target, rotate right until passable, then
/// continue rotating left after a successful move".
pub const LEFT_HAND_PRIORITY: [usize; 8] = [6, 7, 0, 1, 2, 3, 4, 5];

#[must_use]
pub const fn rot_cw_90(d: usize) -> usize {
    (d + 2) % 8
}

#[must_use]
pub const fn rot_ccw_90(d: usize) -> usize {
    (d + 6) % 8
}

#[must_use]
pub const fn dist_sq(a: (i32, i32), b: (i32, i32)) -> i32 {
    let dx = a.0 - b.0;
    let dy = a.1 - b.1;
    dx * dx + dy * dy
}

#[must_use]
pub const fn dir_to_goal(pos: (i32, i32), goal: (i32, i32)) -> usize {
    let dx = (goal.0 - pos.0).signum();
    let dy = (goal.1 - pos.1).signum();
    match (dx, dy) {
        (0, -1) => 0,
        (1, -1) => 1,
        (1, 0) => 2,
        (1, 1) => 3,
        (0, 1) => 4,
        (-1, 1) => 5,
        (-1, 0) => 6,
        (-1, -1) => 7,
        _ => 0,
    }
}

#[must_use]
pub const fn neighbour(pos: (i32, i32), dir: usize) -> (i32, i32) {
    (pos.0 + DIRS[dir].0, pos.1 + DIRS[dir].1)
}

/// Left-hand wall-follow step: try each rotation offset in [`LEFT_HAND_PRIORITY`],
/// return `Some((new_pos, new_follow_dir))` on the first passable direction,
/// or `None` if every neighbour is blocked.
pub fn follow_step(
    pos: (i32, i32),
    follow_dir: usize,
    passable: impl Fn(i32, i32) -> bool,
) -> Option<((i32, i32), usize)> {
    for off in LEFT_HAND_PRIORITY {
        let nd = (follow_dir + off) % 8;
        let np = neighbour(pos, nd);
        if passable(np.0, np.1) {
            return Some((np, nd));
        }
    }
    None
}

/// Wall-follow state anchored to a specific obstacle cell. See
/// [`wall_follow_step`]. Keeping `current_obstacle` explicit prevents drift:
/// each rotation is computed relative to the direction-to-obstacle rather
/// than "the direction I last moved".
#[derive(Clone, Copy, Debug)]
pub struct WallFollowState {
    pub pos: (i32, i32),
    pub current_obstacle: (i32, i32),
    /// true = right-hand-on-wall (rotate CCW from dir-to-obstacle per step).
    /// false = left-hand (rotate CW).
    pub obstacle_on_right: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WallStepOutcome {
    Moved,
    /// All 8 rotations blocked by walls/edges with no edge-flip available.
    Surrounded,
}

/// Returns the direction index (0..8) from `from` to `to` based on sign of
/// delta. `to` must not equal `from`; if they're equal returns N arbitrarily.
#[must_use]
pub const fn direction_to_cell(from: (i32, i32), to: (i32, i32)) -> usize {
    let dx = (to.0 - from.0).signum();
    let dy = (to.1 - from.1).signum();
    match (dx, dy) {
        (0, -1) => 0,
        (1, -1) => 1,
        (1, 0) => 2,
        (1, 1) => 3,
        (0, 1) => 4,
        (-1, 1) => 5,
        (-1, 0) => 6,
        (-1, -1) => 7,
        _ => 0,
    }
}

/// Canonical wall-follow step.
///
/// 1. Compute direction from `state.pos` to `state.current_obstacle`.
/// 2. Rotate that direction 45° away from the wall (CCW if wall on right,
///    CW if wall on left).
/// 3. If the cell in that direction is passable, move there and return
///    `Moved`. Otherwise, if it's a wall cell on the map, update
///    `current_obstacle` to that cell (we're now hugging this new wall)
///    and continue rotating.
/// 4. If it's off-map, flip `obstacle_on_right` once and restart the
///    rotation. (This handles obstacles that touch the map border — bc25's
///    edge-flip trick.)
/// 5. After 8 rotations without moving, return `Surrounded`.
///
/// `passable(x, y)` returns true iff the cell is passable. `on_map(x, y)`
/// returns true iff the cell is within the grid (independent of walls).
pub fn wall_follow_step(
    state: &mut WallFollowState,
    passable: impl Fn(i32, i32) -> bool,
    on_map: impl Fn(i32, i32) -> bool,
) -> WallStepOutcome {
    wall_follow_step_inner(state, &passable, &on_map, true)
}

fn wall_follow_step_inner(
    state: &mut WallFollowState,
    passable: &impl Fn(i32, i32) -> bool,
    on_map: &impl Fn(i32, i32) -> bool,
    can_flip: bool,
) -> WallStepOutcome {
    let mut direction = direction_to_cell(state.pos, state.current_obstacle);
    for _ in 0..8 {
        direction = if state.obstacle_on_right {
            (direction + 7) % 8 // rotate left (CCW)
        } else {
            (direction + 1) % 8 // rotate right (CW)
        };
        let next = neighbour(state.pos, direction);
        if passable(next.0, next.1) {
            state.pos = next;
            return WallStepOutcome::Moved;
        }
        if on_map(next.0, next.1) {
            // Blocked by a wall on the map — now hugging this wall cell.
            state.current_obstacle = next;
        } else if can_flip {
            // Off-map edge. Flip side once and restart from dir-to-obstacle.
            state.obstacle_on_right = !state.obstacle_on_right;
            return wall_follow_step_inner(state, passable, on_map, false);
        }
    }
    WallStepOutcome::Surrounded
}

/// Builder bot vision: cells `c` with `dist_sq(pos, c) ≤ VISION_R_SQ` are
/// sensed. Yields exactly 69 cells including the origin.
pub const VISION_R_SQ: i32 = 20;

/// All cells within sensor range of `origin` (69 cells including origin).
pub fn sensed_cells(origin: (i32, i32)) -> impl Iterator<Item = (i32, i32)> {
    (-4..=4).flat_map(move |dy| {
        (-4..=4).filter_map(move |dx| {
            if dx * dx + dy * dy <= VISION_R_SQ {
                Some((origin.0 + dx, origin.1 + dy))
            } else {
                None
            }
        })
    })
}

/// True iff `target` is within sensor range of `from` AND every cell on the
/// Bresenham line from `from` (exclusive) to `target` (inclusive) is passable.
pub fn has_los(from: (i32, i32), target: (i32, i32), passable: impl Fn(i32, i32) -> bool) -> bool {
    if dist_sq(from, target) > VISION_R_SQ {
        return false;
    }
    let line = bresenham(from, target);
    line.iter().skip(1).all(|&p| passable(p.0, p.1))
}

/// Farthest passable cell reachable along the Bresenham line from `from`
/// (exclusive) toward `toward`, capped at the sensor range. Returns the
/// farthest clear cell, or `from` itself if the first cell along the ray is
/// already blocked.
pub fn farthest_visible_along(
    from: (i32, i32),
    toward: (i32, i32),
    passable: impl Fn(i32, i32) -> bool,
) -> (i32, i32) {
    if from == toward {
        return from;
    }
    let line = bresenham(from, toward);
    let mut last_clear = from;
    for &p in line.iter().skip(1) {
        if dist_sq(from, p) > VISION_R_SQ {
            break;
        }
        if !passable(p.0, p.1) {
            break;
        }
        last_clear = p;
    }
    last_clear
}

/// Local 8-connected BFS from `start` over cells within sensor range
/// (`dist_sq ≤ VISION_R_SQ`). Returns a parent map; cells reachable from
/// `start` appear as keys, with their predecessors on the shortest path
/// from `start`. `start` itself is not in the map.
pub fn local_bfs(
    start: (i32, i32),
    passable: impl Fn(i32, i32) -> bool,
) -> std::collections::HashMap<(i32, i32), (i32, i32)> {
    use std::collections::{HashMap, HashSet, VecDeque};
    const DIRS8: [(i32, i32); 8] = [
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    ];
    let mut queue: VecDeque<(i32, i32)> = VecDeque::new();
    let mut parent: HashMap<(i32, i32), (i32, i32)> = HashMap::new();
    let mut visited: HashSet<(i32, i32)> = HashSet::new();
    queue.push_back(start);
    visited.insert(start);
    while let Some(p) = queue.pop_front() {
        for (dx, dy) in DIRS8 {
            let n = (p.0 + dx, p.1 + dy);
            if dist_sq(start, n) > VISION_R_SQ {
                continue;
            }
            if !passable(n.0, n.1) {
                continue;
            }
            if !visited.insert(n) {
                continue;
            }
            parent.insert(n, p);
            queue.push_back(n);
        }
    }
    parent
}

/// Integer Bresenham line between `a` (inclusive) and `b` (inclusive).
#[must_use]
pub fn bresenham(a: (i32, i32), b: (i32, i32)) -> Vec<(i32, i32)> {
    let (mut x0, mut y0) = a;
    let (x1, y1) = b;
    let dx = (x1 - x0).abs();
    let dy = -(y1 - y0).abs();
    let sx = if x0 < x1 { 1 } else { -1 };
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx + dy;
    let mut out = Vec::new();
    loop {
        out.push((x0, y0));
        if x0 == x1 && y0 == y1 {
            break;
        }
        let e2 = 2 * err;
        if e2 >= dy {
            err += dy;
            x0 += sx;
        }
        if e2 <= dx {
            err += dx;
            y0 += sy;
        }
    }
    out
}
