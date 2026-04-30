//! Translation of `bots/intgrah/v54.7.9/builder/tasks/rejected.py`.
//!
//! Python uses 72 distinct `TaskRejectedError` subclasses for typed
//! debug rendering. The Rust translation collapses them into a single
//! struct carrying a static reason string — the policy runner only
//! needs to know "task rejected, here's why".

/// A task cannot fire this turn. The `reason` string is rendered to
/// the debug log when a task rejects.
#[derive(Clone, Debug)]
pub struct TaskRejected {
    pub reason: String,
}

impl TaskRejected {
    /// Build a rejection from a static reason string.
    #[must_use]
    pub fn new(reason: &str) -> Self {
        Self {
            reason: reason.to_string(),
        }
    }

    /// Build a rejection from an owned reason string (for templated reasons).
    #[must_use]
    pub fn from_string(reason: String) -> Self {
        Self { reason }
    }
}

impl core::fmt::Display for TaskRejected {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str(&self.reason)
    }
}

/// Result type used by every task leaf: `Ok(())` = task fired,
/// `Err(TaskRejected)` = move on to the next sibling.
pub type TaskResult = Result<(), TaskRejected>;
