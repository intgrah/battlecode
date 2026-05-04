//! Launcher swarm: place launchers in tiles around enemy builder bots,
//! picking the spot with the best protection (most surrounding walls /
//! non-passable buildings) and densest enemy-bot coverage. Affordable
//! and spaced ≥`LAUNCHER_SPACING` Chebyshev apart from existing
//! friendlies.
//!
//! Scoring per candidate `p` (an 8-neighbour of an enemy bot):
//!   protection = #(walls + non-walkable buildings in p's 8 neighbours)
//!   bot_score  = #(enemy bots within Chebyshev 1 of p) — these are
//!                 throwable next turn.
//!   total = bot_score * 5 + protection
//!
//! `bot_score` dominates because the throw is the whole point. Protection
//! is a tiebreaker that biases away from open-field placements.

use cambc::{BuildExtra, Controller, ControllerApi, EntityType, Environment, Position};

use crate::builder::Builder;
use crate::builder::helpers::{can_afford, make_move, try_place};
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};
use crate::util::directions::DIR8;
use crate::util::metrics::chebyshev;

/// Don't double-place: skip if a friendly launcher is within this many
/// tiles (Chebyshev) of the candidate spot.
const LAUNCHER_SPACING: i32 = 2;

const PASSABLE_BUILDINGS: [EntityType; 5] = [
    EntityType::Conveyor,
    EntityType::Road,
    EntityType::Splitter,
    EntityType::ArmouredConveyor,
    EntityType::Bridge,
];

/// True iff `pos` is buildable terrain we can place a launcher on.
fn buildable_for_launcher(self_: &Builder, pos: Position) -> bool {
    if !self_.in_bounds(pos) {
        return false;
    }
    if !self_.is_buildable(pos) {
        return false;
    }
    if pyrust::is_some!(self_.kind_at(pos)) {
        return false;
    }
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

/// Count of impassable tiles in `p`'s 8 neighbours (out-of-bounds, walls,
/// non-walkable buildings). Higher = more sheltered launcher spot.
fn protection_score(self_: &Builder, p: Position) -> i32 {
    let mut s = 0;
    for d in DIR8 {
        let n = p.add(d);
        if !self_.in_bounds(n) {
            s += 1;
            continue;
        }
        if self_.get_env(n) == Some(Environment::Wall) {
            s += 1;
            continue;
        }
        if let Some(kind) = self_.kind_at(n)
            && !pyrust::vec::contains!(PASSABLE_BUILDINGS, &kind)
        {
            s += 1;
        }
    }
    s
}

/// Count of enemy builder bots within Chebyshev 1 of `p` — throwable on
/// the very next launcher turn.
fn bot_score(self_: &Builder, p: Position) -> i32 {
    let mut s = 0;
    for &bot in &self_.state.enemy_bots {
        if chebyshev(bot, p) <= 1 {
            s += 1;
        }
    }
    s
}

pub fn launcher_swarm(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    if !can_afford(self_, EntityType::Launcher) {
        return Some(TaskRejected::new("cannot afford LAUNCHER"));
    }

    let enemy_bots: Vec<Position> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(self_.state.enemy_bots)));
    if pyrust::vec::is_empty!(enemy_bots) {
        return Some(TaskRejected::new("no enemy bots in vision"));
    }

    let my_pos = self_.state.my_pos;
    let mut best: Option<Position> = None;
    let mut best_score: i32 = i32::MIN;
    let mut best_dist: i32 = i32::MAX;

    // Candidate spots = 8-neighbours of every visible enemy bot. Dedup
    // happens implicitly via the score comparison.
    for &bot in &enemy_bots {
        for d in DIR8 {
            let p = bot.add(d);
            if !buildable_for_launcher(self_, p) {
                continue;
            }
            if launcher_already_nearby(self_, p) {
                continue;
            }
            let score = bot_score(self_, p) * 5 + protection_score(self_, p);
            let dist = my_pos.distance_squared(p);
            if score > best_score || (score == best_score && dist < best_dist) {
                best_score = score;
                best_dist = dist;
                best = Some(p);
            }
        }
    }

    let Some(spot) = best else {
        return Some(TaskRejected::new(
            "no buildable spot adjacent to any enemy bot",
        ));
    };

    if my_pos.distance_squared(spot) > 2 {
        make_move(self_, ct, spot);
        return None;
    }
    if try_place(
        self_,
        ct,
        EntityType::Launcher,
        spot,
        BuildExtra::None,
        true,
    ) {
        return None;
    }
    Some(TaskRejected::new("launcher placement failed"))
}
