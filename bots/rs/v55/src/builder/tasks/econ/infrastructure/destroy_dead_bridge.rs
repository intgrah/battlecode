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
use crate::util::constants::MAX_WIDTH;
use crate::util::metrics::chebyshev;

const UPSTREAM_SEARCH_CAP: usize = 80;

/// BFS backwards from `start` through `in_edges` until a friendly
/// bridge is found. Returns the bridge position or None.
fn find_upstream_bridge(self_: &Builder, start: Position) -> Option<Position> {
    let mut visited: HashSet<Position> = HashSet::new();
    visited.insert(start);
    let mut queue: Vec<Position> = vec![start];
    while let Some(cur) = queue.pop() {
        if visited.len() >= UPSTREAM_SEARCH_CAP {
            break;
        }
        for &u in &self_.in_edges[cur.y as usize * MAX_WIDTH + cur.x as usize] {
            if visited.contains(&u) {
                continue;
            }
            visited.insert(u);
            if self_.kind_at(u) == Some(EntityType::Bridge)
                && self_.team_at(u) == Some(self_.my_team)
            {
                return Some(u);
            }
            queue.push(u);
        }
    }
    None
}

pub fn destroy_dead_bridge(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if self_.unreachable_dangling.is_empty() {
        return Err(TaskRejected::new("no unreachable dangling"));
    }
    let my_pos = self_.my_pos;
    let target = *self_
        .unreachable_dangling
        .iter()
        .min_by_key(|&&p| (chebyshev(my_pos, p), p.y, p.x))
        .unwrap();
    let Some(bridge) = find_upstream_bridge(self_, target) else {
        return Err(TaskRejected::from_string(format!(
            "no bridge upstream of unreachable dangling {:?}",
            target
        )));
    };
    if ct.can_destroy(bridge).unwrap() {
        ct.destroy(bridge).unwrap();
        self_.apply_local_destroy(bridge);
        return Ok(());
    }
    if make_move(self_, ct, bridge) {
        return Ok(());
    }
    Err(TaskRejected::from_string(format!(
        "cannot destroy or approach bridge {:?}",
        bridge
    )))
}
