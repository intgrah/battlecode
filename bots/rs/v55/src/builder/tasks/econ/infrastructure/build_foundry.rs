//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/build_foundry.py`.
//!
//! Replace a designated Ti conveyor (`foundry_target`) with a foundry
//! once its Ax feed is established. Gated on round >= FOUNDRY_ROUND_GATE.
//! Checks the target is still a friendly pure conveyor, that an Ax cardinal
//! feeds it, and that we can afford the build; walks adjacent and destroys-
//! then-builds the foundry.

use cambc::{BuildExtra, Controller, ControllerApi, EntityType, Environment};

use crate::builder::Builder;
use crate::builder::helpers::{ax_feeds_target, can_afford, make_move, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::debug::debug as log;
use serde_json::Map;

/// First foundry >= turn 500.
const FOUNDRY_ROUND_GATE: i32 = 500;

pub fn build_foundry(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if self_.round < FOUNDRY_ROUND_GATE {
        return Some(TaskRejected::from_string(format!(
            "round {} < gate {}",
            self_.round, FOUNDRY_ROUND_GATE
        )));
    }
    let Some(target) = self_.foundry_target else {
        return Some(TaskRejected::new("foundry_target is None"));
    };
    let kind = self_.kind_at(target);
    let team = self_.team_at(target);
    let is_conveyor = matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
    );
    if !is_conveyor {
        return Some(TaskRejected::from_string(format!(
            "{:?}: got {:?}, expected Ti conveyor",
            target, kind
        )));
    }
    if team != Some(self_.my_team) {
        return Some(TaskRejected::from_string(format!(
            "{:?}: conveyor held by enemy team",
            target
        )));
    }
    if self_.get_env(target) != Some(Environment::Empty) {
        return Some(TaskRejected::from_string(format!(
            "{:?}: terrain is {:?}, not EMPTY",
            target,
            self_.get_env(target)
        )));
    }
    if !ax_feeds_target(self_, target) {
        return Some(TaskRejected::from_string(format!(
            "ax chain hasn't reached {:?}",
            target
        )));
    }

    let dist_sq = self_.my_pos.distance_squared(target);
    if !can_afford(self_, EntityType::Foundry) {
        if dist_sq <= 2 {
            log(
                &format!("build_foundry: holding {:?} until affordable", target),
                Map::new(),
            );
            return None;
        }
        log(
            &format!(
                "build_foundry: walking toward {:?}, can't afford yet",
                target
            ),
            Map::new(),
        );
        make_move(self_, ct, target);
        return None;
    }

    if self_.my_pos == target {
        let dirs = self_.dir_neighbours_4.clone();
        let mut moved = false;
        for (d, _npos) in dirs {
            if ct.can_move(d).unwrap() {
                ct.move_(d).unwrap();
                moved = true;
                break;
            }
        }
        if !moved {
            log(
                &format!(
                    "build_foundry: stuck on {:?}, cannot step off this turn",
                    target
                ),
                Map::new(),
            );
            return None;
        }
    }

    if let Some(&uid) = self_.all_bots.get(&target)
        && uid != self_.my_id
    {
        log(
            &format!(
                "build_foundry: {:?} occupied by friendly bot, holding",
                target
            ),
            Map::new(),
        );
        return None;
    }

    if self_.my_pos.distance_squared(target) <= 2
        && try_place(
            self_,
            ct,
            EntityType::Foundry,
            target,
            BuildExtra::None,
            true,
        )
    {
        log(
            &format!("build_foundry: PLACED at {:?}", target),
            Map::new(),
        );
        return None;
    }

    log(
        &format!("build_foundry: out of range of {:?}, walking", target),
        Map::new(),
    );
    make_move(self_, ct, target);
    None
}
