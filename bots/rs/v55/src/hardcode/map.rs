//! Stub for `bots/intgrah/v54.7.9/hardcode/map.py`.
//!
//! Phase E will replace this with the precomputed lookup table. For now,
//! callers gate on `HARDCODE` and never reach these.

use crate::util::symmetry::Symmetry;

/// Placeholder for the hardcoded `SYMMETRY` table.
pub const SYMMETRY: Option<Symmetry> = None;

/// Placeholder for the hardcoded `TILES` blob — empty until Phase E lands.
pub const TILES: &[u8] = &[];

/// Placeholder for `decode(buf, w, h)`. Real impl returns a dense per-tile
/// array; stub is unreachable when `HARDCODE` is false.
#[must_use]
pub fn decode(_buf: &[u8], _w: i32, _h: i32) -> Vec<u8> {
    unimplemented!("hardcode::map::decode stub — Phase E")
}
