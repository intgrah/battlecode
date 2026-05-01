//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/deny_enemy_ore.py`.
//!
//! Reactively pave a road on a tile cardinal to a spotted enemy ore
//! deposit, denying them a harvester-feeder slot. Tile candidates come from
//! `deny_ore_neighbours` (populated by `update_ore_denial`). One road per
//! turn; rejects if no candidate in vision is buildable right now.

use cambc::{Controller, ControllerApi, Environment};

use crate::builder::Builder;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn deny_enemy_ore(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    for &pos in &self_.nearby_tiles.clone() {
        if self_.deny_ore_neighbours.contains(&pos)
            && self_.get_env(pos) != Some(Environment::Wall)
            && pyrust::is_none!(self_.get_building(pos))
            && pyrust::unwrap!(ct.can_build_road(pos))
        {
            pyrust::unwrap!(ct.build_road(pos));
            return None;
        }
    }
    Some(TaskRejected::new(
        "no in-range tile is a denial candidate right now",
    ))
}
