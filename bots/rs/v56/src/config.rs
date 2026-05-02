//! Debug flags. Set as build-time env vars (`DEBUG_LOG=1 cargo build`, etc.).
//! `build.rs` translates the env vars into `--cfg debug_log` / `--cfg debug_dump`
//! / etc. so call sites can use `#[cfg(...)]` for AST-level elimination, and
//! the const bools below mirror those for value-level `if` gates.

/// Resign upon error.
pub const DEBUG_RESIGN: bool = cfg!(debug_resign);

/// Dump using rich debugging. This slows down the bot a lot.
pub const DEBUG_DUMP: bool = cfg!(debug_dump);

/// `DEBUG_DUMP` implies `DEBUG_LOG`: the dump pipeline rides the per-turn
/// tree machinery, so dumping with logging off would emit nothing. (build.rs
/// already enforces this implication when emitting `--cfg debug_log`.)
pub const DEBUG_LOG: bool = cfg!(debug_log);

#[pyrust::inline]
/// Use hardcoding.
pub const HARDCODE: bool = false;

/// Run oracle recomputations for incrementally-maintained sets
/// (`ti_upstream` / `ax_upstream` / `dangling_set` / counters) and assert
/// equality each turn. Slow — for debugging incremental maintenance only.
pub const DEBUG_INVARIANTS: bool = pyrust::is_some!(option_env!("DEBUG_INVARIANTS"));
