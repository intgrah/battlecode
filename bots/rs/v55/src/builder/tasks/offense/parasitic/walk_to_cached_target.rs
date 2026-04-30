//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/parasitic/walk_to_cached_target.py`.
//!
//! Walk back toward a cached `offense_target` when no fresh harvester is
//! visible. Used when a builder commits to a target, walks out of vision of
//! it, then needs to keep walking back. Routes via `offense_launcher` if
//! one is set and the target is far; else direct.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::builder::tasks::offense::helpers::vulnerable_harvesters;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::building::Building;

pub fn walk_to_cached_target(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !vulnerable_harvesters(self_).is_empty() {
        return Err(TaskRejected::new(
            "a vulnerable harvester is in vision — approach it first",
        ));
    }
    let Some(offense_target) = self_.offense_target else {
        return Err(TaskRejected::new("offense_target is None"));
    };

    if let Some(ol) = self_.offense_launcher {
        let rl = self_.get_building(ol);
        if let Some(Building::Launcher { team }) = rl
            && team == self_.my_team
            && self_.my_pos.distance_squared(offense_target) > 8
        {
            make_move(self_, ct, ol);
            return Ok(());
        }
    }
    make_move(self_, ct, offense_target);
    Ok(())
}
