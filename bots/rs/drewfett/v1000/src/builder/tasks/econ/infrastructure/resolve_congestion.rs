//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/resolve_congestion.py`.
//!
//! Relieve an overcapacity junction by destroying one of its immediate
//! friendly feeders. The removed feeder's upstream chain becomes dangling
//! at the old feeder tile; subsequent extend-chain tasks reroute it to a
//! less-saturated sink. Candidate junctions come from `congested_junctions`
//! (populated empirically by `update_economy_reachability`).

use cambc::{Controller, ControllerApi, Position};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::debug::debug as log;
use crate::util::metrics::chebyshev;
use crate::util::posint::{PosInt, idx_of};

pub fn resolve_congestion(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if pyrust::vec::is_empty!(self_.congested_junctions) {
        return Some(TaskRejected::new("no congested junction in range"));
    }
    log(
        &format!(
            "resolve_congestion: {} congested junctions visible",
            pyrust::len!(self_.congested_junctions)
        ),
        Map::new(),
    );

    // Sort the junction iteration so candidate-feeder accumulation is
    // deterministic across hash-randomized iteration of `congested_junctions`.
    // PosInt = y*100+x, so sorting by PosInt is identical to sorting by (y,x).
    let mut junctions: Vec<PosInt> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(self_.congested_junctions)));
    pyrust::sort!(junctions);
    let mut targets: Vec<Position> = pyrust::vec::new!();
    for j_pi in junctions {
        for &feeder in &self_.in_edges[j_pi as usize] {
            let fi = idx_of(feeder) as usize;
            if pyrust::is_none!(self_.building_kind[fi]) {
                continue;
            }
            if self_.building_team[fi] != Some(self_.my_team) {
                continue;
            }
            pyrust::vec::push!(targets, feeder);
        }
    }
    // Same feeder may be reachable through multiple junctions; dedupe and
    // re-sort so destroy / approach order is fully deterministic.
    pyrust::sort_by_key!(targets, |p| (p.y, p.x));
    // Remove consecutive duplicates after sorting.
    let mut targets_dedup: Vec<Position> = pyrust::vec::new!();
    let mut _prev_dedup: Option<Position> = None;
    for _p_dedup in pyrust::iter!(targets) {
        if _prev_dedup != Some(*_p_dedup) {
            pyrust::vec::push!(targets_dedup, *_p_dedup);
        }
        _prev_dedup = Some(*_p_dedup);
    }
    let targets = targets_dedup;

    if pyrust::vec::is_empty!(targets) {
        log(
            "resolve_congestion: no friendly feeders to remove",
            Map::new(),
        );
        return Some(TaskRejected::new(
            "congested junction has no friendly feeder to remove",
        ));
    }
    log(
        &format!(
            "resolve_congestion: {} candidate feeders",
            pyrust::len!(targets)
        ),
        Map::new(),
    );

    for &feeder in &targets {
        if pyrust::unwrap!(ct.can_destroy(feeder)) {
            log(
                &format!("resolve_congestion: DESTROY feeder {feeder:?}"),
                Map::new(),
            );
            pyrust::unwrap!(ct.destroy(feeder));
            self_.apply_local_destroy(feeder);
            return None;
        }
    }

    let my_pos = self_.my_pos;
    // Tiebreak by (y, x) on top of chebyshev distance.
    let nearest = *pyrust::unwrap!(pyrust::min_by!(pyrust::iter!(targets), |&&p| (
        chebyshev(my_pos, p),
        p.y,
        p.x
    )));
    log(
        &format!("resolve_congestion: walking toward nearest feeder {nearest:?}"),
        Map::new(),
    );
    if make_move(self_, ct, nearest) {
        return None;
    }
    log(
        &format!("resolve_congestion: could not approach {nearest:?}"),
        Map::new(),
    );
    Some(TaskRejected::from_string(format!(
        "cannot approach feeder {nearest:?}"
    )))
}
