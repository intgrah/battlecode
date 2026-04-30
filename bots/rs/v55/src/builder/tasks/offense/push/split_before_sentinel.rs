//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/split_before_sentinel.py`.
//!
//! Upgrade the conveyor immediately upstream of a friendly sentinel into
//! a splitter, forking the offensive chain into three outputs.

use cambc::{BuildExtra, Controller, Direction, EntityType, Position};

use crate::builder::Builder;
use crate::builder::helpers::{can_afford, make_move, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::building::Building;
use crate::util::constants::MAX_WIDTH;
use crate::util::directions::{DIR4, delta_to_dir};

/// If `pos` has exactly one cardinal friendly feeder, return the
/// DIR4 direction `d` such that `pos - d.delta() == feeder_pos`. This
/// is the splitter's forward direction when placed at `pos`: input
/// side = `pos + d.opposite()` = feeder_pos.
fn feeder_delta(self_: &Builder, pos: Position) -> Option<Direction> {
    let feeders = &self_.in_edges[pos.y as usize * MAX_WIDTH + pos.x as usize];
    if feeders.len() != 1 {
        return None;
    }
    let feeder = feeders[0];
    let dx = pos.x - feeder.x;
    let dy = pos.y - feeder.y;
    let d = delta_to_dir(dx, dy)?;
    if !DIR4.contains(&d) {
        return None;
    }
    Some(d)
}

pub fn split_before_sentinel(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !can_afford(self_, EntityType::Splitter) {
        return Err(TaskRejected::new("cannot afford SPLITTER"));
    }

    let mut best_split: Option<Position> = None;
    let mut best_dir: Option<Direction> = None;
    let mut best_dist = 1 << 30;
    for &sent_pos in &self_.nearby_buildings {
        let b = self_.get_building(sent_pos);
        if !matches!(b, Some(Building::Sentinel { team, .. }) if team == self_.my_team) {
            continue;
        }
        let feeders = self_.in_edges[sent_pos.y as usize * MAX_WIDTH + sent_pos.x as usize].clone();
        for split_pos in feeders {
            let sb = self_.get_building(split_pos);
            if !matches!(sb, Some(Building::Conveyor { team, .. }) if team == self_.my_team) {
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
            let d = self_.my_pos.distance_squared(split_pos);
            if d < best_dist {
                best_dist = d;
                best_split = Some(split_pos);
                best_dir = Some(sd);
            }
        }
    }

    let (Some(best_split), Some(best_dir)) = (best_split, best_dir) else {
        return Err(TaskRejected::new(
            "no friendly sentinel with a splittable upstream conveyor",
        ));
    };

    if self_.my_pos.distance_squared(best_split) <= 2 {
        try_place(
            self_,
            ct,
            EntityType::Splitter,
            best_split,
            BuildExtra::Direction(best_dir),
            true,
        );
        return Ok(());
    }
    make_move(self_, ct, best_split);
    Ok(())
}
