//! Translation of `bots/intgrah/v54.7.9/util/directions.py`.

use cambc::{Direction, Position};

/// `N, NE, E, SE, S, SW, W, NW` — the eight non-CENTRE directions, in
/// `EntityType` enum order (matches Python `[d for d in Direction if d != CENTRE]`).
pub const DIR8: [Direction; 8] = [
    Direction::North,
    Direction::Northeast,
    Direction::East,
    Direction::Southeast,
    Direction::South,
    Direction::Southwest,
    Direction::West,
    Direction::Northwest,
];

/// Cardinal directions only: `N, E, S, W`.
pub const DIR4: [Direction; 4] = [
    Direction::North,
    Direction::East,
    Direction::South,
    Direction::West,
];

/// True for the four cardinal directions (N/E/S/W). Mirrors the Rust
/// `Direction::is_cardinal()` helper from `cambc-libre-engine`, which has no
/// Python counterpart on `cambc.Direction`.
#[must_use]
pub const fn is_cardinal(d: Direction) -> bool {
    matches!(
        d,
        Direction::North | Direction::East | Direction::South | Direction::West
    )
}

/// Rotate a direction 45° clockwise. `Centre` is a no-op.
#[must_use]
pub const fn rotate_right(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::Northeast,
        Direction::Northeast => Direction::East,
        Direction::East => Direction::Southeast,
        Direction::Southeast => Direction::South,
        Direction::South => Direction::Southwest,
        Direction::Southwest => Direction::West,
        Direction::West => Direction::Northwest,
        Direction::Northwest => Direction::North,
        Direction::Centre => Direction::Centre,
    }
}

/// `(dx, dy)` offsets for `DIR8`, in the same order.
pub const DIR8_DELTA: [(i32, i32); 8] = [
    (0, -1),  // North
    (1, -1),  // Northeast
    (1, 0),   // East
    (1, 1),   // Southeast
    (0, 1),   // South
    (-1, 1),  // Southwest
    (-1, 0),  // West
    (-1, -1), // Northwest
];

/// `(dx, dy)` offsets for `DIR4` (cardinals only), in the same order.
pub const DIR4_DELTA: [(i32, i32); 4] = [
    (0, -1), // North
    (1, 0),  // East
    (0, 1),  // South
    (-1, 0), // West
];

/// Convert a magnitude-1 or sqrt-2 vector to its `Direction`. Returns `None`
/// for any other delta (including `(0, 0)` and longer vectors).
#[must_use]
pub const fn delta_to_dir(dx: i32, dy: i32) -> Option<Direction> {
    match (dx, dy) {
        (0, -1) => Some(Direction::North),
        (1, -1) => Some(Direction::Northeast),
        (1, 0) => Some(Direction::East),
        (1, 1) => Some(Direction::Southeast),
        (0, 1) => Some(Direction::South),
        (-1, 1) => Some(Direction::Southwest),
        (-1, 0) => Some(Direction::West),
        (-1, -1) => Some(Direction::Northwest),
        _ => None,
    }
}

/// Direction from `from_pos` to `to_pos`, or `None` if not adjacent in king-move.
#[must_use]
pub const fn get_direction_object(from_pos: Position, to_pos: Position) -> Option<Direction> {
    delta_to_dir(to_pos.x - from_pos.x, to_pos.y - from_pos.y)
}
