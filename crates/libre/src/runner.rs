mod watchdog;

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::Path;
use std::rc::Rc;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};
use pyo3_ffi::{
    Py_EndInterpreter, Py_NewInterpreterFromConfig, PyInterpreterConfig,
    PyInterpreterConfig_SHARED_GIL, PyThreadState, PyThreadState_Swap,
};

use crate::bindings as rustlib;
use crate::bindings::controller::Controller;
use crate::bindings::py_convert;
use crate::cli::{Args, BotKind};
use crate::rust_backend::RustBackend;
use libre_engine::common::Team;
use libre_engine::common::game_constants::MAX_TURNS;
use libre_engine::controller::UnitView;
use libre_engine::game::Game;
use libre_engine::game_map::Entity;
use libre_engine::replay_diff::GameDiff;
use libre_replay::map_loader;

/// Per-team execution backend. Python bots run in their own subinterpreter
/// (existing path); Rust bots are loaded as cdylibs and called directly
/// via FFI with no Python involvement.
enum TeamBackend {
    Python { bot_path: String },
    Rust(RustBackend),
}

impl TeamBackend {
    const fn python_path(&self) -> Option<&str> {
        match self {
            Self::Python { bot_path } => Some(bot_path.as_str()),
            Self::Rust(_) => None,
        }
    }
}

/// Returns the calling thread's cumulative CPU time in nanoseconds.
///
/// Uses `CLOCK_THREAD_CPUTIME_ID` (per-thread, not process-wide).
/// Used by `Controller::check_deadline()` for cooperative TLE enforcement.
/// Returns 0 when the `tle` feature is disabled.
#[cfg(feature = "tle")]
#[must_use]
pub fn thread_cpu_time_ns() -> u64 {
    cpu_time_ns_for_clock(libc::CLOCK_THREAD_CPUTIME_ID)
}

#[cfg(not(feature = "tle"))]
pub fn thread_cpu_time_ns() -> u64 {
    0
}

#[cfg(feature = "tle")]
fn cpu_time_ns_for_clock(clock_id: libc::clockid_t) -> u64 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    unsafe {
        libc::clock_gettime(clock_id, &raw mut ts);
    }
    ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64
}

/// CPU clock ID for the main thread. Captured at startup via
/// `pthread_getcpuclockid` so the watchdog on core 0 can read the main
/// thread's CPU time without the GIL.
#[cfg(feature = "tle")]
static MAIN_THREAD_CLOCK_ID: std::sync::atomic::AtomicI32 = std::sync::atomic::AtomicI32::new(0);

#[cfg(feature = "tle")]
fn init_main_thread_clock_id() {
    let mut clock_id: libc::clockid_t = 0;
    unsafe {
        libc::pthread_getcpuclockid(libc::pthread_self(), &raw mut clock_id);
    }
    MAIN_THREAD_CLOCK_ID.store(clock_id, std::sync::atomic::Ordering::Relaxed);
}

#[cfg(not(feature = "tle"))]
fn init_main_thread_clock_id() {}

/// Read the main thread's CPU time from any thread (used by the watchdog).
#[cfg(feature = "tle")]
pub fn main_thread_cpu_time_ns() -> u64 {
    cpu_time_ns_for_clock(MAIN_THREAD_CLOCK_ID.load(std::sync::atomic::Ordering::Relaxed))
}

#[cfg(not(feature = "tle"))]
pub fn main_thread_cpu_time_ns() -> u64 {
    0
}

/// CPU start time (absolute ns) for the current unit turn.
/// Written by `perform_unit_actions`, read by `Controller::get_cpu_time_elapsed`.
pub(crate) static CPU_START_NS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
/// CPU deadline (absolute ns, in per-thread CPU time) for the current unit turn.
/// Written by `perform_unit_actions`, read by `Controller::check_deadline`.
pub(crate) static CPU_DEADLINE_NS: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);

/// Percent of the per-turn time limit that can be banked as extra time.
const ADAPTIVE_TIME_PERCENT: u64 = 5;

struct UnitRunner {
    player: Py<PyAny>,
    tstate: *mut PyThreadState,
    watchdog: watchdog::Watchdog,
}

struct GameRunner {
    game: Rc<RefCell<Game>>,
    /// Per-team execution backend (Python subinterpreter or Rust cdylib).
    team_backends: [TeamBackend; 2],
    /// Engine root path, used when initialising a new subinterpreter's sys.path.
    engine_root: std::path::PathBuf,
    /// The main interpreter's thread state, captured at construction time.
    /// We swap back to this after entering/leaving each unit's subinterpreter.
    main_tstate: *mut PyThreadState,
    /// Per-unit runner: player object + subinterpreter thread state + watchdog.
    unit_runners: HashMap<i32, UnitRunner>,
    /// Per-unit Rust bot pointers (opaque `Box<dyn Player>`) keyed by
    /// unit id, along with the team that owns the backend. Created on
    /// first action by a unit on a Rust team; dropped on unit death.
    rust_unit_bots: HashMap<i32, (Team, *mut std::ffi::c_void)>,
    turn_timeout_ms: u64,
    max_rounds: i32,
    /// Banked extra time per bot (nanoseconds), used to absorb CPU jitter.
    bot_extra_time_ns: HashMap<i32, u64>,
    /// The Rust-backed Controller class, set on each subinterpreter's cambc module.
    controller_cls: Py<PyAny>,
    gc_mod: Py<PyModule>,
}

impl GameRunner {
    fn run(&mut self, py: Python) -> PyResult<()> {
        let gc = self.gc_mod.clone_ref(py).into_bound(py);
        gc.call_method0("disable")?;
        let limit = self.max_rounds.min(MAX_TURNS);
        for i in 0..limit {
            self.run_turn(py, &gc)?;
            if i % 100 == 0 {
                println!("Completed turn {i}");
            }
            if self.game.borrow_mut().winner_team(false).is_some() {
                break;
            }
        }
        gc.call_method0("enable")?;
        Ok(())
    }

    fn run_turn(&mut self, py: Python, gc: &Bound<'_, PyModule>) -> PyResult<()> {
        self.game.borrow_mut().new_turn();

        self.perform_unit_actions(py)?;
        let mut game = self.game.borrow_mut();
        game.distribute_resources();
        game.update_cooldowns();
        // Passive titanium income: +10 Ti to each team every 4 rounds.
        // Granted at the end of round 4, 8, 12, ... (1-indexed). Does
        // NOT increment `titanium_collected` — that stat tracks resources
        // delivered to the core via conveyors, not passive income.
        // Verified against the cambc 1.7.1 binary: `nothing/100` shows
        // 0 mined despite 25 passive grants over 100 rounds.
        if (game.turn + 1) % libre_engine::common::game_constants::PASSIVE_TITANIUM_INTERVAL == 0 {
            for p in &mut game.players {
                p.titanium += libre_engine::common::game_constants::PASSIVE_TITANIUM_AMOUNT;
            }
        }
        let players = game.players.clone();
        game.replay_recorder
            .append(GameDiff::UpdatePlayers { players });
        game.turn += 1;
        drop(game);
        self.cleanup_unit_runners();
        gc.call_method0("collect")?;
        Ok(())
    }

    fn perform_unit_actions(&mut self, py: Python) -> PyResult<()> {
        let cpu_budget_ns = self.turn_timeout_ms * 1_000_000;
        let max_extra_ns = cpu_budget_ns * ADAPTIVE_TIME_PERCENT / 100;
        let units = { self.game.borrow().unit_order.clone() };
        for unit_id in units {
            let game = self.game.borrow();
            let Some(entity) = game.entity(unit_id) else {
                continue;
            };
            let team = entity.team;
            drop(game);
            // Dispatch on the team's backend. Rust units bypass the
            // subinterpreter entirely.
            if matches!(self.team_backends[team.index()], TeamBackend::Rust(_)) {
                self.run_rust_unit(unit_id, team);
                continue;
            }
            self.ensure_unit_runner(py, unit_id, team);
            if !self.unit_runners.contains_key(&unit_id) {
                continue; // init failed, unit was destroyed
            }

            let extra_ns = *self
                .bot_extra_time_ns
                .entry(unit_id)
                .or_insert(max_extra_ns);
            let effective_budget_ns = cpu_budget_ns + extra_ns;
            let wall_timeout = effective_budget_ns as f64 / 1_000_000_000.0 * 1.05;

            // Swap to the unit's subinterpreter for ALL Python operations on
            // subinterpreter-owned objects. Only Rust values cross back.
            let sub_tstate = self.unit_runners[&unit_id].tstate;
            unsafe {
                PyThreadState_Swap(sub_tstate);
            }

            let runner = &self.unit_runners[&unit_id];
            let player = runner.player.clone_ref(py);

            // Clear any pending async exception from a previous turn.
            // Direct memory write (no GIL needed for the clear itself),
            // then absorb any already-raised exception via a Python no-op.
            runner.watchdog.clear_async_exc();
            for _ in 0..100 {
                if let Ok(_) = py.eval(c"None", None, None) {
                    break;
                }
                runner.watchdog.clear_async_exc();
                continue;
            }

            // Create StringIO in the subinterpreter for stdout capture.
            // If subinterpreter is corrupted (bot's __init__ broke imports),
            // treat as a unit error rather than crashing the engine.
            let setup_result: PyResult<(Py<PyAny>, Py<PyAny>)> = (|| {
                let io = PyModule::import(py, "io")?;
                let stdout_buf = io.call_method0("StringIO")?.unbind();
                let sub_sys = PyModule::import(py, "sys")?;
                sub_sys.setattr("stdout", stdout_buf.bind(py))?;
                let controller = Py::new(py, Controller::new(self.game.clone(), unit_id))?;
                Ok((stdout_buf, controller.into_any()))
            })();
            let (stdout_buf, controller) = match setup_result {
                Ok(v) => v,
                Err(err) => {
                    eprintln!("[runner] unit {unit_id} turn setup failed: {err}");
                    unsafe {
                        PyThreadState_Swap(self.main_tstate);
                    }
                    let mut game = self.game.borrow_mut();
                    if game.entity(unit_id).is_some() {
                        game.destroy_entity(unit_id);
                    }
                    continue;
                }
            };

            // Set the deadline as late as possible so setup overhead isn't
            // counted against the bot's CPU budget. With turn_timeout_ms=0,
            // disable enforcement by setting the deadline to u64::MAX (no
            // check_deadline will fire) — `get_cpu_time_elapsed` still
            // returns real per-thread CPU time.
            let cpu_start = thread_cpu_time_ns();
            CPU_START_NS.store(cpu_start, std::sync::atomic::Ordering::Relaxed);
            let deadline = if self.turn_timeout_ms == 0 {
                u64::MAX
            } else {
                cpu_start + effective_budget_ns
            };
            CPU_DEADLINE_NS.store(deadline, std::sync::atomic::Ordering::Relaxed);

            // Arm the Rust watchdog — pure Rust, no GIL needed.
            // Skip arming when timeout is disabled.
            if self.turn_timeout_ms != 0 {
                runner.watchdog.arm(wall_timeout);
            }

            let result = player.call_method1(py, "run", (controller,));
            let cpu_elapsed_ns = thread_cpu_time_ns() - cpu_start;

            // Disarm the watchdog — pure Rust, no GIL needed.
            runner.watchdog.disarm();

            // Clear any async exception injected between player.run() return
            // and disarm, then absorb any already-raised exception.
            runner.watchdog.clear_async_exc();
            for _ in 0..100 {
                if let Ok(_) = py.eval(c"None", None, None) {
                    break;
                }
                runner.watchdog.clear_async_exc();
                continue;
            }

            // Handle errors (still in subinterpreter for err.print)
            let mut destroy_unit = false;

            if let Err(ref err) = result {
                if err.is_instance_of::<pyo3::exceptions::PyKeyboardInterrupt>(py) {
                    unsafe {
                        PyThreadState_Swap(self.main_tstate);
                    }
                    return Err(err.clone_ref(py));
                } else if err.is_instance_of::<pyo3::exceptions::PySystemExit>(py) {
                    // Watchdog or check_deadline fired — skip this unit's turn.
                } else {
                    err.print(py);
                    destroy_unit = true;
                }
            }

            // Extract stdout as Rust String before leaving the subinterpreter
            let stdout: String = stdout_buf
                .call_method0(py, "getvalue")
                .and_then(|s| s.extract(py))
                .unwrap_or_default();

            // Swap back to main interpreter — only Rust values from here
            unsafe {
                PyThreadState_Swap(self.main_tstate);
            }

            if destroy_unit {
                let mut game = self.game.borrow_mut();
                if game.entity(unit_id).is_some() {
                    game.destroy_entity(unit_id);
                }
            }

            self.game
                .borrow_mut()
                .replay_recorder
                .append(GameDiff::BotOutput {
                    id: unit_id,
                    stdout,
                    exec_time_us: (cpu_elapsed_ns / 1000) as u32,
                    tled: cpu_elapsed_ns > effective_budget_ns,
                });

            // Update banked extra time: bank unused time, debit overuse.
            let new_extra = if cpu_elapsed_ns <= cpu_budget_ns + extra_ns {
                (extra_ns + cpu_budget_ns).saturating_sub(cpu_elapsed_ns)
            } else {
                0
            };
            self.bot_extra_time_ns
                .insert(unit_id, new_extra.min(max_extra_ns));
        }
        Ok(())
    }

    /// Run one turn for a unit on a Rust team. No subinterpreter, no
    /// GIL contention — just construct a `UnitView` over the engine
    /// `Game` and hand it to the bot via FFI. Captures the bot's stdout
    /// per turn via fd redirection (mirrors the per-subinterpreter
    /// `StringIO` capture used for Python bots) and emits it on the
    /// replay's `BotOutput` diff.
    fn run_rust_unit(&mut self, unit_id: i32, team: Team) {
        let backend = match &self.team_backends[team.index()] {
            TeamBackend::Rust(b) => b,
            TeamBackend::Python { .. } => unreachable!("dispatched to rust path"),
        };
        let (_, bot_ptr) = *self
            .rust_unit_bots
            .entry(unit_id)
            .or_insert_with(|| (team, backend.create_bot()));
        // Borrow the game mutably for the duration of `run`, then drop
        // the borrow before emitting the BotOutput diff.
        let game_cell = self.game.clone();
        let stdout = crate::stdout_capture::capture(|| {
            let mut game = game_cell.borrow_mut();
            let mut view = UnitView::new(&mut game, unit_id);
            backend.run_bot(bot_ptr, &mut view);
        });
        self.game
            .borrow_mut()
            .replay_recorder
            .append(GameDiff::BotOutput {
                id: unit_id,
                stdout,
                exec_time_us: 0,
                tled: false,
            });
    }

    fn ensure_unit_runner(&mut self, py: Python, unit: i32, team: Team) {
        if self.unit_runners.contains_key(&unit) {
            return;
        }

        // Create a new subinterpreter for this unit (SHARED_GIL — compatible
        // with extension modules like our Rust bindings).
        // NOTE: Py_NewInterpreterFromConfig swaps the current thread state to
        // the new subinterpreter on success, so all Python calls after this
        // point run inside the subinterpreter until we swap back.
        let sub_tstate: *mut PyThreadState = unsafe {
            let config = PyInterpreterConfig {
                use_main_obmalloc: 1,
                allow_fork: 0,
                allow_exec: 0,
                allow_threads: 1,
                allow_daemon_threads: 1,
                check_multi_interp_extensions: 0,
                gil: PyInterpreterConfig_SHARED_GIL,
            };
            let mut tstate: *mut PyThreadState = std::ptr::null_mut();
            let status = Py_NewInterpreterFromConfig(&raw mut tstate, &raw const config);
            assert!(
                !(pyo3_ffi::PyStatus_IsError(status) != 0 || tstate.is_null()),
                "Py_NewInterpreterFromConfig failed"
            );
            tstate
        };

        // sub_tstate is now the current thread state (Py_NewInterpreterFromConfig
        // swaps in the new subinterpreter's thread state on success).
        // Set up sys.path, import cambc natively in this subinterpreter (so Enum
        // metaclasses are native and iteration works), init the type cache,
        // then load the bot and instantiate the player.
        // Create the watchdog BEFORE loading bot code so it can kill
        // infinite loops in module-level code and Player.__init__().
        let mut wd = watchdog::Watchdog::new(sub_tstate);

        // Arm the watchdog with a generous timeout for loading (5 seconds).
        // Normal imports + __init__ should take <100ms. 5s is the hard cap.
        wd.arm(5.0);

        let result: PyResult<Py<PyAny>> = (|| {
            ensure_sys_path(py, &self.engine_root)?;
            install_cambc_module(py)?;
            let cambc = py.import("cambc")?;
            cambc.setattr("Controller", self.controller_cls.bind(py))?;
            py_convert::init_type_cache(py)?;
            let bot_path = self.team_backends[team.index()]
                .python_path()
                .expect("ensure_unit_runner called for non-Python team");
            let player_cls = load_player_class(py, bot_path)?;
            let player = player_cls.call0(py)?;
            Ok(player)
        })();

        // Disarm the load watchdog. Clear any async exception it may have
        // injected (e.g., bot's __init__ was an infinite loop).
        wd.disarm();
        wd.clear_async_exc();

        // Swap back to the main interpreter's thread state.
        let main_tstate = self.main_tstate;
        unsafe {
            PyThreadState_Swap(main_tstate);
        }

        match result {
            Ok(player) => {
                self.unit_runners.insert(
                    unit,
                    UnitRunner {
                        player,
                        tstate: sub_tstate,
                        watchdog: wd,
                    },
                );
            }
            Err(err) => {
                // Bot failed to load or __init__ crashed in this subinterpreter.
                // Print the error, destroy the unit, and clean up the subinterpreter.
                eprintln!("[runner] unit {unit} failed to init: {err}");
                wd.shutdown();
                unsafe {
                    PyThreadState_Swap(sub_tstate);
                    Python::with_gil(|_py| {
                        py_convert::remove_type_cache();
                    });
                    Py_EndInterpreter(sub_tstate);
                    PyThreadState_Swap(main_tstate);
                }
                let mut game = self.game.borrow_mut();
                if game.entity(unit).is_some() {
                    game.destroy_entity(unit);
                }
            }
        }
    }

    fn cleanup_unit_runners(&mut self) {
        let game = self.game.borrow();
        let dead_python: Vec<i32> = self
            .unit_runners
            .keys()
            .copied()
            .filter(|id| game.entity(*id).is_none())
            .collect();
        let dead_rust: Vec<i32> = self
            .rust_unit_bots
            .keys()
            .copied()
            .filter(|id| game.entity(*id).is_none())
            .collect();
        drop(game);

        self.end_subinterpreters(&dead_python);
        for id in dead_rust {
            if let Some((team, bot_ptr)) = self.rust_unit_bots.remove(&id)
                && let TeamBackend::Rust(rb) = &self.team_backends[team.index()]
            {
                rb.drop_bot(bot_ptr);
            }
        }
    }

    /// Drop all remaining Rust bot pointers (called at end of game).
    fn destroy_all_rust_bots(&mut self) {
        let bots: Vec<(i32, Team, *mut std::ffi::c_void)> = self
            .rust_unit_bots
            .drain()
            .map(|(id, (team, ptr))| (id, team, ptr))
            .collect();
        for (_id, team, ptr) in bots {
            if let TeamBackend::Rust(rb) = &self.team_backends[team.index()] {
                rb.drop_bot(ptr);
            }
        }
    }

    /// End subinterpreters for the given unit IDs and remove their runners.
    fn end_subinterpreters(&mut self, ids: &[i32]) {
        let main_tstate = self.main_tstate;
        for &id in ids {
            let UnitRunner {
                player,
                tstate,
                mut watchdog,
            } = self.unit_runners.remove(&id).unwrap();
            self.bot_extra_time_ns.remove(&id);

            // Shut down the Rust watchdog thread BEFORE destroying the
            // subinterpreter. The watchdog is a native Rust thread (not a
            // Python thread), so no GIL or interpreter context needed.
            watchdog.shutdown();

            unsafe {
                PyThreadState_Swap(tstate);
                Python::with_gil(|_py| {
                    // Drop the player Py<PyAny> while the subinterpreter is still
                    // active so Py_DECREF (and any __del__) runs in the correct
                    // interpreter context.
                    drop(player);
                    py_convert::remove_type_cache();
                });
                Py_EndInterpreter(tstate);
                PyThreadState_Swap(main_tstate);
            }
        }
    }

    /// Destroy all remaining subinterpreters. Must be called before process
    /// exit to avoid "`PyInterpreterState_Delete`: remaining subinterpreters".
    fn destroy_all_subinterpreters(&mut self) {
        let all: Vec<i32> = self.unit_runners.keys().copied().collect();
        self.end_subinterpreters(&all);
    }
}

/// Summary of a completed match, returned to the CLI for display.
pub struct MatchSummary {
    pub winner: Option<Team>,
    pub turns_played: i32,
    pub win_condition: &'static str,
    pub player_a_titanium: i32,
    pub player_a_axionite: i32,
    pub player_a_titanium_collected: i32,
    pub player_a_axionite_collected: i32,
    pub player_b_titanium: i32,
    pub player_b_axionite: i32,
    pub player_b_titanium_collected: i32,
    pub player_b_axionite_collected: i32,
    pub units_a: usize,
    pub units_b: usize,
    pub buildings_a: usize,
    pub buildings_b: usize,
    pub resign_message: Option<String>,
}

pub fn run(args: Args) -> PyResult<MatchSummary> {
    Python::with_gil(|py| {
        ensure_sys_path(py, &args.engine_root)?;
        install_cambc_module(py)?;
        register_rust_module(py)?;

        // --- Phase 1: Initialize type cache (before sandbox, while imports work) ---
        py_convert::init_type_cache(py)?;

        // Capture the main thread's CPU clock ID so the watchdog can measure it.
        init_main_thread_clock_id();

        // Pre-import modules that CPython may lazily load during exception
        // handling or traceback formatting.
        py.run(
            c"import traceback, linecache, tokenize, reprlib, random",
            None,
            None,
        )?;

        // Validate bot AST for `except`/`finally` constructs that could
        // evade the watchdog's async-exception TLE injection. Same
        // semantics as the cambc 1.7.1 binary; see check_except_handlers.
        // Rust bots skip this — they're native code, no Python TLE.
        // Exit codes: 10 = bot A failed, 11 = bot B failed, 12 = both.
        let a_check = match &args.player_a {
            BotKind::Python(p) => check_except_handlers(py, p),
            BotKind::Rust(_) => Ok(()),
        };
        let b_check = match &args.player_b {
            BotKind::Python(p) => check_except_handlers(py, p),
            BotKind::Rust(_) => Ok(()),
        };
        match (&a_check, &b_check) {
            (Err(e), Ok(())) => {
                eprintln!("Bot A failed validation: {e}");
                std::process::exit(10);
            }
            (Ok(()), Err(e)) => {
                eprintln!("Bot B failed validation: {e}");
                std::process::exit(11);
            }
            (Err(ea), Err(eb)) => {
                eprintln!("Both bots failed validation: A={ea}, B={eb}");
                std::process::exit(12);
            }
            _ => {}
        }

        // Trial-load Python bots in the main interpreter to surface
        // module-level errors before gameplay starts. Rust bots are
        // already validated by `cargo build` + `dlopen` of all three
        // FFI symbols (in cli.rs / rust_backend.rs).
        let main_tstate = unsafe { pyo3_ffi::PyThreadState_Get() };
        let mut trial_wd = watchdog::Watchdog::new(main_tstate);

        let a_result = match &args.player_a {
            BotKind::Python(p) => {
                trial_wd.arm(5.0);
                let r = load_player_class(py, p);
                trial_wd.disarm();
                trial_wd.clear_async_exc();
                r.map(|_| ())
            }
            BotKind::Rust(_) => Ok(()),
        };
        let b_result = match &args.player_b {
            BotKind::Python(p) => {
                trial_wd.arm(5.0);
                let r = load_player_class(py, p);
                trial_wd.disarm();
                trial_wd.clear_async_exc();
                r.map(|_| ())
            }
            BotKind::Rust(_) => Ok(()),
        };
        trial_wd.shutdown();
        match (&a_result, &b_result) {
            (Err(e), Ok(())) => {
                eprintln!("Bot A failed to load: {e}");
                std::process::exit(10);
            }
            (Ok(()), Err(e)) => {
                eprintln!("Bot B failed to load: {e}");
                std::process::exit(11);
            }
            (Err(ea), Err(eb)) => {
                eprintln!("Both bots failed to load: A={ea}, B={eb}");
                std::process::exit(12);
            }
            _ => {}
        }

        let (env, cores) = map_loader::load_map(&args.map).map_err(|err| {
            pyo3::exceptions::PyIOError::new_err(format!(
                "failed to load map {}: {}",
                args.map, err
            ))
        })?;
        let game = Game::new(env, cores, args.seed, args.suppress_indicators);

        let random_mod = py.import("random")?;
        random_mod.call_method1("seed", (args.seed,))?;

        let controller_cls = py.import("cambc")?.getattr("Controller")?.unbind();

        let gc_mod = PyModule::import(py, "gc")?.unbind();

        // Freeze all current objects into the permanent GC generation so
        // gc.collect() during gameplay only scans game objects, not the
        // thousands of objects from CLI imports (click, rich, etc.).
        // Without this, the CLI is ~50% slower than calling run_game directly.
        gc_mod.bind(py).call_method0("freeze")?;

        // Capture the main interpreter's thread state so subinterpreter swaps can restore it.
        let main_tstate = unsafe { pyo3_ffi::PyThreadState_Get() };

        // Build per-team execution backends. Rust bots are dlopen'd
        // here (the .so was already built by `cli::resolve_bot`).
        let backend_a = bot_kind_to_backend(args.player_a)?;
        let backend_b = bot_kind_to_backend(args.player_b)?;

        let mut runner = GameRunner {
            game: Rc::new(RefCell::new(game)),
            team_backends: [backend_a, backend_b],
            engine_root: args.engine_root.clone(),
            main_tstate,
            unit_runners: HashMap::new(),
            rust_unit_bots: HashMap::new(),
            turn_timeout_ms: args.turn_timeout_ms,
            max_rounds: args.max_rounds,
            bot_extra_time_ns: HashMap::new(),
            controller_cls,
            gc_mod,
        };
        runner.run(py)?;
        runner.destroy_all_subinterpreters();
        runner.destroy_all_rust_bots();
        let mut game = runner.game.borrow_mut();
        // Final winner: force tiebreak if we're stopping early via
        // `--rounds`, so a still-alive game collapses to a winner via
        // the regular tiebreak instead of returning None.
        let winner = game.winner_team(true);
        libre_replay::write_replay(&game.replay_recorder, &args.replay, winner).map_err(|err| {
            pyo3::exceptions::PyIOError::new_err(format!(
                "failed to write replay {}: {}",
                args.replay, err
            ))
        })?;

        let turns_played = game.turn;
        // The 1.7.1 CLI uses these labels (see cambc/commands/run.py
        // condition_labels): core_destroyed, resigned, axionite_collected,
        // titanium_collected, harvesters, axionite_stored, titanium_stored,
        // coinflip, timeout. We approximate: if a resign_message was
        // recorded, report "resigned"; if a core was destroyed without a
        // resign, report "core_destroyed"; otherwise it's a tiebreak / draw.
        let resigned = game.resign_called;
        let win_condition = match winner {
            Some(_) if resigned => "resigned",
            Some(_) if !game.has_core(Team::A) || !game.has_core(Team::B) => "core_destroyed",
            Some(_) => "resources",
            None => "draw",
        };

        let mut units_a = 0usize;
        let mut units_b = 0usize;
        let mut buildings_a = 0usize;
        let mut buildings_b = 0usize;
        for entity in game.entities.values() {
            let is_unit = matches!(
                entity,
                Entity::BuilderBot(_)
                    | Entity::Gunner(_)
                    | Entity::Sentinel(_)
                    | Entity::Breach(_)
                    | Entity::Launcher(_)
            );
            match (entity.team, is_unit) {
                (Team::A, true) => units_a += 1,
                (Team::A, false) => buildings_a += 1,
                (Team::B, true) => units_b += 1,
                (Team::B, false) => buildings_b += 1,
            }
        }

        let pa = &game.players[0];
        let pb = &game.players[1];

        let resign_message = game.resign_message.clone();

        Ok(MatchSummary {
            winner,
            turns_played,
            win_condition,
            player_a_titanium: pa.titanium,
            player_a_axionite: pa.axionite,
            player_a_titanium_collected: pa.titanium_collected,
            player_a_axionite_collected: pa.axionite_collected,
            player_b_titanium: pb.titanium,
            player_b_axionite: pb.axionite,
            player_b_titanium_collected: pb.titanium_collected,
            player_b_axionite_collected: pb.axionite_collected,
            units_a,
            units_b,
            buildings_a,
            buildings_b,
            resign_message,
        })
    })
}

fn bot_kind_to_backend(kind: BotKind) -> PyResult<TeamBackend> {
    match kind {
        BotKind::Python(p) => Ok(TeamBackend::Python { bot_path: p }),
        BotKind::Rust(p) => RustBackend::load(&p)
            .map(TeamBackend::Rust)
            .map_err(pyo3::exceptions::PyIOError::new_err),
    }
}

/// Validate except handlers in all bot .py files.
///
/// Only allows handlers of the form `except Name:` or `except (Name, ...):`
/// where every name is in the whitelist of known-safe builtin exceptions plus
/// `GameError`. This guarantees the type expression is always a valid exception
/// type, preventing the `TypeError` side-channel that could be used to evade TLE.
///
/// Excluded from the whitelist: `BaseException`, `SystemExit`, `KeyboardInterrupt`
/// (used for TLE/engine control)
fn check_except_handlers(py: Python, main_py_path: &str) -> PyResult<()> {
    // Use the same dict for globals and locals so that `import ast` bindings
    // are visible inside generator expressions (which create their own scope
    // and can only see globals, not exec-level locals).
    let globals = PyDict::new(py);
    globals.set_item("main_py_path", main_py_path)?;
    py.run(
        c"
import ast, os

ALLOWED = {
    # All builtin exceptions minus BaseException, SystemExit, KeyboardInterrupt
    'ArithmeticError', 'AssertionError', 'AttributeError',
    'BaseExceptionGroup', 'BlockingIOError', 'BrokenPipeError', 'BufferError',
    'BytesWarning', 'ChildProcessError', 'ConnectionAbortedError',
    'ConnectionError', 'ConnectionRefusedError', 'ConnectionResetError',
    'DeprecationWarning', 'EOFError', 'EncodingWarning', 'EnvironmentError',
    'Exception', 'ExceptionGroup', 'FileExistsError', 'FileNotFoundError',
    'FloatingPointError', 'FutureWarning', 'GeneratorExit', 'IOError',
    'ImportError', 'ImportWarning', 'IndentationError', 'IndexError',
    'InterruptedError', 'IsADirectoryError', 'KeyError', 'LookupError',
    'MemoryError', 'ModuleNotFoundError', 'NameError', 'NotADirectoryError',
    'NotImplementedError', 'OSError', 'OverflowError',
    'PendingDeprecationWarning', 'PermissionError', 'ProcessLookupError',
    'RecursionError', 'ReferenceError', 'ResourceWarning', 'RuntimeError',
    'RuntimeWarning', 'StopAsyncIteration', 'StopIteration', 'SyntaxError',
    'SyntaxWarning', 'SystemError', 'TabError', 'TimeoutError', 'TypeError',
    'UnboundLocalError', 'UnicodeDecodeError', 'UnicodeEncodeError',
    'UnicodeError', 'UnicodeTranslateError', 'UnicodeWarning', 'UserWarning',
    'ValueError', 'Warning', 'ZeroDivisionError',
    # Game-specific
    'GameError',
}

bot_dir = os.path.dirname(os.path.abspath(main_py_path))

for root, dirs, files in os.walk(bot_dir):
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source, filename=fpath)
        for node in ast.walk(tree):
            # `try ... finally:` runs the finally body even when an async
            # exception (the watchdog's TLE injection) is propagating, so
            # a bot could do unbounded work in a finally block. Match
            # 1.7.1's validator and reject all `finally` blocks outright.
            if isinstance(node, ast.Try) and node.finalbody:
                raise ValueError(f'{fpath}:{node.finalbody[0].lineno}: `finally` blocks are not allowed')
            if not isinstance(node, ast.ExceptHandler):
                continue
            lineno = node.lineno
            ty = node.type
            if ty is None:
                raise ValueError(f'{fpath}:{lineno}: bare `except:` is not allowed; use a specific exception type')
            # Only Name or Tuple-of-Names are permitted — anything else
            # (Attribute, Call, Constant, List, etc.) is rejected.
            if isinstance(ty, ast.Name):
                names = [ty.id]
            elif isinstance(ty, ast.Tuple):
                if not all(isinstance(e, ast.Name) for e in ty.elts):
                    raise ValueError(f'{fpath}:{lineno}: except handler types must be plain names')
                names = [e.id for e in ty.elts]
            else:
                raise ValueError(f'{fpath}:{lineno}: except handler types must be plain names')
            for name in names:
                if name not in ALLOWED:
                    raise ValueError(f'{fpath}:{lineno}: `{name}` is not an allowed exception type')
",
        Some(&globals),
        Some(&globals),
    )?;
    Ok(())
}

fn load_player_class(py: Python, path: &str) -> PyResult<PyObject> {
    // Add the bot's directory to sys.path so sibling imports work
    // (e.g. `import core` from main.py finds core.py in the same dir).
    let bot_dir = std::path::Path::new(path)
        .parent()
        .unwrap_or(std::path::Path::new("."));
    let sys = PyModule::import(py, "sys")?;
    let sys_path = sys.getattr("path")?;
    let bot_dir_str = bot_dir.to_str().unwrap();
    if !sys_path.contains(bot_dir_str)? {
        sys_path.call_method1("insert", (0, bot_dir_str))?;
    }

    let importlib = PyModule::import(py, "importlib.util")?;
    let spec = importlib
        .call_method1("spec_from_file_location", ("player_mod", path))?
        .unbind();
    let module = importlib
        .call_method1("module_from_spec", (spec.clone_ref(py),))?
        .unbind();
    spec.getattr(py, "loader")?
        .call_method1(py, "exec_module", (module.clone_ref(py),))?;
    let player_cls = module.getattr(py, "Player")?;
    Ok(player_cls)
}

fn ensure_sys_path(py: Python, engine_root: &Path) -> PyResult<()> {
    let sys = PyModule::import(py, "sys")?;
    let path = sys.getattr("path")?;
    let py_dir = engine_root.join("py");
    path.call_method1("insert", (0i32, py_dir.to_str().unwrap()))?;
    path.call_method1("insert", (1i32, engine_root.to_str().unwrap()))?;
    Ok(())
}

/// Source of the `cambc` Python shim, embedded at compile time. Defines
/// `Team`, `Direction`, `EntityType`, `ResourceType`, `Environment`,
/// `Position`, `GameConstants`, `GameError`, and a placeholder
/// `Controller` (overwritten by the Rust class before bot code runs).
const CAMBC_SHIM_SOURCE: &str = include_str!("cambc_shim.py");

/// Install our embedded `cambc` package in this interpreter's
/// `sys.modules`, ahead of any disk-resolved `cambc` package. Called once
/// per interpreter (main + each subinterpreter) before any `py.import`,
/// `init_type_cache`, or bot import runs. Removes the engine's runtime
/// dependency on the upstream `cambc` `PyPI` wheel.
///
/// The shim is installed as `cambc._types` (matching the upstream wheel's
/// layout), with `cambc` as a package that re-exports its public symbols.
/// This keeps `__module__` attributes on the classes consistent with the
/// upstream — important because Python's traceback formatter prints
/// `cambc._types.GameError` and that string ends up in the bot's stdout
/// (and thus the replay).
fn install_cambc_module(py: Python) -> PyResult<()> {
    use pyo3::types::{PyDict, PyModule as PyModuleType};
    let globals = PyDict::new(py);
    globals.set_item("__SHIM_SOURCE__", CAMBC_SHIM_SOURCE)?;
    py.run(
        c"
import sys
import types

types_mod = types.ModuleType('cambc._types')
types_mod.__file__ = '<embedded cambc._types>'
exec(compile(__SHIM_SOURCE__, types_mod.__file__, 'exec'), types_mod.__dict__)
sys.modules['cambc._types'] = types_mod

cambc = types.ModuleType('cambc')
cambc.__file__ = '<embedded cambc>'
cambc.__path__ = []  # mark as package so `cambc._types` resolves
cambc._types = types_mod
for _name in ('Team', 'Direction', 'EntityType', 'ResourceType',
              'Environment', 'Position', 'GameConstants', 'GameError',
              'Controller'):
    setattr(cambc, _name, getattr(types_mod, _name))
del _name
sys.modules['cambc'] = cambc
",
        Some(&globals),
        Some(&globals),
    )?;
    let _ = PyModuleType::import(py, "cambc")?;
    Ok(())
}

fn register_rust_module(py: Python) -> PyResult<()> {
    let rust_mod = pyo3::wrap_pymodule!(rustlib::controller::controller_mod)(py);
    let controller = rust_mod.bind(py).getattr("Controller")?;
    let cambc = PyModule::import(py, "cambc")?;
    cambc.setattr("Controller", controller)?;
    Ok(())
}
