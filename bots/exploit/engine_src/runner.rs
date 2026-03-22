mod watchdog;

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
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
use crate::cli::Args;
use crate::common::game_constants::MAX_TURNS;
use crate::common::Team;
use crate::game::Game;
use crate::game_map::Entity;
use crate::map_loader;
use crate::replay::recorder::GameDiff;

/// Returns the calling thread's cumulative CPU time in nanoseconds.
/// Uses CLOCK_THREAD_CPUTIME_ID (per-thread, not process-wide).
/// Used by Controller::check_deadline() for cooperative TLE enforcement.
/// Returns 0 when the `tle` feature is disabled.
#[cfg(feature = "tle")]
pub fn thread_cpu_time_ns() -> u64 {
    cpu_time_ns_for_clock(libc::CLOCK_THREAD_CPUTIME_ID)
}

#[cfg(not(feature = "tle"))]
pub fn thread_cpu_time_ns() -> u64 {
    0
}

#[cfg(feature = "tle")]
fn cpu_time_ns_for_clock(clock_id: libc::clockid_t) -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(clock_id, &mut ts); }
    ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64
}

/// CPU clock ID for the main thread. Captured at startup via
/// pthread_getcpuclockid so the watchdog on core 0 can read the main
/// thread's CPU time without the GIL.
#[cfg(feature = "tle")]
static MAIN_THREAD_CLOCK_ID: std::sync::atomic::AtomicI32 = std::sync::atomic::AtomicI32::new(0);

#[cfg(feature = "tle")]
fn init_main_thread_clock_id() {
    let mut clock_id: libc::clockid_t = 0;
    unsafe { libc::pthread_getcpuclockid(libc::pthread_self(), &mut clock_id); }
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
pub fn main_thread_cpu_time_ns() -> u64 { 0 }

/// CPU start time (absolute ns) for the current unit turn.
/// Written by perform_unit_actions, read by Controller::get_cpu_time_elapsed.
pub(crate) static CPU_START_NS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
/// CPU deadline (absolute ns, in per-thread CPU time) for the current unit turn.
/// Written by perform_unit_actions, read by Controller::check_deadline.
pub(crate) static CPU_DEADLINE_NS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// Percent of the per-turn time limit that can be banked as extra time.
const ADAPTIVE_TIME_PERCENT: u64 = 5;

/// Install a seccomp-bpf filter blocking execve/execveat syscalls.
/// Called from inside titan_runner AFTER nsjail has exec'd us, so the filter
/// only blocks future exec attempts (bot code). Thread creation (clone) is
/// still allowed for the watchdog.
#[cfg(feature = "tle")]
fn install_seccomp() {
    // BPF instruction helpers
    #[repr(C)]
    struct SockFilter { code: u16, jt: u8, jf: u8, k: u32 }
    #[repr(C)]
    struct SockFprog { len: u16, filter: *const SockFilter }

    const BPF_LD_W_ABS: u16 = 0x20;    // LD | W | ABS
    const BPF_JMP_JEQ_K: u16 = 0x15;   // JMP | JEQ | K
    const BPF_RET_K: u16 = 0x06;       // RET | K
    const SECCOMP_RET_ALLOW: u32 = 0x7fff_0000;
    const SECCOMP_RET_ERRNO_EPERM: u32 = 0x0005_0001; // ERRNO | EPERM

    // Syscall numbers (aarch64 / x86_64)
    #[cfg(target_arch = "aarch64")]
    const NR_EXECVE: u32 = 221;
    #[cfg(target_arch = "aarch64")]
    const NR_EXECVEAT: u32 = 281;
    #[cfg(target_arch = "x86_64")]
    const NR_EXECVE: u32 = 59;
    #[cfg(target_arch = "x86_64")]
    const NR_EXECVEAT: u32 = 322;

    let filter = [
        // [0] Load syscall number from seccomp_data.nr (offset 0)
        SockFilter { code: BPF_LD_W_ABS, jt: 0, jf: 0, k: 0 },
        // [1] if nr == execve → skip 2 to [4] (deny); else fall through to [2]
        SockFilter { code: BPF_JMP_JEQ_K, jt: 2, jf: 0, k: NR_EXECVE },
        // [2] if nr == execveat → skip 1 to [4] (deny); else fall through to [3]
        SockFilter { code: BPF_JMP_JEQ_K, jt: 1, jf: 0, k: NR_EXECVEAT },
        // [3] allow
        SockFilter { code: BPF_RET_K, jt: 0, jf: 0, k: SECCOMP_RET_ALLOW },
        // [4] deny with EPERM
        SockFilter { code: BPF_RET_K, jt: 0, jf: 0, k: SECCOMP_RET_ERRNO_EPERM },
    ];
    let prog = SockFprog { len: filter.len() as u16, filter: filter.as_ptr() };

    unsafe {
        // Required before SECCOMP_MODE_FILTER
        libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
        let ret = libc::prctl(
            libc::PR_SET_SECCOMP,
            2, // SECCOMP_MODE_FILTER
            &prog as *const SockFprog,
            0,
            0,
        );
        if ret != 0 {
            eprintln!(
                "Warning: seccomp filter failed: {}",
                std::io::Error::last_os_error()
            );
        }
    }
}

#[cfg(not(feature = "tle"))]
fn install_seccomp() {
    // No-op when TLE feature disabled (macOS dev, CI without tle)
}

/// In-memory bot source files, decrypted from encrypted on-disk copies.
/// Module names map to source code strings. Only exists when sandboxed.
type BotSources = HashMap<String, String>;

/// Read all .py files from a bot directory, XOR-decrypt with key, return as
/// module_name -> source_code map. Module names use dot notation for packages
/// (e.g. "core.pathfinding" for core/pathfinding.py).
fn read_bot_sources(bot_main: &str, key: &[u8]) -> BotSources {
    let main_path = PathBuf::from(bot_main);
    let bot_dir = main_path.parent().unwrap_or(Path::new("."));
    let mut sources = HashMap::new();

    fn walk(dir: &Path, base: &Path, key: &[u8], sources: &mut BotSources) {
        let Ok(entries) = std::fs::read_dir(dir) else { return };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                walk(&path, base, key, sources);
            } else if path.extension().is_some_and(|e| e == "py") {
                let rel = path.strip_prefix(base).unwrap();
                // Convert path to Python module name:
                // main.py -> "main", helpers.py -> "helpers",
                // core/__init__.py -> "core", core/foo.py -> "core.foo"
                let module_name = if rel.file_stem().unwrap() == "__init__" {
                    rel.parent()
                        .unwrap()
                        .to_str()
                        .unwrap()
                        .replace('/', ".")
                } else {
                    rel.with_extension("")
                        .to_str()
                        .unwrap()
                        .replace('/', ".")
                };
                if let Ok(encrypted) = std::fs::read(&path) {
                    let decrypted: Vec<u8> = encrypted
                        .iter()
                        .enumerate()
                        .map(|(i, &b)| b ^ key[i % key.len()])
                        .collect();
                    if let Ok(source) = String::from_utf8(decrypted) {
                        sources.insert(module_name, source);
                    }
                }
            }
        }
    }

    walk(bot_dir, bot_dir, key, &mut sources);
    sources
}

/// Read encryption keys from stdin (hex-encoded, one per line).
/// Must be called before Python initialisation consumes stdin.
pub fn read_encryption_keys() -> Option<([u8; 256], [u8; 256])> {
    use std::io::Read;
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).ok()?;
    let mut lines = input.lines();
    let key_a = hex_decode(lines.next()?)?;
    let key_b = hex_decode(lines.next()?)?;
    Some((key_a, key_b))
}

fn hex_decode(s: &str) -> Option<[u8; 256]> {
    let bytes: Vec<u8> = (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok())
        .collect::<Option<Vec<u8>>>()?;
    if bytes.len() != 256 {
        return None;
    }
    let mut arr = [0u8; 256];
    arr.copy_from_slice(&bytes);
    Some(arr)
}

struct UnitRunner {
    player: Py<PyAny>,
    tstate: *mut PyThreadState,
    watchdog: watchdog::Watchdog,
}

struct GameRunner {
    game: Rc<RefCell<Game>>,
    /// Per-team bot source paths (on disk, possibly encrypted).
    bot_paths: [String; 2],
    /// Engine root path, used when initialising a new subinterpreter's sys.path.
    engine_root: std::path::PathBuf,
    /// In-memory decrypted bot sources (sandboxed mode only).
    /// When Some, load_player_class uses in-memory sources instead of disk files.
    bot_sources: Option<[BotSources; 2]>,
    /// The main interpreter's thread state, captured at construction time.
    /// We swap back to this after entering/leaving each unit's subinterpreter.
    main_tstate: *mut PyThreadState,
    /// Per-unit runner: player object + subinterpreter thread state + watchdog.
    unit_runners: HashMap<i32, UnitRunner>,
    turn_timeout_ms: u64,
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
        for i in 0..MAX_TURNS {
            self.run_turn(py, &gc)?;
            if i % 100 == 0 {
                println!("Completed turn {}", i);
            }
            if self.game.borrow_mut().winner_team().is_some() {
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
            unsafe { PyThreadState_Swap(sub_tstate); }

            let runner = &self.unit_runners[&unit_id];
            let player = runner.player.clone_ref(py);

            // Clear any pending async exception from a previous turn.
            // Direct memory write (no GIL needed for the clear itself),
            // then absorb any already-raised exception via a Python no-op.
            runner.watchdog.clear_async_exc();
            for _ in 0..100 {
                match py.eval(c"None", None, None) {
                    Ok(_) => break,
                    Err(_) => { runner.watchdog.clear_async_exc(); continue; }
                }
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
                    unsafe { PyThreadState_Swap(self.main_tstate); }
                    let mut game = self.game.borrow_mut();
                    if game.entity(unit_id).is_some() {
                        game.destroy_entity(unit_id);
                    }
                    continue;
                }
            };

            // Set the deadline as late as possible so setup overhead isn't
            // counted against the bot's CPU budget.
            let cpu_start = thread_cpu_time_ns();
            CPU_START_NS.store(cpu_start, std::sync::atomic::Ordering::Relaxed);
            CPU_DEADLINE_NS.store(cpu_start + effective_budget_ns, std::sync::atomic::Ordering::Relaxed);

            // Arm the Rust watchdog — pure Rust, no GIL needed.
            runner.watchdog.arm(wall_timeout);

            let result = player.call_method1(py, "run", (controller,));
            let cpu_elapsed_ns = thread_cpu_time_ns() - cpu_start;

            // Disarm the watchdog — pure Rust, no GIL needed.
            runner.watchdog.disarm();

            // Clear any async exception injected between player.run() return
            // and disarm, then absorb any already-raised exception.
            runner.watchdog.clear_async_exc();
            for _ in 0..100 {
                match py.eval(c"None", None, None) {
                    Ok(_) => break,
                    Err(_) => { runner.watchdog.clear_async_exc(); continue; }
                }
            }

            // Handle errors (still in subinterpreter for err.print)
            let mut destroy_unit = false;

            if let Err(ref err) = result {
                if err.is_instance_of::<pyo3::exceptions::PyKeyboardInterrupt>(py) {
                    unsafe { PyThreadState_Swap(self.main_tstate); }
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
            unsafe { PyThreadState_Swap(self.main_tstate); }

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
            let status = Py_NewInterpreterFromConfig(&mut tstate, &config);
            if pyo3_ffi::PyStatus_IsError(status) != 0 || tstate.is_null() {
                panic!("Py_NewInterpreterFromConfig failed");
            }
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
            let cambc = py.import("cambc")?;
            cambc.setattr("Controller", self.controller_cls.bind(py))?;
            py_convert::init_type_cache(py)?;
            let player_cls = if let Some(ref bot_sources) = self.bot_sources {
                load_player_class_from_memory(py, &bot_sources[team.index()])?
            } else {
                load_player_class(py, &self.bot_paths[team.index()])?
            };

            // Strip dangerous modules/attributes BEFORE Player.__init__() so
            // bots can't save references to dangerous functions. seccomp is already installed
            // (blocks execve at kernel level). Import hook (MemoryFinder) is
            // active so __init__ imports still work via in-memory sources.
            if self.bot_sources.is_some() {
                py.run(c"
import sys, os, builtins

# Remove builtins.open — prevents file reads (source is in memory)
del builtins.open

# Remove dangerous os functions (keep os.path for bot convenience)
for _a in ('system','popen','exec','execl','execle','execlp','execlpe',
           'execv','execve','execvp','execvpe','fork','forkpty',
           'spawn','spawnl','spawnle','spawnlp','spawnlpe',
           'spawnv','spawnve','spawnvp','spawnvpe',
           'kill','killpg','open','read','write','fdopen',
           'listdir','scandir','walk',
           'symlink','link','rename','replace','remove','unlink','rmdir',
           'chmod','chown','lchown','mkdir','makedirs'):
    if hasattr(os, _a): delattr(os, _a)

# Remove gc introspection
import gc
for _a in ('get_objects','get_referrers','get_referents'):
    if hasattr(gc, _a): delattr(gc, _a)

# Neuter _thread: replace with a fake module so import _thread gives a
# module without start_new_thread. The watchdog thread is already running.
import types as _types
_fake_thread = _types.ModuleType('_thread')
_fake_thread.LockType = type(__import__('_thread').allocate_lock())
_fake_thread.allocate_lock = __import__('_thread').allocate_lock
_fake_thread.get_ident = __import__('_thread').get_ident
_fake_thread._count = __import__('_thread')._count
# start_new_thread deliberately NOT copied
sys.modules['_thread'] = _fake_thread
sys.modules['threading'] = None  # block threading import entirely

# Prevent removing our fake _thread from sys.modules by wrapping it
# in a dict subclass that blocks deletion/replacement of protected keys.
class _ProtectedModules(dict):
    _locked = frozenset({'_thread', 'threading'})
    def __delitem__(self, key):
        if key in self._locked: return
        super().__delitem__(key)
    def __setitem__(self, key, value):
        if key in self._locked: return
        super().__setitem__(key, value)
    def pop(self, key, *args):
        if key in self._locked: return self.get(key)
        return super().pop(key, *args)
_pm = _ProtectedModules(sys.modules)
sys.modules = _pm

# Remove importlib.reload to prevent restoring the real _thread module
import importlib as _il
if hasattr(_il, 'reload'): del _il.reload

# Remove other dangerous modules
for _m in ('subprocess','socket','signal','_posixsubprocess',
           'ctypes','_ctypes',
           '_multiprocessing','multiprocessing','_posixshmem',
           '_socket','_ssl','ssl','mmap','fcntl','resource',
           'select','readline','termios','syslog','grp'):
    sys.modules.pop(_m, None)

del _a, _m, _types, _fake_thread, _il, _pm, _ProtectedModules
", None, None)?;
            }

            // NOW instantiate Player — __init__ runs with all protections active.
            let player = player_cls.call0(py)?;
            Ok(player)
        })();

        // Disarm the load watchdog. Clear any async exception it may have
        // injected (e.g., bot's __init__ was an infinite loop).
        wd.disarm();
        wd.clear_async_exc();

        // Swap back to the main interpreter's thread state.
        let main_tstate = self.main_tstate;
        unsafe { PyThreadState_Swap(main_tstate); }

        match result {
            Ok(player) => {
                self.unit_runners.insert(unit, UnitRunner {
                    player, tstate: sub_tstate, watchdog: wd,
                });
            }
            Err(err) => {
                // Bot failed to load or __init__ crashed in this subinterpreter.
                // Print the error, destroy the unit, and clean up the subinterpreter.
                eprintln!("[runner] unit {unit} failed to init: {err}");
                wd.shutdown();
                unsafe {
                    PyThreadState_Swap(sub_tstate);
                    Python::with_gil(|_py| { py_convert::remove_type_cache(); });
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
        let dead: Vec<i32> = self
            .unit_runners
            .keys()
            .copied()
            .filter(|id| game.entity(*id).is_none())
            .collect();
        drop(game);

        self.end_subinterpreters(&dead);
    }

    /// End subinterpreters for the given unit IDs and remove their runners.
    fn end_subinterpreters(&mut self, ids: &[i32]) {
        let main_tstate = self.main_tstate;
        for &id in ids {
            let UnitRunner { player, tstate, mut watchdog } = self.unit_runners.remove(&id).unwrap();
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
    /// exit to avoid "PyInterpreterState_Delete: remaining subinterpreters".
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
}

pub fn run(args: Args) -> PyResult<MatchSummary> {
    Python::with_gil(|py| {
        ensure_sys_path(py, &args.engine_root)?;
        register_rust_module(py)?;

        // --- Phase 1: Initialize type cache (before sandbox, while imports work) ---
        py_convert::init_type_cache(py)?;

        // Capture the main thread's CPU clock ID so the watchdog can measure it.
        init_main_thread_clock_id();

        // Pre-import modules that CPython may lazily load during exception
        // handling or traceback formatting.
        py.run(c"import traceback, linecache, tokenize, reprlib, random", None, None)?;

        // Sandbox note: Python-level audit hooks (sys.addaudithook) are NOT used.
        // They are per-interpreter in CPython 3.12+ and explicitly documented as
        // unsuitable for sandboxing. All security enforcement is at the OS level
        // via nsjail (seccomp, namespaces, read-only mounts, rlimits) and
        // deletion of dangerous C extensions (_ctypes.so, _posixsubprocess.so).
        //
        // When sandboxed, bot source is encrypted on disk. Encryption keys are
        // read from stdin (consumed before bot code runs). Source is decrypted
        // into Rust memory and loaded via exec() — never written to disk.

        // --- Decrypt bot sources (sandboxed only) ---
        let bot_sources = if args.sandboxed {
            if let Some((key_a, key_b)) = args.encryption_keys.as_ref() {
                let src_a = read_bot_sources(&args.player_a, key_a);
                let src_b = read_bot_sources(&args.player_b, key_b);
                Some([src_a, src_b])
            } else {
                None
            }
        } else {
            None
        };

        // --- Validate bot code ---
        // Exit codes: 10 = bot A failed, 11 = bot B failed, 12 = both failed.
        // check_except_handlers validates from encrypted files on disk — the
        // encryption is XOR so we decrypt inline. But actually, for sandboxed
        // mode with in-memory sources, we validate from the decrypted sources.
        // For unsandboxed (CLI), we validate from disk as before.
        if bot_sources.is_none() {
            // File-based validation (CLI mode)
            let a_check = check_except_handlers(py, &args.player_a);
            let b_check = check_except_handlers(py, &args.player_b);
            match (&a_check, &b_check) {
                (Err(e), Ok(_)) => {
                    eprintln!("Bot A failed validation: {e}");
                    std::process::exit(10);
                }
                (Ok(_), Err(e)) => {
                    eprintln!("Bot B failed validation: {e}");
                    std::process::exit(11);
                }
                (Err(ea), Err(eb)) => {
                    eprintln!("Both bots failed validation: A={ea}, B={eb}");
                    std::process::exit(12);
                }
                _ => {}
            }
        }
        // TODO: validate except handlers from in-memory sources for sandboxed mode

        // Do a trial load in the main interpreter to validate both bots.
        // Protect with a watchdog (5s timeout) in case bot has a module-level
        // infinite loop. The watchdog fires SystemExit which causes the load
        // to return Err.
        let main_tstate = unsafe { pyo3_ffi::PyThreadState_Get() };
        let mut trial_wd = watchdog::Watchdog::new(main_tstate);

        // Load each bot with its own 5s timeout. A module-level infinite
        // loop will be killed by the watchdog and return Err(SystemExit).
        trial_wd.arm(5.0);
        let a_result = if let Some(ref sources) = bot_sources {
            load_player_class_from_memory(py, &sources[0])
        } else {
            load_player_class(py, &args.player_a)
        };
        trial_wd.disarm();
        trial_wd.clear_async_exc();

        trial_wd.arm(5.0);
        let b_result = if let Some(ref sources) = bot_sources {
            load_player_class_from_memory(py, &sources[1])
        } else {
            load_player_class(py, &args.player_b)
        };
        trial_wd.disarm();
        trial_wd.clear_async_exc();
        trial_wd.shutdown();
        match (&a_result, &b_result) {
            (Err(e), Ok(_)) => {
                eprintln!("Bot A failed to load: {e}");
                std::process::exit(10);
            }
            (Ok(_), Err(e)) => {
                eprintln!("Bot B failed to load: {e}");
                std::process::exit(11);
            }
            (Err(ea), Err(eb)) => {
                eprintln!("Both bots failed to load: A={ea}, B={eb}");
                std::process::exit(12);
            }
            _ => {}
        }

        // Install seccomp filter to block execve/execveat at kernel level.
        // Done after trial load (which doesn't exec) but before gameplay.
        // This is per-process and irreversible — no Python code can bypass it.
        if args.sandboxed {
            install_seccomp();
        }

        let (env, cores) = map_loader::load_map(&args.map).map_err(|err| {
            pyo3::exceptions::PyIOError::new_err(format!(
                "failed to load map {}: {}",
                args.map, err
            ))
        })?;
        let game = Game::new(env, cores, args.seed, args.suppress_indicators);

        // Seed Python's random module so bot RNG is reproducible.
        let random_mod = py.import("random")?;
        random_mod.call_method1("seed", (args.seed,))?;

        // Grab the Controller class so we can set it on each subinterpreter's cambc.
        let controller_cls = py.import("cambc")?.getattr("Controller")?.unbind();

        let gc_mod = PyModule::import(py, "gc")?.unbind();

        // Freeze all current objects into the permanent GC generation so
        // gc.collect() during gameplay only scans game objects, not the
        // thousands of objects from CLI imports (click, rich, etc.).
        // Without this, the CLI is ~50% slower than calling run_game directly.
        gc_mod.bind(py).call_method0("freeze")?;

        // Capture the main interpreter's thread state so subinterpreter swaps can restore it.
        let main_tstate = unsafe { pyo3_ffi::PyThreadState_Get() };

        let mut runner = GameRunner {
            game: Rc::new(RefCell::new(game)),
            bot_paths: [args.player_a.clone(), args.player_b.clone()],
            engine_root: args.engine_root.to_path_buf(),
            bot_sources,
            main_tstate,
            unit_runners: HashMap::new(),
            turn_timeout_ms: args.turn_timeout_ms,
            bot_extra_time_ns: HashMap::new(),
            controller_cls,
            gc_mod,
        };
        runner.run(py)?;
        runner.destroy_all_subinterpreters();
        let mut game = runner.game.borrow_mut();
        let winner = game.winner_team();
        game.replay_recorder
            .write_to_path(&args.replay, winner)
            .map_err(|err| {
                pyo3::exceptions::PyIOError::new_err(format!(
                    "failed to write replay {}: {}",
                    args.replay, err
                ))
            })?;

        let turns_played = game.turn;
        let win_condition = match winner {
            Some(_) if !game.has_core(Team::A) || !game.has_core(Team::B) => "core_destroyed",
            Some(_) => "resources",
            None => "draw",
        };

        let mut units_a = 0usize;
        let mut units_b = 0usize;
        let mut buildings_a = 0usize;
        let mut buildings_b = 0usize;
        for entity in game.entities.values() {
            let is_unit = matches!(entity, Entity::BuilderBot(_) | Entity::Gunner(_) | Entity::Sentinel(_) | Entity::Breach(_) | Entity::Launcher(_));
            match (entity.team, is_unit) {
                (Team::A, true) => units_a += 1,
                (Team::A, false) => buildings_a += 1,
                (Team::B, true) => units_b += 1,
                (Team::B, false) => buildings_b += 1,
            }
        }

        let pa = &game.players[0];
        let pb = &game.players[1];

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
        })
    })
}

/// Validate except handlers in all bot .py files.
///
/// Only allows handlers of the form `except Name:` or `except (Name, ...):`
/// where every name is in the whitelist of known-safe builtin exceptions plus
/// GameError. This guarantees the type expression is always a valid exception
/// type, preventing the TypeError side-channel that could be used to evade TLE.
///
/// Excluded from the whitelist: BaseException, SystemExit, KeyboardInterrupt
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

/// Load a bot's Player class from in-memory source files (decrypted).
/// Installs a custom import hook so `import helpers` etc. resolves from memory.
fn load_player_class_from_memory(py: Python, sources: &BotSources) -> PyResult<PyObject> {
    let globals = PyDict::new(py);
    // Convert Rust HashMap to Python dict
    let py_sources = PyDict::new(py);
    for (name, source) in sources {
        py_sources.set_item(name, source)?;
    }
    globals.set_item("_sources", py_sources)?;
    py.run(
        c"
import sys, types, importlib.abc, importlib.machinery

class _MemoryFinder(importlib.abc.MetaPathFinder):
    def __init__(self, sources):
        self.sources = sources
    def find_spec(self, name, path, target=None):
        if name in self.sources:
            is_pkg = any(k.startswith(name + '.') for k in self.sources)
            spec = importlib.machinery.ModuleSpec(
                name, _MemoryLoader(self.sources[name], name),
                origin='<bot>/' + name.replace('.', '/') + '.py',
                is_package=is_pkg,
            )
            if is_pkg:
                spec.submodule_search_locations = ['<bot>/' + name.replace('.', '/')]
            return spec
        return None

class _MemoryLoader(importlib.abc.Loader):
    def __init__(self, source, name):
        self.source = source
        self.name = name
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        code = compile(self.source, spec_origin(module), 'exec')
        exec(code, module.__dict__)

def spec_origin(module):
    s = getattr(module, '__spec__', None)
    return s.origin if s else '<bot>/' + module.__name__ + '.py'

_finder = _MemoryFinder(_sources)
sys.meta_path.insert(0, _finder)

# Load the main module
import importlib
_player_mod = importlib.import_module('main')
_Player = _player_mod.Player
",
        Some(&globals),
        Some(&globals),
    )?;
    let player_cls = globals
        .get_item("_Player")?
        .expect("Player class not found")
        .unbind();
    Ok(player_cls)
}

fn ensure_sys_path(py: Python, engine_root: &Path) -> PyResult<()> {
    let sys = PyModule::import(py, "sys")?;
    let path = sys.getattr("path")?;
    let py_dir = engine_root.join("py");
    path.call_method1("insert", (0, py_dir.to_str().unwrap()))?;
    path.call_method1("insert", (1, engine_root.to_str().unwrap()))?;
    Ok(())
}

fn register_rust_module(py: Python) -> PyResult<()> {
    let rust_mod = pyo3::wrap_pymodule!(rustlib::controller::controller_mod)(py);
    let controller = rust_mod.bind(py).getattr("Controller")?;
    let cambc = PyModule::import(py, "cambc")?;
    cambc.setattr("Controller", controller)?;
    Ok(())
}
