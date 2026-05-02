//! Bot-side debug helpers — structured per-turn JSON tree + cambc indicator
//! overlays.
//!
//! Per-turn flow:
//! - The first `Scope` of the turn starts a fresh root node and stack.
//! - Nested `Scope`s become child nodes of the current top-of-stack scope.
//! - Bodies append `msg` and `vis` nodes via `debug()` and `vis()`.
//! - At end of turn, the bot calls `flush()` which prints the root tree as
//!   one line of JSON to stdout.
//!
//! State lives in a `DebugCtx` struct with one process-global instance. Each
//! cdylib has its own copy of the static, and the engine serialises bot
//! calls per turn, so no locking is needed in practice — `unsafe` reads from
//! a `static mut` are fine on this single-threaded path.

use cambc::{Controller, ControllerApi, Position};
use serde_json::{Map, Value};

use crate::config::DEBUG_LOG;
use crate::util::visualiser::{Dump, Dumper};

#[pyrust::inline]
/// Discriminator key for typed JSON nodes (matches Python `_TYPE = "$type"`).
const TYPE_KEY: &str = "$type";

/// Per-frame entry: the index of this scope's child slot inside its parent's
/// `children` array, plus (for timed scopes) the start nanosecond timestamp.
/// The frame at index 0 has `parent_child_idx = None` because it is the root.
struct Frame {
    parent_child_idx: Option<usize>,
    t0_ns: Option<u64>,
}

/// Process-global debug state. The `Dumper`'s same_cache is keyed by
/// `(current_bot_id, name)` so multiple builders running through the
/// same static still get per-bot same-elision.
pub struct DebugCtx {
    /// The root node of the current turn's tree. `None` when no scope is
    /// active. Owns all nested children.
    root: Option<Value>,
    /// Frame stack. Empty when no scope is active. The top frame is always
    /// the current scope; new children are appended to it.
    frames: Vec<Frame>,
    /// Per-bot same-elision dumper for `vis()`.
    dumper: Dumper,
    /// Microseconds spent inside the previous `flush()` call. Recorded into
    /// the next root as `prev_flush_us` so the visualiser can show I/O cost.
    last_flush_us: u64,
    /// The id of the bot currently running. Set by `set_current_bot` at
    /// the top of each `Player::run`. Used by `Dumper` as part of the
    /// same_cache key.
    pub current_bot_id: i32,
}

impl DebugCtx {
    #[must_use]
    pub fn new() -> Self {
        Self {
            root: None,
            frames: pyrust::vec::new!(),
            dumper: Dumper::new(),
            last_flush_us: 0,
            current_bot_id: -1,
        }
    }

    /// Walk into the current scope node (the deepest open scope), using
    /// the parent-child indices recorded in `frames`.
    fn current_scope_mut(&mut self) -> &mut Value {
        let root = pyrust::expect!(pyrust::as_mut!(self.root), "scope active but root is None");
        let mut node: &mut Value = root;
        // Skip frame 0 (the root frame). Each subsequent frame says which
        // child slot of the previous scope it occupies.
        for f in &self.frames[1..] {
            let idx = pyrust::expect!(f.parent_child_idx, "non-root frame must have idx");
            node = &mut node["children"][idx];
        }
        node
    }

    pub fn push_scope(&mut self, label: &str, timed: bool) {
        let node = serde_json::json!({
            TYPE_KEY: "scope",
            "name": pyrust::to_string!(label),
            "children": [],
        });
        let t0_ns = if timed {
            Some(pyrust::time::now_ns!())
        } else {
            None
        };
        if pyrust::is_none!(self.root) {
            // First scope of the turn: this becomes the root.
            self.root = Some(node);
            pyrust::vec::push!(
                self.frames,
                Frame {
                    parent_child_idx: None,
                    t0_ns,
                }
            );
            return;
        }
        let parent = self.current_scope_mut();
        let children = pyrust::serde::array_mut!(parent["children"]);
        let idx = pyrust::len!(children);
        pyrust::vec::push!(children, node);
        pyrust::vec::push!(
            self.frames,
            Frame {
                parent_child_idx: Some(idx),
                t0_ns,
            }
        );
    }

    pub fn pop_scope(&mut self) {
        let frame = pyrust::expect!(
            pyrust::vec::pop!(self.frames),
            "Scope::drop with empty frame stack"
        );
        if let Some(t0_ns) = frame.t0_ns {
            let us = (pyrust::time::now_ns!() - t0_ns) / 1000;
            if pyrust::vec::is_empty!(self.frames) {
                // The frame we just popped was the root.
                let root = pyrust::expect!(pyrust::as_mut!(self.root), "ROOT must be Some");
                root["us"] = serde_json::Value::Number(pyrust::into!(us));
            } else {
                let idx = pyrust::expect!(frame.parent_child_idx, "non-root has idx");
                let parent = self.current_scope_mut();
                parent["children"][idx]["us"] = serde_json::Value::Number(pyrust::into!(us));
            }
        }
        // Once the outer scope drops, clear ROOT so the next turn's first
        // `Scope::new` rebuilds a fresh tree. Mirrors Python's `_stack`
        // emptying on outer-scope exit.
        if pyrust::vec::is_empty!(self.frames) {
            self.root = None;
        }
    }

    fn emit_child(&mut self, node: Value) {
        if pyrust::vec::is_empty!(self.frames) {
            return;
        }
        let parent = self.current_scope_mut();
        pyrust::vec::push!(pyrust::serde::array_mut!(parent["children"]), node);
    }

    pub fn debug(&mut self, tmpl: &str, args: Map<String, Value>) {
        let node = serde_json::json!({
            TYPE_KEY: "msg",
            "tmpl": pyrust::to_string!(tmpl),
            "args": Value::Object(args),
        });
        self.emit_child(node);
    }

    pub fn vis(&mut self, name: &str, value: &Dump) {
        if pyrust::vec::is_empty!(self.frames) {
            return;
        }
        // Split-borrow: walk root → child slot via raw indexing so the
        // borrow into the children Vec is disjoint from `self.dumper`.
        let root = pyrust::expect!(pyrust::as_mut!(self.root), "scope active but root is None");
        let mut node: &mut Value = root;
        for f in &self.frames[1..] {
            let idx = pyrust::expect!(f.parent_child_idx, "non-root frame must have idx");
            node = &mut node["children"][idx];
        }
        let children = pyrust::serde::array_mut!(node["children"]);
        self.dumper.dump(children, self.current_bot_id, name, value);
    }

    pub fn flush(&mut self) {
        let prev_us = self.last_flush_us;
        let root = pyrust::expect!(
            pyrust::as_mut!(self.root),
            "flush() called outside any Scope"
        );
        root["prev_flush_us"] = serde_json::Value::Number(pyrust::into!(prev_us));
        let t0_ns = pyrust::time::now_ns!();
        let payload = pyrust::expect!(serde_json::to_string(root), "root scope must serialise");
        println!("{payload}");
        self.last_flush_us = (pyrust::time::now_ns!() - t0_ns) / 1000;
    }
}

impl Default for DebugCtx {
    fn default() -> Self {
        Self::new()
    }
}

/// Process-global debug context. The `Dumper` inside same-elides per
/// `(bot_id, name)`, so multiple builders sharing the static still get
/// per-builder same_cache isolation. `current_bot_id` is set at the top
/// of `Player::run` via `set_current_bot` and used by `Dumper.dump`.
static mut CTX: Option<DebugCtx> = None;

#[allow(static_mut_refs)]
fn ctx() -> &'static mut DebugCtx {
    if unsafe { pyrust::is_none!(CTX) } {
        unsafe { CTX = Some(DebugCtx::new()) };
    }
    unsafe { pyrust::unwrap!(pyrust::as_mut!(CTX)) }
}

/// Set the bot id used as the same-elision cache key for subsequent
/// `vis()` calls. Call at the top of each `run()` before any scope opens.
pub fn set_current_bot(id: i32) {
    if !DEBUG_LOG {
        return;
    }
    ctx().current_bot_id = id;
}

/// Tree-internal scope guard. The full implementation only exists when
/// `DEBUG_LOG=1` was set at build time (build.rs emits `--cfg debug_log`).
/// When the cfg is off, `Scope` is a ZST whose constructors and Drop are
/// no-ops, so `let _g = Scope::new(...)` compiles to nothing in release.
///
/// pyrust always sees the `#[pyrust::context_manager]` annotation on this
/// struct (it ignores `#[cfg]`), so Python emission still gets `with`-blocks
/// regardless of the native build's cfg state.
#[pyrust::context_manager]
#[cfg(debug_log)]
pub struct Scope {
    pub label: String,
}

#[cfg(debug_log)]
impl Scope {
    /// Push an untimed scope onto the stack. The returned guard pops on drop.
    #[must_use]
    pub fn new(label: &str) -> Self {
        ctx().push_scope(label, false);
        Self {
            label: pyrust::to_string!(label),
        }
    }

    /// Push a timed scope; on drop, records `us` (microseconds elapsed).
    /// Mirrors Python `Scope(label, time=True)`.
    #[must_use]
    pub fn new_timed(label: &str) -> Self {
        ctx().push_scope(label, true);
        Self {
            label: pyrust::to_string!(label),
        }
    }
}

#[cfg(debug_log)]
impl Drop for Scope {
    fn drop(&mut self) {
        ctx().pop_scope();
    }
}

#[pyrust::context_manager]
#[cfg(not(debug_log))]
pub struct Scope;

#[cfg(not(debug_log))]
impl Scope {
    #[inline(always)]
    #[must_use]
    pub const fn new(_label: &str) -> Self {
        Self
    }

    #[inline(always)]
    #[must_use]
    pub const fn new_timed(_label: &str) -> Self {
        Self
    }
}

/// Append a `msg` node under the current scope. `tmpl` is a Python-style
/// format-string fragment using `{name}` slots; `args` provide the values
/// referenced by those slots.
pub fn debug(tmpl: &str, args: Map<String, Value>) {
    if !DEBUG_LOG {
        return;
    }
    ctx().debug(tmpl, args);
}

/// Append a vis node under the current scope, routed through the per-unit
/// `Dumper` for same-elision.
pub fn vis(name: &str, value: &Dump) {
    if !DEBUG_LOG {
        return;
    }
    ctx().vis(name, value);
}

/// Print the root scope as one JSON line to stdout. MUST be called from
/// inside the top-level `Scope::new("turn")` block, before that block's
/// guard drops.
pub fn flush() {
    if !DEBUG_LOG {
        return;
    }
    ctx().flush();
}

/// Wrapper over `Controller::draw_indicator_dot`. Engine-side overlay,
/// visible to all spectators, on/off globally per replay.
pub fn dot(ct: &mut Controller<'_>, pos: Position, r: i32, g: i32, b: i32) {
    if !DEBUG_LOG {
        return;
    }
    pyrust::unwrap!(ct.draw_indicator_dot(pos, r, g, b));
}

/// Wrapper over `Controller::draw_indicator_line`.
pub fn line(ct: &mut Controller<'_>, pos_a: Position, pos_b: Position, r: i32, g: i32, b: i32) {
    if !DEBUG_LOG {
        return;
    }
    pyrust::unwrap!(ct.draw_indicator_line(pos_a, pos_b, r, g, b));
}
