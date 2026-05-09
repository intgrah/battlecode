//! Pure game engine for Cambridge Battlecode.
//!
//! No Python, no protobuf, no I/O. Provides:
//! - `common::game_constants` — all balance values (HP, costs, scaling, …).
//! - `common::{Direction, EntityType, ResourceType, Team, Environment, Pos}`
//! - `game_map` — `Entity`, `GameMap`, `Tile`, `PlayerState`, building/turret structs.
//! - `game` — `Game` struct + the per-action build/distribute/turret/heal/damage
//!   methods, the cooldown loop, and win-condition detection.
//! - `map_loader` — `.map26` protobuf parsing into a starting environment.
//! - `replay_diff` — `GameDiff` event enum and `ReplayRecorder` (memory-only
//!   storage). Serialization to protobuf lives in the `cambc-libre-replay` crate.
//!
//! This crate is pure: no IPC, no Python, no `clock_gettime`, no async
//! exception injection. Suitable for direct use from native Rust bots,
//! fuzzers, replay-driven tests, etc.

pub mod common;
pub mod controller;
pub mod game;
pub mod game_map;
pub mod replay_diff;

/// `IntoPyObject`/`FromPyObject` impls for the engine's enums + Pos.
/// Behind a feature so the pure engine has zero pyo3 dep when unused
/// (e.g. for native Rust bots, fuzzers, replay-driven tests).
#[cfg(feature = "pyo3")]
pub mod pyo3_impls;
