//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/wander.py`.
//!
//! Walk-away-from-core fallback for ECON / DEFENSE roles. Tries each
//! of the 8 directions in order of decreasing Chebyshev distance from
//! our core, walking only on pre-existing walkable tiles — no road
//! paving (no Ti spend). Rejects if no direction produces a legal move.

use cambc::{Controller, Direction};

use crate::builder::Builder;
use crate::builder::helpers::try_move_dir;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR8;
use crate::util::posint::{DIR8_INT, cheb, idx_of};

pub fn wander(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let my_pos_p = idx_of(self_.my_pos);
    let my_core_p = idx_of(self_.my_core);
    // Build (direction, neg-chebyshev) pairs, sort, then try each direction.
    let mut dir_scores: Vec<(Direction, i32)> = pyrust::vec::new!();
    for i in 0..8usize {
        let d = DIR8[i];
        let di = DIR8_INT[i];
        let score = -cheb(my_pos_p + di, my_core_p);
        pyrust::vec::push!(dir_scores, (d, score));
    }
    pyrust::sort_by_key!(dir_scores, |t| t.1);
    for entry in &dir_scores {
        let d = entry.0;
        if try_move_dir(ct, d) {
            return None;
        }
    }
    Some(TaskRejected::new(
        "no walkable direction available without paving",
    ))
}
