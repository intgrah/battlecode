//! Launcher swarm: place launchers diagonally adjacent to ISOLATED
//! enemy harvesters (no other enemy harvester within `ISOLATION_R²`).
//!
//! Strategy: an isolated harvester's defender bot sees only one threat
//! (us) and one resource (the harvester). They can't easily react with
//! sentinels because that requires building a chain — a single launcher
//! we placed will throw any defender bot away before they can dig in.
//!
//! Placement pattern (diagonal, not cardinal):
//! ```text
//!   L . .
//!   . H .
//!   . . L
//! ```
//! Diagonal because cardinal cardinals would be the harvester's defensive
//! ring and they'd react. Diagonals look like a road-pave intent and
//! most teams don't react.

use cambc::{BuildExtra, Controller, ControllerApi, EntityType, Position};

use crate::builder::Builder;
use crate::builder::helpers::{can_afford, make_move, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::{DIR4, DIR8};
use crate::util::metrics::chebyshev;

/// Other enemy harvester within this Chebyshev distance disqualifies a
/// candidate as "isolated" — defenders from that other harvester would
/// react to our launcher.
const ISOLATION_R: i32 = 5;

/// Don't double-place: skip if a friendly launcher is within this many
/// tiles (Chebyshev) of the candidate diagonal.
const LAUNCHER_SPACING: i32 = 2;

/// True iff `target` is an enemy harvester with no OTHER enemy harvester
/// within `ISOLATION_R`.
fn is_isolated_enemy_harvester(self_: &Builder, target: Position) -> bool {
    for &other in &self_.nearby_buildings {
        if other == target {
            continue;
        }
        if self_.kind_at(other) != Some(EntityType::Harvester) {
            continue;
        }
        if self_.team_at(other) == Some(self_.my_team) {
            continue;
        }
        if chebyshev(other, target) <= ISOLATION_R {
            return false;
        }
    }
    true
}

/// True iff `pos` is buildable terrain we can place a launcher on.
fn buildable_for_launcher(self_: &Builder, pos: Position) -> bool {
    if !self_.in_bounds(pos) {
        return false;
    }
    if !self_.is_buildable(pos) {
        return false;
    }
    if self_.kind_at(pos).is_some() {
        return false;
    }
    // Don't place on a tile a friendly bot occupies.
    !pyrust::dict::contains!(self_.state.all_bots, &pos)
}

/// Returns true iff a friendly launcher already covers this area.
fn launcher_already_nearby(self_: &Builder, pos: Position) -> bool {
    for &other in &self_.nearby_buildings {
        if self_.kind_at(other) != Some(EntityType::Launcher) {
            continue;
        }
        if self_.team_at(other) != Some(self_.my_team) {
            continue;
        }
        if chebyshev(other, pos) <= LAUNCHER_SPACING {
            return true;
        }
    }
    false
}

/// Pick the diagonal-of-target spot closest to my_pos that is buildable
/// and not too close to an existing friendly launcher.
fn pick_diagonal_spot(self_: &Builder, target: Position) -> Option<Position> {
    let my_pos = self_.state.my_pos;
    let mut best: Option<Position> = None;
    let mut best_d: i32 = i32::MAX;
    for d in DIR8 {
        // Skip cardinals — those are guard-ring spots the enemy will
        // notice and react to.
        if pyrust::vec::contains!(DIR4, &d) {
            continue;
        }
        let p = target.add(d);
        if !buildable_for_launcher(self_, p) {
            continue;
        }
        if launcher_already_nearby(self_, p) {
            continue;
        }
        let dist = my_pos.distance_squared(p);
        if dist < best_d {
            best_d = dist;
            best = Some(p);
        }
    }
    best
}

pub fn launcher_swarm(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !can_afford(self_, EntityType::Launcher) {
        return Some(TaskRejected::new("cannot afford LAUNCHER"));
    }

    // Find isolated enemy harvesters, closest first.
    let my_pos = self_.state.my_pos;
    let mut targets: Vec<Position> = pyrust::vec::new!();
    for &pos in &pyrust::clone!(self_.nearby_buildings) {
        if self_.kind_at(pos) != Some(EntityType::Harvester) {
            continue;
        }
        if self_.team_at(pos) == Some(self_.my_team) {
            continue;
        }
        if !is_isolated_enemy_harvester(self_, pos) {
            continue;
        }
        pyrust::vec::push!(targets, pos);
    }
    if pyrust::vec::is_empty!(targets) {
        return Some(TaskRejected::new(
            "no isolated enemy harvester in vision",
        ));
    }
    pyrust::sort_by_key!(targets, |t| my_pos.distance_squared(*t));

    for target in &targets {
        let target = *target;
        let Some(spot) = pick_diagonal_spot(self_, target) else {
            continue;
        };
        // Walk to within action range of the spot.
        if my_pos.distance_squared(spot) > 2 {
            make_move(self_, ct, spot);
            return None;
        }
        if try_place(self_, ct, EntityType::Launcher, spot, BuildExtra::None, true) {
            return None;
        }
    }
    Some(TaskRejected::new(
        "no diagonal-of-isolated-harvester slot available",
    ))
}
