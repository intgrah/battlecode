//! Translation of `bots/intgrah/v54.7.9/builder/tasks/`.
//!
//! Tree-structured task policy framework.
//!
//! Each role's POLICIES entry is a `TaskGroup`: a tree where leaves are
//! `(self, ct) -> TaskResult` functions and internal nodes group siblings under
//! a common name (and optional gate). The runner does depth-first
//! traversal; the first leaf that doesn't reject claims the turn. See
//! `_policy.rs` for `TaskGroup` and `run_policy`.

pub mod _policy;
pub mod defense;
pub mod econ;
pub mod offense;
pub mod rejected;
pub mod shared;

use crate::builder::role::Role;
use crate::builder::tasks::_policy::Policy;
use crate::builder::tasks::defense::DEFENSE_GROUP;
use crate::builder::tasks::econ::ECON_GROUP;
use crate::builder::tasks::offense::{PARASITIC_ROLE_GROUP, PUSH_ROLE_GROUP};

/// Resolve a role to its top-level policy tree.
#[must_use]
pub fn policy_for_role(role: Role) -> &'static Policy {
    match role {
        Role::Push => &PUSH_ROLE_GROUP,
        Role::Parasitic => &PARASITIC_ROLE_GROUP,
        Role::Econ | Role::PermEcon => &ECON_GROUP,
        Role::Defense | Role::PermDefense => &DEFENSE_GROUP,
    }
}
