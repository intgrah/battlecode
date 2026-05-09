//! Protobuf replay (de)serialization and `.map26` loader for `cambc-libre-engine`.
//!
//! Bridges the pure engine's `GameDiff`/`ReplayRecorder` to the on-disk
//! `cambc.proto` schema. Use:
//! - `load_map(path)` — parse a `.map26` into the (env, cores) tuple
//!   accepted by `cambc_libre_engine::game::Game::new`.
//! - `save_map(path, env, cores)` — round-trip a map back out.
//! - `write_replay(recorder, path, winner)` — serialize a finished
//!   recorder to a `.replay26` protobuf file.

pub mod conversions;
pub mod map_loader;
mod writer;

pub use map_loader::{load_map, save_map};
pub use writer::write_replay;
