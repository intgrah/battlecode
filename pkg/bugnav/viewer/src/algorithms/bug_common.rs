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

/// Left-hand wall-follow priority: rotation offsets from `follow_dir`, ordered
/// -90°, -45°, 0°, +45°, +90°, +135°, +180°, -135°.
pub const LEFT_HAND_PRIORITY: [usize; 8] = [6, 7, 0, 1, 2, 3, 4, 5];

pub const fn rot_cw_90(d: usize) -> usize {
    (d + 2) % 8
}

#[must_use]
pub const fn dist_sq(a: (i32, i32), b: (i32, i32)) -> i32 {
    let dx = a.0 - b.0;
    let dy = a.1 - b.1;
    dx * dx + dy * dy
}

#[must_use]
pub fn dir_to_goal(pos: (i32, i32), goal: (i32, i32)) -> usize {
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

pub fn neighbour(pos: (i32, i32), dir: usize) -> (i32, i32) {
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
