//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/guard_harvester_neighbours.py`.
//!
//! Guard work around our Ti harvesters / claimed-but-unbuilt ore tiles.

use cambc::{Controller, ControllerApi, EntityType, Environment, Position};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::harvest::{needs_harvester_guard, place_harvester_guard};
use crate::builder::helpers::{can_afford, harvester_feed_cardinal, harvester_io_cardinals};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::config::DEBUG_LOG;
use crate::util::debug::debug as log;
use crate::util::directions::DIR4_DELTA;
use crate::util::metrics::chebyshev;
use crate::util::posint::idx_of;
use crate::util::visualiser::auto_wrap_position;

/// Buffer turns subtracted from the closest possible enemy-arrival
/// chebyshev distance. Until that turn, defer proactive harvester
/// guarding — the placements often get overwritten in the early game.
#[pyrust::inline]
const GUARD_BUFFER: i32 = 4;

pub fn guard_harvester_neighbours(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    // Gate: don't proactively guard harvesters until the earliest possible
    // enemy arrival is GUARD_BUFFER turns away.
    {
        let mut min_d: i32 = i32::MAX;
        for sym in pyrust::copied!(pyrust::iter!(self_.state.symmetry_candidates)) {
            let en = sym.action(self_.my_core, self_.state.width, self_.state.height);
            let d = chebyshev(self_.my_core, en);
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
    }

    // Hoisted hot-loop refs: avoid LOAD_ATTR per iteration in Python.
    let my_team = self_.state.my_team;
    let ek = &self_.building_kind;
    let et = &self_.building_team;
    let env = &self_.env;
    let w = self_.state.width;
    let h = self_.state.height;
    let mut targets: Vec<Position> = pyrust::vec::new!();
    for &pos in &self_.state.nearby_tiles {
        let i = idx_of(pos) as usize;
        if ek[i] == Some(EntityType::Harvester)
            && et[i] == Some(my_team)
            && env[i] == Some(Environment::OreTitanium)
        {
            pyrust::vec::push!(targets, pos);
        }
    }
    let my_pos = self_.state.my_pos;
    for tgt_opt in [self_.ore_target, self_.ax_ore_target] {
        if let Some(tgt) = tgt_opt
            && my_pos == tgt
            && !pyrust::vec::contains!(targets, &tgt)
        {
            pyrust::vec::push!(targets, tgt);
        }
    }

    if pyrust::vec::is_empty!(targets) {
        return Some(TaskRejected::new(
            "nothing to guard around any visible harvester / claim",
        ));
    }

    let near: std::collections::HashSet<Position> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(self_.state.nearby_tiles)));
    let affords_road = can_afford(self_, EntityType::Road);
    let affords_guard = can_afford(self_, EntityType::Conveyor);

    let mut no_guard: std::collections::HashSet<Position> = pyrust::set::new!();
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

        if affords_road
            && pyrust::set::contains!(near, &feed)
            && self_.get_cost_p(idx_of(feed)) > 1
            && pyrust::unwrap!(ct.can_build_road(feed))
        {
            if DEBUG_LOG {
                if DEBUG_LOG {
                    let mut args = Map::new();
                    pyrust::dict::insert!(
                        args,
                        pyrust::to_string!("feed"),
                        auto_wrap_position(feed)
                    );
                    log(
                        "guard_harvester_neighbours: ROAD on feed {feed} (prep step-off)",
                        args,
                    );
                }
            }
            pyrust::unwrap!(ct.build_road(feed));
            return None;
        }

        if !affords_guard {
            continue;
        }
        let tx = target.x;
        let ty = target.y;
        for &(dx, dy) in &DIR4_DELTA {
            let nx = tx + dx;
            let ny = ty + dy;
            if nx < 0 || nx >= w || ny < 0 || ny >= h {
                continue;
            }
            let pos = Position { x: nx, y: ny };
            if !pyrust::set::contains!(near, &pos) {
                continue;
            }
            if pyrust::set::contains!(no_guard, &pos) {
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
