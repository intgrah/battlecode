//! WS-6: per-turn CPU budget helpers.
//!
//! The cambc engine grants 2ms (2000μs) per unit per round, with a 5%
//! rolling buffer. Long-running tasks (extend_chain, parasitic, scout)
//! can blow the budget on pathological inputs; this module provides a
//! single yield checkpoint they can poll cheaply, plus a place to drop
//! per-turn telemetry.
//!
//! Telemetry is gated on `BUDGET_DEBUG`. When enabled, p50/p95 of the
//! per-turn elapsed cap-readings are emitted via `eprintln!` periodically.
//! Reads `ct.get_cpu_time_elapsed()` directly — on platforms where that
//! returns 0 (cambc-libre on Mac) telemetry will be all-zeros, but the
//! production server is Linux and reports real CPU time.

use cambc::{Controller, ControllerApi};
#[cfg(pyrust_translate)]
use pyrust::sys;

/// Microsecond budget — abort long-running tasks when elapsed exceeds this.
///
/// Sized below the 2000μs hard cap to leave headroom for end-of-turn hooks
/// (heal pass, indicators, marker propagation, debug flush).
pub const YIELD_BUDGET_US: u64 = 1500;

/// Compile-time toggle for budget telemetry (`eprintln!` p50/p95 stats).
/// Set `BUDGET_DEBUG=1` env var at build time (Rust) or at runtime (Python
/// via translated `os.environ` lookup).
const BUDGET_DEBUG: bool = pyrust::is_some!(option_env!("BUDGET_DEBUG"));

/// Returns true iff the bot has consumed more than `YIELD_BUDGET_US` of
/// CPU time this turn. Long-running tasks should poll this between
/// independent work units (one path probe, one chain extension step,
/// one scout target evaluation) and break out early on `true`.
#[must_use]
pub fn should_yield(ct: &Controller<'_>) -> bool {
    pyrust::unwrap_or!(ct.get_cpu_time_elapsed(), 0) > YIELD_BUDGET_US
}

/// Like `should_yield`, but with a caller-supplied threshold (μs).
#[must_use]
pub fn should_yield_at(ct: &Controller<'_>, budget_us: u64) -> bool {
    pyrust::unwrap_or!(ct.get_cpu_time_elapsed(), 0) > budget_us
}

/// Per-turn budget telemetry, kept on the heap as a rolling window.
pub struct BudgetTelemetry {
    samples: Vec<u64>,
    cap: usize,
}

impl Default for BudgetTelemetry {
    fn default() -> Self {
        Self::new()
    }
}

impl BudgetTelemetry {
    #[must_use]
    pub fn new() -> Self {
        Self {
            samples: pyrust::vec::new!(),
            cap: 64,
        }
    }

    /// No-op now; kept so call sites in `builder::run` don't need rewriting.
    pub fn start_turn(&mut self) {}

    /// Record this turn's final elapsed-μs reading. Emits a summary line
    /// every `cap` turns when `BUDGET_DEBUG` is enabled.
    pub fn record(&mut self, ct: &Controller<'_>) {
        if !BUDGET_DEBUG {
            return;
        }
        let us = pyrust::unwrap_or!(ct.get_cpu_time_elapsed(), 0);
        pyrust::vec::push!(self.samples, us);
        if pyrust::len!(self.samples) >= self.cap {
            self.flush();
        }
    }

    fn flush(&mut self) {
        if pyrust::vec::is_empty!(self.samples) {
            return;
        }
        let mut sorted = pyrust::clone!(self.samples);
        sorted.sort();
        let n = pyrust::len!(sorted);
        let p50 = sorted[n / 2];
        let p95 = sorted[pyrust::min!((n * 95 / 100), n - 1)];
        let max = sorted[n - 1];
        eprintln!(
            "[budget] window n={n} p50={p50}us p95={p95}us max={max}us yield_cap={}us",
            YIELD_BUDGET_US
        );
        self.samples.clear();
    }
}
