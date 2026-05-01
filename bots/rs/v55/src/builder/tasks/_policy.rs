//! Translation of `bots/intgrah/v54.7.9/builder/tasks/_policy.py`.
//!
//! Tree-structured policy primitives.
//!
//! A `Policy` is either a `TaskGroup` (an internal node with named children
//! and an optional gate) or a leaf function `LeafFn` of shape
//! `(Builder, Controller) -> TaskResult`. Leaves either complete the turn
//! (return `Ok(())`) or return `Err(TaskRejected)` to defer to the next
//! sibling.
//!
//! Traversal: depth-first, first-success-wins. `run_policy` returns true
//! iff some leaf in the subtree completed without rejecting; false iff
//! every leaf rejected (or the group's gate denied the subtree). The
//! caller's parent group treats a false return the same way it treats a
//! leaf rejection — move on to the next sibling.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
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
    match policy {
        Policy::Group(group) => {
            if let Some(gate) = group.gate
                && !gate(self_, ct)
            {
                let mut args = Map::new();
                args.insert(
                    "name".to_string(),
                    serde_json::Value::String(group.name.to_string()),
                );
                log("{name}: gated off", args);
                return false;
            }
            let _scope = Scope::new_timed(group.name);
            for child in group.children {
                if run_policy(self_, ct, child) {
                    return true;
                }
            }
            false
        }
        Policy::Leaf { name, fn_ } => {
            let scope_label = format!("task={name}");
            let _scope = Scope::new_timed(&scope_label);
            match fn_(self_, ct) {
                Ok(()) => true,
                Err(rej) => {
                    let mut args = Map::new();
                    args.insert(
                        "name".to_string(),
                        serde_json::Value::String((*name).to_string()),
                    );
                    args.insert(
                        "reason".to_string(),
                        serde_json::Value::String(rej.reason.clone()),
                    );
                    log("{name}: {reason}", args);
                    false
                }
            }
        }
    }
}
