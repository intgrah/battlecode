//! Translation of `bots/intgrah/v54.7.9/util/symmetry.py`.

use cambc::Position;

/// All maps exhibit one of these symmetries.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Symmetry {
    /// 180° rotation about the map centre. Point reflection.
    Rot = 0,
    /// Reflection across the horizontal axis. x unchanged, y flipped.
    Hor = 1,
    /// Reflection across the vertical axis. x flipped, y unchanged.
    Ver = 2,
}

/// All three symmetries, in priority order (matches Python's
/// `Symmetry` enum iteration order).
pub const ALL: [Symmetry; 3] = [Symmetry::Rot, Symmetry::Hor, Symmetry::Ver];

impl Symmetry {
    /// Apply this symmetry to `pos` on a map with the given dimensions.
    #[must_use]
    pub const fn action(self, pos: Position, w: i32, h: i32) -> Position {
        match self {
            Symmetry::Rot => Position {
                x: w - 1 - pos.x,
                y: h - 1 - pos.y,
            },
            Symmetry::Hor => Position {
                x: pos.x,
                y: h - 1 - pos.y,
            },
            Symmetry::Ver => Position {
                x: w - 1 - pos.x,
                y: pos.y,
            },
        }
    }
}

impl core::fmt::Display for Symmetry {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str(match self {
            Symmetry::Rot => "ROT",
            Symmetry::Hor => "HOR",
            Symmetry::Ver => "VER",
        })
    }
}
