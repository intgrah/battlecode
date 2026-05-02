//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/destroy_dead_bridge.py`.
//!
//! Tear down a friendly bridge whose downstream chain has become
//! unreachable. BFS upstream from each `unreachable_dangling` tile through
//! `in_edges` to find a friendly bridge; if found and within range, destroy
//! it (freeing the Ti scaling) so the upstream chain can be re-routed by the
//! extend-chain tasks. Otherwise approach the bridge.

use std::collections::HashSet;

use cambc::{Controller, ControllerApi, EntityType, Position};

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::posint::{cheb, idx_of, pos_of};

const UPSTREAM_SEARCH_CAP: usize = 80;

/// BFS backwards from `start` through `in_edges` until a friendly
/// bridge is found. Returns the bridge position or None.
fn find_upstream_bridge(self_: &Builder, start: Position) -> Option<Position> {
    let mut visited: HashSet<Position> = pyrust::set::new!();
    pyrust::set::add!(visited, start);
    let mut queue: Vec<Position> = vec![start];
    while let Some(cur) = pyrust::vec::pop!(queue) {
        if pyrust::len!(visited) >= UPSTREAM_SEARCH_CAP {
            break;
        }
        for &u in &self_.in_edges[idx_of(cur) as usize] {
            if pyrust::vec::contains!(visited, &u) {
                continue;
            }
            pyrust::set::add!(visited, u);
            if self_.kind_at(u) == Some(EntityType::Bridge)
                && self_.team_at(u) == Some(self_.my_team)
            {
                return Some(u);
            }
            pyrust::vec::push!(queue, u);
        }
    }
    None
}

pub fn destroy_dead_bridge(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if pyrust::vec::is_empty!(self_.unreachable_dangling) {
        return Some(TaskRejected::new("no unreachable dangling"));
    }
    let my_pos = self_.my_pos;
    let my_pos_i = idx_of(my_pos);
    let target_i = *pyrust::unwrap!(pyrust::min_by!(
        pyrust::iter!(self_.unreachable_dangling),
        |&&p| {
            // Use chebyshev table directly: no pos_of needed. Tiebreak by p
            // is equivalent to (y, x) since p = y*100+x and x < 50.
            (cheb(my_pos_i, p), p)
        }
    ));
    let target = pos_of(target_i);
    let Some(bridge) = find_upstream_bridge(self_, target) else {
        return Some(TaskRejected::from_string(format!(
            "no bridge upstream of unreachable dangling {target:?}"
        )));
    };
    if pyrust::unwrap!(ct.can_destroy(bridge)) {
        pyrust::unwrap!(ct.destroy(bridge));
        self_.apply_local_destroy(bridge);
        return None;
    }
    if make_move(self_, ct, bridge) {
        return None;
    }
    Some(TaskRejected::from_string(format!(
        "cannot destroy or approach bridge {bridge:?}"
    )))
}
