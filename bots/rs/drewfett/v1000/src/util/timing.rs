//! Cross-target wall-clock helper: native uses SystemTime, translated
//! Python uses `time.perf_counter_ns`.

#[cfg(not(pyrust_translate))]
pub fn perf_counter_ns() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0)
}

#[cfg(pyrust_translate)]
pub fn perf_counter_ns() -> u64 {
    pyrust::time::now_ns!()
}
