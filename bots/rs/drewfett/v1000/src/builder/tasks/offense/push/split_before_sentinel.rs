//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/split_before_sentinel.py`.
//!
//! Upgrade the conveyor immediately upstream of a friendly sentinel into
//! a splitter, forking the offensive chain into three outputs.

use cambc::{BuildExtra, Controller, Direction, EntityType, Position};

use crate::builder::Builder;
use crate::builder::helpers::{can_afford, make_move, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::{DIR4, delta_to_dir};
use crate::util::posint::{dist_sq, idx_of};

/// If `pos` has exactly one cardinal friendly feeder, return the
/// DIR4 direction `d` such that `pos - d.delta() == feeder_pos`. This
/// is the splitter's forward direction when placed at `pos`: input
/// side = `pos + d.opposite()` = `feeder_pos`.
fn feeder_delta(self_: &Builder, pos: Position) -> Option<Direction> {
    let feeders = &self_.in_edges[idx_of(pos) as usize];
    if pyrust::len!(feeders) != 1 {
        return None;
    }
    let feeder = feeders[0];
    let dx = pos.x - feeder.x;
    let dy = pos.y - feeder.y;
    let Some(d) = delta_to_dir(dx, dy) else {
        return None;
    };
    if !pyrust::vec::contains!(DIR4, &d) {
        return None;
    }
    Some(d)
}

pub fn split_before_sentinel(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !can_afford(self_, EntityType::Splitter) {
        return Some(TaskRejected::new("cannot afford SPLITTER"));
    }

    let my_p = idx_of(self_.my_pos);
    let mut best_split: Option<Position> = None;
    let mut best_dir: Option<Direction> = None;
    let mut best_dist = 1 << 30;
    for &sent_pos in &self_.nearby_buildings {
        let pi_sent = idx_of(sent_pos);
        if !(self_.kind_at_p(pi_sent) == Some(EntityType::Sentinel)
            && self_.team_at_p(pi_sent) == Some(self_.my_team))
        {
            continue;
        }
        let feeders = pyrust::clone!(self_.in_edges[pi_sent as usize]);
        for split_pos in feeders {
            let pi_split = idx_of(split_pos);
            if !(self_.kind_at_p(pi_split) == Some(EntityType::Conveyor)
                && self_.team_at_p(pi_split) == Some(self_.my_team))
            {
                continue;
            }
            if let Some(&uid) = self_.all_bots.get(&split_pos)
                && uid != self_.my_id
            {
                continue;
            }
            let sd = feeder_delta(self_, split_pos);
            let Some(sd) = sd else {
                continue;
            };
            let d = dist_sq(my_p, pi_split);
            if d < best_dist {
                best_dist = d;
                best_split = Some(split_pos);
                best_dir = Some(sd);
            }
        }
    }

    let (Some(best_split), Some(best_dir)) = (best_split, best_dir) else {
        return Some(TaskRejected::new(
            "no friendly sentinel with a splittable upstream conveyor",
        ));
    };

    if dist_sq(my_p, idx_of(best_split)) <= 2 {
        try_place(
            self_,
            ct,
            EntityType::Splitter,
            best_split,
            BuildExtra::Direction(best_dir),
            true,
        );
        return None;
    }
    make_move(self_, ct, best_split);
    None
}
