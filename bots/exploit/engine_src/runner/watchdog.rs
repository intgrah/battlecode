//! Pure-Rust watchdog for TLE enforcement.
//!
//! Runs on a dedicated OS thread pinned to core 0 (separate from the engine on
//! core 1). Uses direct atomic writes to CPython's `tstate->async_exc` and
//! `interp->ceval.eval_breaker` to inject SystemExit — no GIL acquisition needed.
//!
//! After the wall-clock timeout, the watchdog checks the main thread's CPU time.
//! If CPU budget remains (e.g. kernel preempted the bot), it resleeps via busy-wait
//! until CPU is exhausted or a hard wall cap (2x) is reached. This is fair: bots
//! aren't penalised for scheduler jitter. The CPU check is a direct syscall
//! (`clock_gettime` on the main thread's CPU clock) — no GIL needed.

use std::sync::{Arc, Condvar, Mutex};
use std::time::{Duration, Instant};
#[cfg(feature = "tle")]
use std::sync::atomic::{AtomicU64, Ordering};

/// Offsets into CPython structs, computed at build time by build.rs.
/// Verified at runtime against the known `thread_id` field.
#[cfg(feature = "tle")]
mod offsets {
    include!(concat!(env!("OUT_DIR"), "/cpython_offsets.rs"));
}

/// Hard wall-clock multiplier. Even if CPU budget remains, fire after this
/// multiple of the wall timeout. Limits thread-based TLE bypass where bots
/// spawn worker threads that steal GIL time from the main thread.
const HARD_WALL_MULTIPLIER: f64 = 2.0;

pub struct Watchdog {
    inner: Arc<Inner>,
    handle: Option<std::thread::JoinHandle<()>>,
}

struct Inner {
    mu: Mutex<State>,
    cv: Condvar,
}

struct State {
    /// Wall-clock deadline. None = disarmed.
    deadline: Option<Instant>,
    /// Hard wall-clock cap (HARD_WALL_MULTIPLIER × wall_timeout past arm time).
    hard_deadline: Option<Instant>,
    shutdown: bool,
    /// Raw pointer to the subinterpreter's PyThreadState for this unit.
    tstate: *mut u8,
    /// PyExc_SystemExit pointer (immortal object, no refcount needed).
    system_exit: *mut u8,
}

// Safety: tstate and system_exit are only written during init (single-threaded)
// and read from the watchdog thread. The pointers themselves are stable for the
// lifetime of the subinterpreter.
unsafe impl Send for State {}

impl Watchdog {
    /// Create a new Rust watchdog for the given subinterpreter thread state.
    ///
    /// `tstate` must be a valid `PyThreadState*` for the unit's subinterpreter.
    /// The caller must have the GIL (for reading PyExc_SystemExit).
    ///
    /// The watchdog thread is pinned to core 0 to avoid competing with the
    /// engine on core 1.
    #[cfg(feature = "tle")]
    pub fn new(tstate: *mut pyo3_ffi::PyThreadState) -> Self {
        // Verify offsets by checking that thread_id at the computed offset
        // matches pthread_self() (which is what CPython stores there).
        let current_pthread = unsafe { libc::pthread_self() } as std::ffi::c_ulong;
        let tid_at_offset = unsafe {
            *((tstate as *const u8).add(offsets::THREAD_ID_OFFSET) as *const std::ffi::c_ulong)
        };
        assert_eq!(
            current_pthread, tid_at_offset,
            "CPython struct offset mismatch: thread_id at offset {} is {tid_at_offset:#x}, \
             expected pthread_self={current_pthread:#x}. Build-time offsets wrong for this Python.",
            offsets::THREAD_ID_OFFSET,
        );

        let system_exit = unsafe { pyo3_ffi::PyExc_SystemExit as *mut u8 };

        let inner = Arc::new(Inner {
            mu: Mutex::new(State {
                deadline: None,
                hard_deadline: None,
                shutdown: false,
                tstate: tstate as *mut u8,
                system_exit,
            }),
            cv: Condvar::new(),
        });

        let inner2 = inner.clone();
        let handle = std::thread::Builder::new()
            .name("tle-watchdog".into())
            .spawn(move || watchdog_thread(inner2))
            .expect("spawn watchdog thread");

        Watchdog {
            inner,
            handle: Some(handle),
        }
    }

    #[cfg(not(feature = "tle"))]
    pub fn new(_tstate: *mut pyo3_ffi::PyThreadState) -> Self {
        Watchdog {
            inner: Arc::new(Inner {
                mu: Mutex::new(State {
                    deadline: None,
                    hard_deadline: None,
                    shutdown: false,
                    tstate: std::ptr::null_mut(),
                    system_exit: std::ptr::null_mut(),
                }),
                cv: Condvar::new(),
            }),
            handle: None,
        }
    }

    /// Arm the watchdog with a wall-clock timeout in seconds.
    pub fn arm(&self, wall_timeout_secs: f64) {
        let now = Instant::now();
        let deadline = now + Duration::from_secs_f64(wall_timeout_secs);
        let hard_deadline = now + Duration::from_secs_f64(wall_timeout_secs * HARD_WALL_MULTIPLIER);
        let mut state = self.inner.mu.lock().unwrap();
        state.deadline = Some(deadline);
        state.hard_deadline = Some(hard_deadline);
        self.inner.cv.notify_one();
    }

    /// Disarm the watchdog (bot finished its turn within budget).
    pub fn disarm(&self) {
        let mut state = self.inner.mu.lock().unwrap();
        state.deadline = None;
        state.hard_deadline = None;
        self.inner.cv.notify_one();
    }

    /// Clear any pending async exception on the target thread state.
    /// Does a direct memory write — no GIL needed.
    #[cfg(feature = "tle")]
    pub fn clear_async_exc(&self) {
        let state = self.inner.mu.lock().unwrap();
        if !state.tstate.is_null() {
            unsafe {
                let async_exc_ptr =
                    state.tstate.add(offsets::ASYNC_EXC_OFFSET) as *mut *mut u8;
                std::ptr::write_volatile(async_exc_ptr, std::ptr::null_mut());
            }
        }
    }

    #[cfg(not(feature = "tle"))]
    pub fn clear_async_exc(&self) {}

    /// Shut down the watchdog thread and wait for it to exit.
    pub fn shutdown(&mut self) {
        {
            let mut state = self.inner.mu.lock().unwrap();
            state.shutdown = true;
            self.inner.cv.notify_one();
        }
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

#[cfg(feature = "tle")]
static FIRE_COUNT: AtomicU64 = AtomicU64::new(0);

#[cfg(feature = "tle")]
fn watchdog_thread(inner: Arc<Inner>) {
    // Pin to core 0 so we don't compete with the engine on core 1.
    #[cfg(target_os = "linux")]
    unsafe {
        let mut cpuset: libc::cpu_set_t = std::mem::zeroed();
        libc::CPU_SET(0, &mut cpuset);
        let ret = libc::sched_setaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), &cpuset);
        if ret != 0 {
            eprintln!(
                "[watchdog] sched_setaffinity to core 0 failed: {}",
                std::io::Error::last_os_error()
            );
        }
    }

    let mut guard = inner.mu.lock().unwrap();
    loop {
        // Wait for arm or shutdown.
        while guard.deadline.is_none() && !guard.shutdown {
            guard = inner.cv.wait(guard).unwrap();
        }
        if guard.shutdown {
            return;
        }

        let deadline = guard.deadline.unwrap();
        let hard_deadline = guard.hard_deadline.unwrap_or(deadline);

        // Phase 1: Wait until wall-clock deadline, checking for disarm.
        // For short timeouts (< 20ms, i.e. typical game turns), pure busy-wait
        // on core 0. Condvar sleeps round up to 10ms on CONFIG_HZ=100 kernels,
        // which would overshoot a 5ms deadline. For longer timeouts, use condvar
        // to avoid burning CPU for hundreds of ms.
        let use_busywait = deadline.saturating_duration_since(Instant::now()) < Duration::from_millis(20);
        if use_busywait {
            // Drop mutex during spin so disarm() isn't blocked.
            drop(guard);
            while Instant::now() < deadline {
                std::hint::spin_loop();
            }
            guard = inner.mu.lock().unwrap();
        } else {
            guard = wait_until(guard, &inner, deadline);
        }

        // Check if disarmed or shutdown while waiting.
        if guard.shutdown {
            return;
        }
        if guard.deadline != Some(deadline) {
            continue; // disarmed
        }

        // Phase 2: CPU resleep. If the main thread hasn't exhausted its CPU
        // budget (e.g. kernel preempted it), busy-wait until CPU is used up
        // or the hard wall cap is reached. This is a pure syscall
        // (clock_gettime on the main thread's clock) — no GIL needed.
        let cpu_deadline = crate::runner::CPU_DEADLINE_NS.load(Ordering::Relaxed);
        loop {
            let cpu_now = crate::runner::main_thread_cpu_time_ns();
            if cpu_now >= cpu_deadline {
                break; // CPU budget exhausted
            }
            if Instant::now() >= hard_deadline {
                break; // Hard wall cap
            }
            // Busy-wait — we're on core 0, not blocking the bot
            std::hint::spin_loop();
        }

        // Check if disarmed during CPU resleep (disarm sets deadline to None).
        if guard.deadline != Some(deadline) {
            continue;
        }
        guard.deadline = None;
        guard.hard_deadline = None;

        // FIRE — direct memory writes, no GIL needed.
        fire(&guard);
    }
}

#[cfg(feature = "tle")]
fn wait_until<'a>(
    mut guard: std::sync::MutexGuard<'a, State>,
    inner: &'a Inner,
    target: Instant,
) -> std::sync::MutexGuard<'a, State> {
    loop {
        let now = Instant::now();
        if now >= target {
            return guard;
        }
        let remaining = target - now;
        if remaining > Duration::from_millis(1) {
            let sleep_for = remaining - Duration::from_millis(1);
            let (g, _) = inner.cv.wait_timeout(guard, sleep_for).unwrap();
            guard = g;
            if guard.shutdown || guard.deadline.is_none() {
                return guard;
            }
        } else {
            // Final <1ms: busy-wait for precision.
            drop(guard);
            while Instant::now() < target {
                std::hint::spin_loop();
            }
            return inner.mu.lock().unwrap();
        }
    }
}

/// Inject SystemExit into the target thread state via direct memory writes.
#[cfg(feature = "tle")]
fn fire(state: &State) {
    let count = FIRE_COUNT.fetch_add(1, Ordering::Relaxed) + 1;
    if count <= 20 || count % 500 == 0 {
        eprintln!("[watchdog #{count}] fired");
    }

    unsafe {
        // 1. Set tstate->async_exc = PyExc_SystemExit
        //    SystemExit is immortal in CPython 3.12 — no Py_INCREF needed.
        let async_exc_ptr = state.tstate.add(offsets::ASYNC_EXC_OFFSET) as *mut *mut u8;
        let async_exc_atomic = &*(async_exc_ptr as *const std::sync::atomic::AtomicPtr<u8>);
        async_exc_atomic.store(state.system_exit, Ordering::Release);

        // 2. Set interp->ceval.eval_breaker to non-zero.
        let interp = *(state.tstate.add(offsets::INTERP_OFFSET) as *const *mut u8);
        let eval_breaker_ptr = interp.add(offsets::EVAL_BREAKER_OFFSET) as *const std::sync::atomic::AtomicI32;
        (*eval_breaker_ptr).store(1, Ordering::Release);
    }
}

#[cfg(not(feature = "tle"))]
fn fire(_state: &State) {}
