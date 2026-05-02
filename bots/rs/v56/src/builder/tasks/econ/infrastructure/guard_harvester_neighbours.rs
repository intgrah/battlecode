//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/guard_harvester_neighbours.py`.
//!
//! Guard work around our Ti harvesters / claimed-but-unbuilt ore tiles.

use std::collections::HashSet;

use cambc::{Controller, ControllerApi, EntityType, Environment, Position};

use crate::builder::Builder;
use crate::builder::harvest::{needs_harvester_guard, place_harvester_guard};
use crate::builder::helpers::{can_afford, harvester_feed_cardinal, harvester_io_cardinals};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR4;
use crate::util::metrics::chebyshev;
use crate::util::symmetry::ALL as SYM_ALL;

/// Buffer turns subtracted from the closest possible enemy-arrival
/// chebyshev distance. Until that turn, defer proactive harvester
/// guarding — the placements often get overwritten in the early game.
#[pyrust::inline]
const GUARD_BUFFER: i32 = 4;

pub fn guard_harvester_neighbours(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    // Gate: don't proactively guard harvesters until the earliest possible
    // enemy arrival is GUARD_BUFFER turns away.
    let w = self_.state.width;
    let h = self_.state.height;
    let my_core = self_.my_core;
    let mut min_d: i32 = i32::MAX;
    for sym in SYM_ALL {
        let en = sym.action(my_core, w, h);
        let d = chebyshev(my_core, en);
        if d < min_d {
            min_d = d;
        }
    }
    let gate = min_d - GUARD_BUFFER;
    if self_.state.round < gate {
        return Some(TaskRejected::from_string(format!(
            "deferred: round {} < guard gate {} (min enemy arrival {})",
            self_.state.round, gate, min_d
        )));
    }

    let mut targets: Vec<Position> = pyrust::vec::new!();
    for &pos in &self_.nearby_tiles {
        if self_.kind_at(pos) == Some(EntityType::Harvester)
            && self_.team_at(pos) == Some(self_.my_team)
            && self_.get_env(pos) == Some(Environment::OreTitanium)
        {
            pyrust::vec::push!(targets, pos);
        }
    }
    // Ax ore is excluded: raw Ax can't be parasitised for offence, so
    // leaking some to a placed enemy conveyor isn't worth the Ti spent
    // on inward conveyors / barriers around the Ax harvester.
    let my_pos = self_.my_pos;
    if let Some(tgt) = self_.ore_target
        && my_pos == tgt
        && !pyrust::vec::contains!(targets, &tgt)
    {
        pyrust::vec::push!(targets, tgt);
    }

    if pyrust::vec::is_empty!(targets) {
        return Some(TaskRejected::new(
            "nothing to guard around any visible harvester / claim",
        ));
    }

    let near: HashSet<Position> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(self_.nearby_tiles)));
    let affords_road = can_afford(self_, EntityType::Road);
    let affords_guard = can_afford(self_, EntityType::Conveyor);

    let mut no_guard: HashSet<Position> = pyrust::set::new!();
    for &target in &targets {
        for p in harvester_io_cardinals(self_, target) {
            pyrust::set::add!(no_guard, p);
        }
    }

    for target in &targets {
        let target = *target;
        let feed = harvester_feed_cardinal(self_, target);
        let Some(feed) = feed else {
            continue;
        };

        // Don't try to pave under ourselves: that creates a livelock
        // with claim_ore (we pave, claim_ore destroys to walk on, we
        // pave again, …).
        if feed != self_.my_pos
            && affords_road
            && pyrust::vec::contains!(near, &feed)
            && self_.get_cost(feed) > 1
            && pyrust::unwrap!(ct.can_build_road(feed))
        {
            pyrust::unwrap!(ct.build_road(feed));
            return None;
        }

        if !affords_guard {
            continue;
        }
        for d in DIR4 {
            let pos = target.add(d);
            if !pyrust::vec::contains!(near, &pos) {
                continue;
            }
            if pyrust::vec::contains!(no_guard, &pos) {
                continue;
            }
            if !needs_harvester_guard(self_, pos, target, &no_guard) {
                continue;
            }
            if place_harvester_guard(self_, ct, pos, target) {
                return None;
            }
        }
    }
    Some(TaskRejected::new(
        "nothing to guard around any visible harvester / claim",
    ))
}
