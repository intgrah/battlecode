//! Walk to a transport tile cardinally adjacent to a visible enemy
//! turret (Gunner / Sentinel / Launcher / Breach) and destroy it,
//! starving the turret of resources. The transport can be friendly
//! (parasitic chain leaking our resources) or enemy (their own supply).
//! Friendly Harvesters are explicitly excluded — never destroy our own
//! production buildings even if cardinal to an enemy turret.

use cambc::{Controller, ControllerApi, EntityType, Position};

use crate::builder::Builder;
use crate::builder::helpers::{make_move, try_attack};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR4;
use crate::util::metrics::manhattan;

/// Builder fire can't damage `ArmouredConveyor` (immune to bot attacks),
/// so excluded — targeting one would waste the defender's turn standing
/// on an untouchable feeder.
#[must_use]
const fn _is_transport(kind: Option<EntityType>) -> bool {
    matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::Splitter | EntityType::Bridge)
    )
}

#[must_use]
const fn _is_enemy_turret(kind: Option<EntityType>) -> bool {
    matches!(
        kind,
        Some(
            EntityType::Gunner
                | EntityType::Sentinel
                | EntityType::Launcher
                | EntityType::Breach
        )
    )
}

pub fn kill_feeder(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let my_pos = self_.state.my_pos;
    let my_team = self_.my_team;

    // Inline scan: find enemy turrets in nearby_buildings (v1000 doesn't
    // keep an `enemy_turrets` list field; this is cheap enough since
    // defense tasks run only on the Defender role).
    let mut enemy_turrets: Vec<Position> = pyrust::vec::new!();
    for &pos in &pyrust::clone!(self_.nearby_buildings) {
        if !_is_enemy_turret(self_.kind_at(pos)) {
            continue;
        }
        if self_.team_at(pos) == Some(my_team) {
            continue;
        }
        pyrust::vec::push!(enemy_turrets, pos);
    }
    if pyrust::vec::is_empty!(enemy_turrets) {
        return Some(TaskRejected::new("no enemy turrets in vision"));
    }

    let mut closest: Option<Position> = None;
    let mut closest_d: i32 = i32::MAX;
    for t in &enemy_turrets {
        for d in DIR4 {
            let c = t.add(d);
            if !self_.in_bounds(c) {
                continue;
            }
            if !_is_transport(self_.kind_at(c)) {
                continue;
            }
            // Defensive: never destroy our own Harvesters even if cardinal
            // to an enemy turret. (Harvester isn't in `_is_transport` so
            // this is belt-and-braces.)
            if self_.kind_at(c) == Some(EntityType::Harvester)
                && self_.team_at(c) == Some(my_team)
            {
                continue;
            }
            let dist = manhattan(my_pos, c);
            if dist < closest_d {
                closest_d = dist;
                closest = Some(c);
            }
        }
    }

    let Some(target) = closest else {
        return Some(TaskRejected::new(
            "no destroyable feeder cardinal of any enemy turret",
        ));
    };

    if my_pos == target {
        // Friendly transport: free destroy. Enemy transport: fire (2 Ti).
        if self_.team_at(target) == Some(my_team) {
            if pyrust::unwrap!(ct.can_destroy(target)) {
                pyrust::unwrap!(ct.destroy(target));
                self_.apply_local_destroy(target);
            }
        } else {
            try_attack(ct, target);
        }
        return None;
    }

    make_move(self_, ct, target);
    None
}
