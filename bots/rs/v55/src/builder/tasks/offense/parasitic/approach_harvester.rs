//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/parasitic/approach_harvester.py`.
//!
//! Walk toward a vulnerable enemy harvester so a follow-up turn can fire
//! on it. Picks a cardinal-of-target destination via `pick_attack_destination`
//! (prefers no-healer, low-HP, close), optionally stages a launcher en route,
//! and walks via the launcher / cached `offense_target` / direct-to-target
//! cascade.

use cambc::{BuildExtra, Controller, ControllerApi, EntityType, GameConstants};

use crate::builder::Builder;
use crate::builder::helpers::{make_move, try_attack, try_place};
use crate::builder::tasks::offense::helpers::{
    buildable, is_allied_transport, open_tiles, pick_attack_destination, pick_harvester_target,
    should_attack, vulnerable_harvesters, without_allied_transport,
};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR4;
use crate::util::metrics::closest;

pub fn approach_harvester(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let vulnerable = vulnerable_harvesters(self_);
    if vulnerable.is_empty() {
        return Some(TaskRejected::new(
            "no vulnerable enemy harvesters in vision",
        ));
    }
    let target = pick_harvester_target(self_, &vulnerable);

    let on_friendly_conveyor = is_allied_transport(self_, self_.my_pos);
    if self_.my_pos.distance_squared(target) == 1 && !on_friendly_conveyor {
        return Some(TaskRejected::new(
            "already adjacent to target (fire/turret task handles this)",
        ));
    }

    let mut destination = pick_attack_destination(self_, target, false);
    if pyrust::is_none!(destination) {
        let cardinal_positions: Vec<_> =
            pyrust::collect!(pyrust::map!(pyrust::iter!(DIR4), |&d| target.add(d)));
        let opens = open_tiles(self_, &cardinal_positions);
        let filtered = without_allied_transport(self_, &opens);
        destination = closest(self_.my_pos, filtered);
        if pyrust::is_none!(destination) {
            return Some(TaskRejected::new("no walkable cardinal of target"));
        }
    }
    let destination = pyrust::unwrap!(destination);

    let neighbours_8 = pyrust::clone!(self_.neighbours_8);
    let buildable_8 = buildable(self_, &neighbours_8);
    let launcher_location = closest(destination, buildable_8);

    let adjacent_launchers: Vec<_> = pyrust::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(self_.neighbours_8)),
        |&p| self_.kind_at(p) == Some(EntityType::Launcher)
    ));
    let best_adjacent_launcher = closest(destination, adjacent_launchers);

    if self_.my_pos.distance_squared(destination) <= 2 || self_.my_pos.distance_squared(target) < 9
    {
        make_move(self_, ct, destination);
    } else if let Some(bal) = best_adjacent_launcher
        && self_.is_walkable(destination)
        && bal.distance_squared(destination) <= GameConstants::LAUNCHER_VISION_RADIUS_SQ
    {
        // wait
    } else if let Some(loc) = launcher_location
        && pyrust::is_none!(best_adjacent_launcher)
        && self_.is_walkable(destination)
        && loc.distance_squared(destination) <= GameConstants::LAUNCHER_VISION_RADIUS_SQ
        && try_place(self_, ct, EntityType::Launcher, loc, BuildExtra::None, true)
    {
        self_.offense_launcher = Some(loc);
    } else if let Some(ol) = self_.offense_launcher
        && ol.distance_squared(self_.my_pos) < 25
    {
        make_move(self_, ct, ol);
    } else if let Some(ot) = self_.offense_target
        && ot.distance_squared(self_.my_pos) < 20
    {
        make_move(self_, ct, ot);
    } else {
        make_move(self_, ct, target);
    }

    let cur_pos = pyrust::unwrap!(ct.get_position(None));
    if cur_pos.distance_squared(target) == 1
        && self_.is_enemy_building(cur_pos)
        && should_attack(self_, cur_pos)
    {
        try_attack(ct, cur_pos);
    }
    None
}
