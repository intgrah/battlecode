//! Stub for `bots/intgrah/v54.7.9/hardcode/identify.py`.
//!
//! Phase E will replace this with the real identifier. For now, callers
//! gate on `HARDCODE` and never reach these — they panic if invoked.

use cambc::{Controller, Position};

/// Placeholder for `find_core(ct, pos)`. Real impl returns the centre of a
/// known core in vision; the stub is unreachable when `HARDCODE` is false.
#[must_use]
pub fn find_core(_ct: &Controller<'_>, _hint: Position) -> Position {
    unimplemented!("hardcode::identify::find_core stub — Phase E")
}

#[pyrust::inline]
/// Placeholder for `identify_map(w, h, my_core)`. Real impl returns a
/// `KnownMap` describing the precomputed level. Returns `None` because
/// the v55 default is `HARDCODE=false`.
#[must_use]
pub const fn identify_map(_w: i32, _h: i32, _my_core: Position) -> Option<KnownMap> {
    None
}

/// Opaque placeholder for the hardcoded-map type. Phase E will define the
/// real shape (level id, symmetry, tile encoding).
#[derive(Clone, Copy, Debug)]
pub struct KnownMap;
