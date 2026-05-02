//! Integer-encoded tile positions and precomputed distance tables.
//!
//! Each tile (x, y) maps to a single `PosInt` (i32):
//! ```text
//!   idx = y * STRIDE + x
//! ```
//!
//! `STRIDE = 100`, NOT `MAX_WIDTH (50)`. The 2× stride matters: with
//! stride=50 and `|dx| ≤ 49`, two distinct (dy, dx) pairs can collide on
//! `dy * stride + dx` (e.g. `dy=1, dx=-49 → 1` and `dy=0, dx=1 → 1`),
//! which would break a `dist[p - q + OFFSET]` lookup. With stride=100,
//! `|dx| < stride/2` so the encoding is invertible.
//!
//! The trade-off: per-tile arrays sized to `BOUND_RANGE = STRIDE * 50 = 5000`
//! have unused "holes" at `x ∈ [50, 100)` — half the slots are wasted.
//! Trivial relative to the cost of `Position(x, y)` allocation per call.
//!
//! Sprint4ax (`bots/adgato/sprint4ax`) is the pure-Python prototype that
//! seeded this design; v1000 takes the idea further by pushing PosInt
//! through more of the cascade than sprint4ax did.

use cambc::Position;

pub type PosInt = i32;

/// `i32` view of `constants::STRIDE` for signed arithmetic
/// (`pos += DIR4_INT[i]`, `dy * STRIDE + dx`). Use `constants::STRIDE`
/// for usize indexing. Inlined into call sites by pyrust so callers
/// don't need to import STRIDE just because idx_of/pos_of use it.
#[pyrust::inline]
pub const STRIDE: i32 = 100;

pub use crate::util::constants::BOUND_RANGE;

/// `(MAX_WIDTH - 1) * STRIDE + (MAX_WIDTH - 1) = 49 * 100 + 49 = 4949`.
/// `dist_size = 2 * MAX_DELTA + 1 = 9899`.
pub const MAX_DELTA: i32 = 4949;
#[pyrust::inline]
pub const DIST_OFFSET: i32 = 4949;
pub const DIST_TABLE_LEN: usize = 9899;

/// PosInt deltas for `DIR4` (N, E, S, W). Order matches `util::directions::DIR4`.
pub const DIR4_INT: [i32; 4] = [-100, 1, 100, -1];

/// PosInt deltas for `DIR8` (N, NE, E, SE, S, SW, W, NW). Order matches
/// `util::directions::DIR8`.
pub const DIR8_INT: [i32; 8] = [-100, -99, 1, 101, 100, 99, -1, -101];

/// `Position` → `PosInt`. Inlined so callers pay no function-call overhead.
#[pyrust::inline]
#[must_use]
#[inline]
pub fn idx_of(pos: Position) -> PosInt {
    pos.y * STRIDE + pos.x
}

/// `PosInt` → `Position`. Use only at engine boundaries.
///
/// Native: plain arithmetic, inlined.
/// Translated Python: `Position.lookup` is bound by the cambc alias prelude
/// to a precomputed 5000-entry table's `__getitem__`. A lookup is ~5× faster
/// than constructing a fresh `Position(x=, y=)` per call — adgato's "wrap
/// the controller methods" idea applied at the conversion boundary.
#[cfg(not(pyrust_translate))]
#[must_use]
#[inline]
pub fn pos_of(idx: PosInt) -> Position {
    Position {
        x: idx % STRIDE,
        y: idx / STRIDE,
    }
}

#[pyrust::inline]
#[cfg(pyrust_translate)]
pub fn pos_of(idx: PosInt) -> Position {
    Position::lookup(idx)
}

/// Squared euclidean distance between two PosInts.
///
/// Native: inline arithmetic (LLVM elides decode + multiply costs).
/// Translated Python: `Position.dist_sq_table` is bound by the cambc alias
/// prelude to a precomputed 9899-entry tuple's `__getitem__`. The table is
/// built once per subinterpreter at module-import (no per-Builder allocation).
#[cfg(not(pyrust_translate))]
#[must_use]
#[inline]
pub fn dist_sq(p: PosInt, q: PosInt) -> i32 {
    let dy = (p / STRIDE) - (q / STRIDE);
    let dx = (p % STRIDE) - (q % STRIDE);
    dx * dx + dy * dy
}

#[pyrust::inline]
#[cfg(pyrust_translate)]
pub fn dist_sq(p: PosInt, q: PosInt) -> i32 {
    Position::dist_sq_table(p - q + DIST_OFFSET)
}

/// Manhattan (L1) distance between two PosInts. Same setup as `dist_sq`.
#[cfg(not(pyrust_translate))]
#[must_use]
#[inline]
pub fn manhat(p: PosInt, q: PosInt) -> i32 {
    let dy = (p / STRIDE) - (q / STRIDE);
    let dx = (p % STRIDE) - (q % STRIDE);
    dx.abs() + dy.abs()
}

#[pyrust::inline]
#[cfg(pyrust_translate)]
pub fn manhat(p: PosInt, q: PosInt) -> i32 {
    Position::manhat_table(p - q + DIST_OFFSET)
}

/// Chebyshev (L∞) distance between two PosInts. Same setup as `dist_sq`.
#[cfg(not(pyrust_translate))]
#[must_use]
#[inline]
pub fn cheb(p: PosInt, q: PosInt) -> i32 {
    let dy = ((p / STRIDE) - (q / STRIDE)).abs();
    let dx = ((p % STRIDE) - (q % STRIDE)).abs();
    if dx > dy { dx } else { dy }
}

#[pyrust::inline]
#[cfg(pyrust_translate)]
pub fn cheb(p: PosInt, q: PosInt) -> i32 {
    Position::chebyshev_table(p - q + DIST_OFFSET)
}
