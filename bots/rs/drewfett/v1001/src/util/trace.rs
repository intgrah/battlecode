//! TLE diagnosis: section ENTER/EXIT prints with immediate flush.
//!
//! Why not `Scope::new_timed`? `Scope` aggregates per-turn samples and
//! flushes every 64 turns. A TLE interrupts mid-execution and the
//! aggregated samples are lost. We need each enter/exit to hit stdout
//! before the next instruction so the replay binary captures the last
//! successful checkpoint pair. Any unmatched ENTER in
//! `strings <replay> | grep PROF_` is the section that TLE'd.
//!
//! Why stdout not stderr? cambc captures both into the replay binary
//! as plaintext strings. Stdout is what `match replay` emits.
//!
//! `time.perf_counter_ns()` returns 0 on the actual ladder server
//! (engine freezes wall clock for TLE determinism), so we use
//! `ct.get_cpu_time_elapsed()` — engine-provided, real microseconds.
//!
//! Gated on the `TRACE_TLE` build flag (set `TRACE_TLE=1` env var).
//! Sampled by `uid % TRACE_SAMPLE`: with 50-unit cap and SAMPLE=8, ~6
//! bots emit traces. Adjust SAMPLE to trade volume for coverage.

use cambc::{Controller, ControllerApi};

#[cfg(pyrust_translate)]
use cambc::Position;

use crate::config::TRACE_TLE;

/// One trace per `TRACE_SAMPLE` bots (by uid). 1 = trace all bots,
/// 8 = ~12% sample rate.
pub const TRACE_SAMPLE: i32 = 8;

#[cfg(not(pyrust_translate))]
fn emit(_kind: &str, _ct: &Controller<'_>, _name: &str) {}

#[cfg(pyrust_translate)]
fn emit(kind: &str, ct: &Controller<'_>, name: &str) {
    let uid = pyrust::unwrap_or!(ct.get_id(), -1);
    if uid % TRACE_SAMPLE != 0 {
        return;
    }
    let cpu = pyrust::unwrap_or!(ct.get_cpu_time_elapsed(), 0);
    let turn = pyrust::unwrap_or!(ct.get_current_round(), -1);
    Position::_prof_emit(uid, turn, kind, name, cpu);
}

/// Print `PROF_E uid=N t=T sec=NAME cpu=Cus` and flush.
/// Call at the top of any section we want to diagnose.
#[inline]
pub fn enter(ct: &Controller<'_>, name: &str) {
    if !TRACE_TLE {
        return;
    }
    emit("E", ct, name);
}

/// Print `PROF_X uid=N t=T sec=NAME cpu=Cus` and flush.
/// Pair with `enter` at section exit. An ENTER in the replay stdout
/// with no matching EXIT before the next ENTER on the same uid means
/// the section was TLE-interrupted.
#[inline]
pub fn exit(ct: &Controller<'_>, name: &str) {
    if !TRACE_TLE {
        return;
    }
    emit("X", ct, name);
}
