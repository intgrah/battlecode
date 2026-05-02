//! Translation of `bots/intgrah/v54.7.9/builder/tasks/_policy.py`.
//!
//! Tree-structured policy primitives.
//!
//! A `Policy` is either a `TaskGroup` (an internal node with named children
//! and an optional gate) or a leaf function `LeafFn` of shape
//! `(Builder, Controller) -> TaskResult`. Leaves either complete the turn
//! (return `None`) or return `Err(TaskRejected)` to defer to the next
//! sibling.
//!
//! Traversal: depth-first, first-success-wins. `run_policy` returns true
//! iff some leaf in the subtree completed without rejecting; false iff
//! every leaf rejected (or the group's gate denied the subtree). The
//! caller's parent group treats a false return the same way it treats a
//! leaf rejection — move on to the next sibling.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::tasks::rejected::TaskResult;
use crate::config::DEBUG_LOG;
use crate::util::debug::{Scope, debug as log};

use serde_json::Map;

pub type LeafFn = fn(&mut Builder, &mut Controller<'_>) -> TaskResult;
pub type Gate = fn(&mut Builder, &mut Controller<'_>) -> bool;

/// Internal policy node. `children` is searched in order; `gate`, if set,
/// can short-circuit the entire subtree when its precondition doesn't
/// hold (cheaper than rejecting at every leaf separately).
pub struct TaskGroup {
    pub name: &'static str,
    pub children: &'static [Policy],
    pub gate: Option<Gate>,
}

#[derive(Clone, Copy)]
pub enum Policy {
    Group(&'static TaskGroup),
    Leaf { name: &'static str, fn_: LeafFn },
}

pub fn run_policy(self_: &mut Builder, ct: &mut Controller<'_>, policy: &Policy) -> bool {
    if DEBUG_LOG {
        return _run_policy_debug(self_, ct, policy);
    }
    // Hot path: iterative DFS over the policy tree, eliminating ~50k
    // recursive Python frames per game. Children are pushed in reverse
    // order so the first child is popped first (DFS left-to-right order
    // preserved). A leaf that succeeds (returns None) short-circuits
    // immediately; a gated-off group skips its entire subtree.
    let mut stack: Vec<&Policy> = pyrust::vec::new!();
    pyrust::vec::push!(stack, policy);
    while let Some(p) = pyrust::vec::pop!(stack) {
        match p {
            Policy::Leaf { fn_, .. } => {
                if pyrust::is_none!(fn_(self_, ct)) {
                    return true;
                }
            }
            Policy::Group(group) => {
                if let Some(gate) = group.gate
                    && !gate(self_, ct)
                {
                    continue;
                }
                for child in pyrust::rev!(pyrust::iter!(group.children)) {
                    pyrust::vec::push!(stack, child);
                }
            }
        }
    }
    false
}

/// Debug-only recursive walk: preserves `Scope::new_timed` per group/leaf
/// so the timing tree is visible in logs. Never called when `DEBUG_LOG` is
/// false (compile-time dead code).
fn _run_policy_debug(self_: &mut Builder, ct: &mut Controller<'_>, policy: &Policy) -> bool {
    match policy {
        Policy::Group(group) => {
            if let Some(gate) = group.gate
                && !gate(self_, ct)
            {
                if DEBUG_LOG {
                    let mut args = Map::new();
                    pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("name"),
                    serde_json::Value::String(pyrust::to_string!(group.name))
                    );
                    log("{name}: gated off", args);
                }
                return false;
            }
            let _scope = Scope::new_timed(group.name);
            for child in group.children {
                if _run_policy_debug(self_, ct, child) {
                    return true;
                }
            }
            false
        }
        Policy::Leaf { name, fn_ } => {
            let scope_label = format!("task={name}");
            let _scope = Scope::new_timed(&scope_label);
            match fn_(self_, ct) {
                None => true,
                Some(rej) => {
                    if DEBUG_LOG {
                        let mut args = Map::new();
                        pyrust::dict::insert!(
                        args,
                        pyrust::to_string!("name"),
                        serde_json::Value::String(pyrust::to_string!((*name)))
                        );
                        pyrust::dict::insert!(
                        args,
                        pyrust::to_string!("reason"),
                        serde_json::Value::String(rej.reason)
                        );
                        log("{name}: {reason}", args);
                    }
                    false
                }
            }
        }
    }
}
