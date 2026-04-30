//! Internal modules for the `cambc-libre` binary.
//!
//! This is everything that depends on PyO3: the subinterpreter manager,
//! the watchdog, the PyO3 `Controller` class, the `cambc` shim installer,
//! the clap CLI, and the binary's `main`. The pure game logic lives in
//! `libre-engine`; protobuf I/O lives in `libre-replay`.

pub mod bindings;
pub mod cli;
pub mod runner;
pub mod rust_backend;
