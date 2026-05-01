//! Reactive frontier exploration.
//!
//! Each builder picks an unobserved tile as its target, scoring candidates
//! by:
//!   - distance from self (closer is better, base term)
//!   - heading commitment (prefer targets in the direction we last moved;
//!     prevents u-turning through already-observed territory)
//!   - frontier-density along the path to the target (reward routes that
//!     cross unobserved tiles, not already-trodden ones)
//!   - cluster penalty (avoid targets near other friendly builders)
//!
//! Target sticks across turns until reached, observed, or unreachable
//! (UF component mismatch). The heading is set by `try_move_to` and decays
//! to None when the bot didn't move last turn.
//!
//! No hard quadrants, no fixed landmarks. Map shape and other-bot positions
//! shape the target selection reactively.

use cambc::{Controller, Position};

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::util::constants::MAX_WIDTH;

/// Number of unobserved tiles to sample as candidate targets each replan.
const _K_CANDIDATES: usize = 20;

/// Number of points sampled along self->target line for frontier-density score.
const _LINE_SAMPLES: i32 = 8;

/// α: penalty for picking targets misaligned with current heading.
/// 0 = pure distance; large = strict heading commitment.
const _HEADING_WEIGHT: f64 = 8.0;

/// β: reward per unobserved-tile-along-path. Drives the bot toward
/// candidates whose route cuts through fog rather than known territory.
const _FRONTIER_REWARD: f64 = 6.0;

/// γ: per-friendly-bot proximity penalty around candidate.
const _CLUSTER_PENALTY: f64 = 30.0;

/// Friendly bots within this chebyshev radius of a candidate add the
/// full γ penalty; falls off linearly to 0 at radius.
const _CLUSTER_RADIUS: i32 = 20;

pub fn explore(builder: &mut Builder, ct: &mut Controller<'_>) {
    if pyrust::is_none!(builder.explore_target) || _target_invalid(builder, pyrust::unwrap!(builder.explore_target))
    {
        builder.explore_target = _pick_target(builder);
    }

    let Some(target) = builder.explore_target else {
        return;
    };
    make_move(builder, ct, target);
}

/// A target is invalid once it has been observed (env transitioned
/// from None). UF reachability isn't checked here: an unobserved
/// candidate is necessarily not in any UF component (UF only admits
/// tiles seeded by observed buildings), so requiring UF membership
/// would reject every fog tile by definition.
fn _target_invalid(builder: &Builder, target: Position) -> bool {
    let i = (target.y as usize) * MAX_WIDTH + (target.x as usize);
    pyrust::is_some!(builder.env[i])
}

/// Sample K random unobserved tiles within an expanding Chebyshev
/// radius of a center, score each, pick the lowest. The radius grows
/// linearly from 0.4·s at T0 to cap·s at T100 (capped), where
/// `s = max(w, h)`.
///
/// For OFFENSE the center is `en_core_guess` — fog gets cleared in a
/// growing orbit around the enemy core rather than around the bot.
/// Cap is 1.0 (eventually full map). For ECON / DEFENSE the center
/// is the bot itself with cap 0.8.
fn _pick_target(builder: &mut Builder) -> Option<Position> {
    let w = builder.state.width;
    let h = builder.state.height;
    let is_offense = builder
        .role
        .is_some_and(|r: crate::builder::role::Role| r.is_offensive());
    let cap: f64 = if is_offense { 1.0 } else { 0.8 };
    let frac = (cap).min(0.4 + (cap - 0.4) * (builder.state.round as f64) / 100.0);
    let radius = ((w.max(h) as f64) * frac) as i32;
    let center = if is_offense {
        builder.en_core_guess()
    } else {
        builder.state.my_pos
    };
    let cx = center.x;
    let cy = center.y;
    let mut candidates: Vec<Position> = pyrust::vec::new!();
    for _ in 0..(_K_CANDIDATES * 4) {
        if pyrust::len!(candidates) >= _K_CANDIDATES {
            break;
        }
        let x = builder.state.rng.randint(0, (w - 1) as i64) as i32;
        let y = builder.state.rng.randint(0, (h - 1) as i64) as i32;
        if (x - cx).abs().max((y - cy).abs()) > radius {
            continue;
        }
        let i = (y as usize) * MAX_WIDTH + (x as usize);
        if pyrust::is_none!(builder.env[i]) {
            pyrust::vec::push!(candidates, Position { x, y });
        }
    }
    if candidates.is_empty() {
        return None;
    }

    let heading = builder.explore_heading;
    let mut best: Option<Position> = None;
    let mut best_score = f64::INFINITY;
    for c in &candidates {
        let score = _score(builder, *c, heading);
        if score < best_score {
            best_score = score;
            best = Some(*c);
        }
    }
    best
}

fn _score(builder: &Builder, c: Position, heading: Option<(i32, i32)>) -> f64 {
    let pos = builder.state.my_pos;
    let dx = c.x - pos.x;
    let dy = c.y - pos.y;
    let chebyshev_d = dx.abs().max(dy.abs());

    let mut score = chebyshev_d as f64;

    // Heading commitment: penalty when the target is misaligned with
    // the direction we've been going. cos_align in [-1, 1]; (1 - x) in
    // [0, 2] so a u-turn target costs 2*α.
    if let Some((hx, hy)) = heading
        && (hx != 0 || hy != 0)
    {
        let cx = (dx > 0) as i32 - (dx < 0) as i32;
        let cy = (dy > 0) as i32 - (dy < 0) as i32;
        let h_mag = (((hx * hx + hy * hy) as f64).sqrt()).abs();
        let c_mag = (((cx * cx + cy * cy) as f64).sqrt()).abs();
        if h_mag > 0.0 && c_mag > 0.0 {
            let cos_align = ((hx * cx + hy * cy) as f64) / (h_mag * c_mag);
            score += _HEADING_WEIGHT * (1.0 - cos_align);
        }
    }

    // Frontier-density along the line: sample tiles between self and
    // target, count unobserved. Reward (subtract) is scaled to the
    // number of unobserved samples, normalised by sample count.
    let mut unseen = 0;
    for k in 1..=_LINE_SAMPLES {
        let t = (k as f64) / ((_LINE_SAMPLES + 1) as f64);
        let sx = ((pos.x as f64) + t * (dx as f64)).round() as i32;
        let sy = ((pos.y as f64) + t * (dy as f64)).round() as i32;
        if 0 <= sx
            && sx < builder.state.width
            && 0 <= sy
            && sy < builder.state.height
            && pyrust::is_none!(builder.env[(sy as usize) * MAX_WIDTH + (sx as usize)])
        {
            unseen += 1;
        }
    }
    score -= _FRONTIER_REWARD * (unseen as f64) / (_LINE_SAMPLES as f64);

    // Cluster penalty: if any friendly bot is near the candidate, add
    // to the score. Linear falloff to zero at _CLUSTER_RADIUS. Iterate
    // (y, x)-sorted so the float accumulation order matches across runs
    // (HashSet iteration is randomized; sorted folds are not).
    let mut friendlies: Vec<Position> = pyrust::collect!(pyrust::copied!(pyrust::iter!(builder.state.friendly_bots)));
    pyrust::sort_by_key!(friendlies, |p| (p.y, p.x));
    for fb in &friendlies {
        if *fb == pos {
            continue;
        }
        let cdx = (c.x - fb.x).abs();
        let cdy = (c.y - fb.y).abs();
        let d = cdx.max(cdy);
        if d < _CLUSTER_RADIUS {
            score += _CLUSTER_PENALTY * (1.0 - (d as f64) / (_CLUSTER_RADIUS as f64));
        }
    }

    score
}
