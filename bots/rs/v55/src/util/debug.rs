//! Translation of `bots/intgrah/v54.7.9/util/debug.py`.
//!
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

use std::time::Instant;

use cambc::{Controller, ControllerApi, Position};
use serde_json::{Map, Value};

use crate::config::DEBUG_LOG;
use crate::util::visualiser::{Dump, Dumper};

/// Discriminator key for typed JSON nodes (matches Python `_TYPE = "$type"`).
const TYPE_KEY: &str = "$type";

/// Per-frame entry: the index of this scope's child slot inside its parent's
/// `children` array, plus (for timed scopes) the start instant. The frame at
/// index 0 has `parent_child_idx = None` because it is the root.
struct Frame {
    parent_child_idx: Option<usize>,
    t0: Option<Instant>,
}

/// Per-bot debug state. One instance per process via `DebugCtx::global()`.
pub struct DebugCtx {
    /// The root node of the current turn's tree. `None` when no scope is
    /// active. Owns all nested children.
    root: Option<Map<String, Value>>,
    /// Frame stack. Empty when no scope is active. The top frame is always
    /// the current scope; new children are appended to it.
    frames: Vec<Frame>,
    /// Per-unit same-elision dumper for `vis()`.
    dumper: Dumper,
    /// Microseconds spent inside the previous `flush()` call. Recorded into
    /// the next root as `prev_flush_us` so the visualiser can show I/O cost.
    last_flush_us: u64,
}

impl DebugCtx {
    #[must_use]
    pub fn new() -> Self {
        Self {
            root: None,
            frames: Vec::new(),
            dumper: Dumper::new(),
            last_flush_us: 0,
        }
    }

    /// Walk into the current scope node (the deepest open scope), using
    /// the parent-child indices recorded in `frames`.
    fn current_scope_mut(&mut self) -> &mut Map<String, Value> {
        let root = self.root.as_mut().expect("scope active but root is None");
        let mut node: &mut Map<String, Value> = root;
        // Skip frame 0 (the root frame). Each subsequent frame says which
        // child slot of the previous scope it occupies.
        for f in &self.frames[1..] {
            let idx = f.parent_child_idx.expect("non-root frame must have idx");
            let children = node
                .get_mut("children")
                .and_then(Value::as_array_mut)
                .expect("scope node missing children array");
            node = children
                .get_mut(idx)
                .and_then(Value::as_object_mut)
                .expect("child at idx must be a scope object");
        }
        node
    }

    pub fn push_scope(&mut self, label: &str, timed: bool) {
        let mut node = Map::new();
        node.insert(TYPE_KEY.to_string(), Value::String("scope".to_string()));
        node.insert("name".to_string(), Value::String(label.to_string()));
        node.insert("children".to_string(), Value::Array(Vec::new()));
        let t0 = if timed { Some(Instant::now()) } else { None };
        if self.root.is_none() {
            // First scope of the turn: this becomes the root.
            self.root = Some(node);
            self.frames.push(Frame {
                parent_child_idx: None,
                t0,
            });
            return;
        }
        let parent = self.current_scope_mut();
        let children = parent
            .get_mut("children")
            .and_then(Value::as_array_mut)
            .expect("scope node missing children array");
        let idx = children.len();
        children.push(Value::Object(node));
        self.frames.push(Frame {
            parent_child_idx: Some(idx),
            t0,
        });
    }

    pub fn pop_scope(&mut self) {
        let frame = self
            .frames
            .pop()
            .expect("Scope::drop with empty frame stack");
        if let Some(t0) = frame.t0 {
            let us = t0.elapsed().as_micros() as u64;
            if self.frames.is_empty() {
                // The frame we just popped was the root.
                let root = self.root.as_mut().expect("ROOT must be Some");
                root.insert("us".to_string(), Value::Number(us.into()));
            } else {
                let idx = frame.parent_child_idx.expect("non-root has idx");
                let parent = self.current_scope_mut();
                let children = parent
                    .get_mut("children")
                    .and_then(Value::as_array_mut)
                    .expect("scope node missing children array");
                let node = children
                    .get_mut(idx)
                    .and_then(Value::as_object_mut)
                    .expect("child at idx must be a scope object");
                node.insert("us".to_string(), Value::Number(us.into()));
            }
        }
        // Once the outer scope drops, clear ROOT so the next turn's first
        // `Scope::new` rebuilds a fresh tree. Mirrors Python's `_stack`
        // emptying on outer-scope exit.
        if self.frames.is_empty() {
            self.root = None;
        }
    }

    fn emit_child(&mut self, node: Map<String, Value>) {
        if self.frames.is_empty() {
            return;
        }
        let parent = self.current_scope_mut();
        let children = parent
            .get_mut("children")
            .and_then(Value::as_array_mut)
            .expect("scope node missing children array");
        children.push(Value::Object(node));
    }

    pub fn debug(&mut self, tmpl: &str, args: Map<String, Value>) {
        let mut node = Map::new();
        node.insert(TYPE_KEY.to_string(), Value::String("msg".to_string()));
        node.insert("tmpl".to_string(), Value::String(tmpl.to_string()));
        node.insert("args".to_string(), Value::Object(args));
        self.emit_child(node);
    }

    pub fn vis(&mut self, name: &str, value: &Dump) {
        if self.frames.is_empty() {
            return;
        }
        // Split-borrow: dumper.dump needs `&mut Vec<Value>` (the children
        // array of the current scope) AND `&mut Dumper`, both off `self`.
        // Walk to the children array via raw indexing into root + frames
        // so the borrow on `self.dumper` is independent.
        let root = self.root.as_mut().expect("scope active but root is None");
        let mut node: &mut Map<String, Value> = root;
        for f in &self.frames[1..] {
            let idx = f.parent_child_idx.expect("non-root frame must have idx");
            let children = node
                .get_mut("children")
                .and_then(Value::as_array_mut)
                .expect("scope node missing children array");
            node = children
                .get_mut(idx)
                .and_then(Value::as_object_mut)
                .expect("child at idx must be a scope object");
        }
        let children = node
            .get_mut("children")
            .and_then(Value::as_array_mut)
            .expect("scope node missing children array");
        self.dumper.dump(children, name, value);
    }

    pub fn flush(&mut self) {
        let prev_us = self.last_flush_us;
        let root = self
            .root
            .as_mut()
            .expect("flush() called outside any Scope");
        root.insert("prev_flush_us".to_string(), Value::Number(prev_us.into()));
        let t0 = Instant::now();
        let payload = serde_json::to_string(root).expect("root scope must serialise");
        println!("{payload}");
        self.last_flush_us = t0.elapsed().as_micros() as u64;
    }
}

impl Default for DebugCtx {
    fn default() -> Self {
        Self::new()
    }
}

/// Process-global debug context. Lazily initialised on first access. Each
/// cdylib has its own copy of `CTX`, and the engine serialises bot calls
/// per turn, so the unsynchronised access is safe on the single-threaded
/// hot path.
static mut CTX: Option<DebugCtx> = None;

#[allow(static_mut_refs)]
fn ctx() -> &'static mut DebugCtx {
    unsafe { CTX.get_or_insert_with(DebugCtx::new) }
}

/// Tree-internal scope guard. Constructed via `Scope::new` (untimed) or
/// `Scope::new_timed` (records `us` elapsed on drop). The constructor pushes
/// a `scope` node onto the stack and attaches it to its parent; `Drop` pops
/// the stack and records elapsed microseconds if timed.
///
/// pyrust will translate `let _g = Scope::new("foo");` blocks back to Python
/// `with Scope("foo"):` blocks (RAII guard ↔ context manager).
pub struct Scope {
    // No fields needed — all state lives in the global context.
    _private: (),
}

impl Scope {
    /// Push an untimed scope onto the stack. The returned guard pops on drop.
    #[must_use]
    pub fn new(label: &str) -> Self {
        if DEBUG_LOG {
            ctx().push_scope(label, false);
        }
        Self { _private: () }
    }

    /// Push a timed scope; on drop, records `us` (microseconds elapsed).
    /// Mirrors Python `Scope(label, time=True)`.
    #[must_use]
    pub fn new_timed(label: &str) -> Self {
        if DEBUG_LOG {
            ctx().push_scope(label, true);
        }
        Self { _private: () }
    }
}

impl Drop for Scope {
    fn drop(&mut self) {
        if DEBUG_LOG {
            ctx().pop_scope();
        }
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
    ct.draw_indicator_dot(pos, r, g, b).unwrap();
}

/// Wrapper over `Controller::draw_indicator_line`.
pub fn line(ct: &mut Controller<'_>, pos_a: Position, pos_b: Position, r: i32, g: i32, b: i32) {
    if !DEBUG_LOG {
        return;
    }
    ct.draw_indicator_line(pos_a, pos_b, r, g, b).unwrap();
}
