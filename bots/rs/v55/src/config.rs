//! Translation of `bots/intgrah/v54.7.9/config.py`.
//!
//! Debug flags. Python reads these from environment variables; Rust reads them
//! once via `option_env!` at compile time so they're zero-overhead in release
//! builds. Set `DEBUG_DUMP=1`, `DEBUG_LOG=1`, etc. as build-time env vars.

/// Resign upon error.
pub const DEBUG_RESIGN: bool = pyrust::is_some!(option_env!("DEBUG_RESIGN"));

/// Dump using rich debugging. This slows down the bot a lot.
pub const DEBUG_DUMP: bool = pyrust::is_some!(option_env!("DEBUG_DUMP"));

/// `DEBUG_DUMP` implies `DEBUG_LOG`: the dump pipeline rides the per-turn
/// tree machinery, so dumping with logging off would emit nothing.
pub const DEBUG_LOG: bool = pyrust::is_some!(option_env!("DEBUG_LOG")) || DEBUG_DUMP;

/// Use hardcoding.
pub const HARDCODE: bool = false;

/// Run oracle recomputations for incrementally-maintained sets
/// (`ti_upstream` / `ax_upstream` / `dangling_set` / counters) and assert
/// equality each turn. Slow — for debugging incremental maintenance only.
pub const DEBUG_INVARIANTS: bool = pyrust::is_some!(option_env!("DEBUG_INVARIANTS"));
