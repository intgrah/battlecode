//! Translation of `bots/intgrah/v54.7.9/builder/tasks/rejected.py`.
//!
//! Failure model is Option-shape, not Result: `None` = task fired,
//! `Some(TaskRejected)` = task rejected. Dodges Python exceptions
//! (which would be non-deterministic if any unrelated exception
//! propagated mid-turn) and matches the pyrust DSL `try_!` macro for
//! early propagation.

#[derive(Clone, Debug)]
pub struct TaskRejected {
    pub reason: String,
}

impl TaskRejected {
    /// Build a rejection from a static reason string.
    #[must_use]
    pub fn new(reason: &str) -> Self {
        Self {
            reason: pyrust::to_string!(reason),
        }
    }

    /// Build a rejection from an owned reason string (for templated reasons).
    #[must_use]
    pub const fn from_string(reason: String) -> Self {
        Self { reason }
    }
}

impl core::fmt::Display for TaskRejected {
    #[pyrust::inline]
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str(&self.reason)
    }
}

/// Result type used by every task leaf: `None` = task fired,
/// `Some(TaskRejected)` = move on to the next sibling.
pub type TaskResult = Option<TaskRejected>;
