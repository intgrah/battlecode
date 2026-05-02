//! Walk onto an unharvested ore tile to claim it. Highest-priority of
//! the three ore-claim phases. Single responsibility: navigate (with
//! contest-clearing) onto `ore_target` or `ax_ore_target`. No conveyor
//! placement, no harvester placement.

use cambc::{Controller, ControllerApi, Position};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::harvest::{find_contest_target, walk_to_ore_claim};
use crate::builder::helpers::ore_available;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::debug::debug as log;
use crate::util::directions::delta_to_dir;
use crate::util::visualiser::auto_wrap_position;

const fn resolve_target(self_: &Builder) -> Option<Position> {
    if let Some(t) = self_.ore_target {
        return Some(t);
    }
    if let Some(t) = self_.ax_ore_target
        && pyrust::is_some!(self_.ax_sink)
    {
        return Some(t);
    }
    None
}

pub fn claim_ore(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some(target) = resolve_target(self_) else {
        return Some(TaskRejected::new("no ore_target / ax_ore_target to claim"));
    };
    if !ore_available(self_, target) {
        return Some(TaskRejected::from_string(format!(
            "ore {target:?} no longer available"
        )));
    }
    if self_.my_pos == target {
        // Pre-guard contest clearing. Standing on the ore, an enemy
        // Road/Conveyor/Splitter/Bridge on a cardinal would survive
        // guard placement (is_guarded_cardinal lets enemy roads
        // through, place_harvester_guard.can_destroy returns false
        // for enemy team) and the harvester goes down exposed.
        //
        // Builders fire AT THEIR OWN TILE — to break the enemy
        // structure we have to step *off* the ore onto it first.
        // Once we're on the contest tile, walk_to_ore_claim (run by
        // claim_ore on the next turn, since my_pos != target then)
        // detects my_pos == contest_pos and fires until destroyed,
        // then walks us back onto the ore.
        if let Some(contest_pos) = find_contest_target(self_, target, self_.my_team) {
            let dx = contest_pos.x - self_.my_pos.x;
            let dy = contest_pos.y - self_.my_pos.y;
            if let Some(d) = delta_to_dir(dx, dy)
                && pyrust::unwrap!(ct.can_move(d))
            {
                let mut args = Map::new();
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("contest"),
                    auto_wrap_position(contest_pos)
                );
                pyrust::dict::insert!(args, pyrust::to_string!("ore"), auto_wrap_position(target));
                log(
                    "claim_ore: on-ore CONTEST → step off {ore} onto enemy {contest}",
                    args,
                );
                pyrust::unwrap!(ct.move_(d));
                return None;
            }
            // Can't move yet (cooldown). Wait this turn; same code
            // re-fires next turn.
            return None;
        }
        return Some(TaskRejected::from_string(format!(
            "already standing on ore {target:?}"
        )));
    }
    if !walk_to_ore_claim(self_, ct, target) {
        return Some(TaskRejected::from_string(format!(
            "could not progress toward ore {target:?}"
        )));
    }
    None
}
