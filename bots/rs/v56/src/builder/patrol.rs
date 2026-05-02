//! Cluster-aware cyclic patrol with alert-graded expansion.
//!
//! Each builder maintains a list of clusters: `patrol_clusters[i]` is
//! a Vec<Position> (insertion-NN cycle), `patrol_cluster_centroids[i]`
//! is its centroid. New harvesters join the cluster whose centroid is
//! closest, provided d² ≤ `_CLUSTER_THRESHOLD`. Otherwise a new
//! cluster is born. No merging, no splitting.
//!
//! On entering patrol, the builder picks one cluster:
//! - First time, or its current cluster is dead → closest cluster by
//!   centroid d² to `my_pos`.
//! - Else if `alert == 0` and 50 turns have passed since last reroll →
//!   weighted random pick by cluster size.
//! - Otherwise → keep the current pick.
//!
//! The walk target is `expand_outward(cycle[idx], my_core, expansion)`
//! where `expansion = LOW * (1 - alert/MAX)`.

use cambc::{Controller, Position};
use serde_json::{Map, Value};

use crate::builder::Builder;
use crate::builder::helpers::make_move;
use crate::util::constants::{INF, MAX_WIDTH};
use crate::util::debug::debug as log;
use crate::util::directions::DIR4;
use crate::util::metrics::chebyshev;
use crate::util::visualiser::auto_wrap_position;

#[pyrust::inline]
const _ALERT_BOOST_TO: i32 = 60;
#[pyrust::inline]
const _ALERT_MAX: i32 = 60;
#[pyrust::inline]
/// Turns before earliest possible enemy arrival at our core to one-shot
/// max-alert all builders. `min_chebyshev_to_mirrored_core - this`.
const _PRE_EMPTIVE_BUFFER: i32 = 8;
#[pyrust::inline]
const _EXPANSION_LOW: f64 = 6.0;
#[pyrust::inline]
/// Cluster size at which the size-cap on expansion starts dropping.
/// Below this, the size-cap is _EXPANSION_LOW (8). Above, it falls
/// linearly toward 0.
const _SIZE_CAP_KNEE: f64 = 4.0;
#[pyrust::inline]
/// Cluster size at which the size-cap reaches the half-cap target (4).
/// Used to set the linear slope past the knee; cap continues falling
/// past this point at the same rate.
const _SIZE_CAP_HALF: f64 = 10.0;
#[pyrust::inline]
const _CLUSTER_THRESHOLD: i32 = 50;
#[pyrust::inline]
/// Centroid weight of a Harvester member.
pub const HARVESTER_WEIGHT: f64 = 4.0;
#[pyrust::inline]
/// Centroid weight of a Conveyor / ArmouredConveyor member.
pub const CONVEYOR_WEIGHT: f64 = 1.0;
#[pyrust::inline]
const _REROLL_INTERVAL: i32 = 50;

#[pyrust::inline]
const _ECON_RADIUS_FLOOR: i32 = 256;
#[pyrust::inline]
const _ECON_RADIUS_CAP: i32 = 1600;
#[pyrust::inline]
const _ECON_RADIUS_PICK_SHRINK: i32 = 8;
#[pyrust::inline]
const _ECON_RADIUS_DRY_GROW: i32 = 4;

/// Ratchet the ECON exploration locus radius. Shrinks on a recent
/// harvester observation (just-picked = good, pull bot back toward
/// known infra). Grows otherwise (dry streak = bot needs to look
/// further). Clamped to `[_ECON_RADIUS_FLOOR, _ECON_RADIUS_CAP]`.
pub fn update_econ_explore_radius(builder: &mut Builder) {
    let dry = builder.state.round - builder.last_harvester_add_round;
    if dry <= 1 {
        builder.econ_explore_radius_sq -= _ECON_RADIUS_PICK_SHRINK;
    } else {
        builder.econ_explore_radius_sq += _ECON_RADIUS_DRY_GROW;
    }
    if builder.econ_explore_radius_sq < _ECON_RADIUS_FLOOR {
        builder.econ_explore_radius_sq = _ECON_RADIUS_FLOOR;
    }
    if builder.econ_explore_radius_sq > _ECON_RADIUS_CAP {
        builder.econ_explore_radius_sq = _ECON_RADIUS_CAP;
    }
}

/// True iff `p` is within `econ_explore_radius_sq` of any member of
/// any cluster. Vacuously true if there are no clusters. Used as a soft
/// bound on ECON/PermEcon explore-target selection only — does NOT
/// constrain ore picking.
#[must_use]
pub fn in_any_cluster_locus(builder: &Builder, p: Position) -> bool {
    if pyrust::vec::is_empty!(builder.patrol_clusters) {
        return true;
    }
    let r = builder.econ_explore_radius_sq;
    for cluster in &builder.patrol_clusters {
        for m in cluster {
            if p.distance_squared(*m) <= r {
                return true;
            }
        }
    }
    false
}

/// Earliest possible enemy arrival turn at our core: the chebyshev
/// distance from `my_core` to its mirror under any *surviving*
/// symmetry candidate. As candidates are ruled out, the bound only
/// grows (later trigger).
fn _min_enemy_arrival(builder: &Builder) -> i32 {
    let w = builder.state.width;
    let h = builder.state.height;
    let my_core = builder.my_core;
    let mut min_d = i32::MAX;
    for sym in pyrust::copied!(pyrust::iter!(builder.state.symmetry_candidates)) {
        let en = sym.action(my_core, w, h);
        let d = chebyshev(my_core, en);
        if d < min_d {
            min_d = d;
        }
    }
    min_d
}

/// Bump alert if any enemy bot OR turret is in vision; else decay by
/// 1 (floored at 0). One-shot pre-emptive max-alert at
/// `min_enemy_arrival - _PRE_EMPTIVE_BUFFER`. Capped at `_ALERT_MAX`.
pub fn update_alert(builder: &mut Builder) {
    let has_enemy = !pyrust::vec::is_empty!(builder.state.enemy_bots)
        || pyrust::is_some!(builder.nearest_enemy_turret);
    if has_enemy {
        if builder.alert < _ALERT_BOOST_TO {
            builder.alert = _ALERT_BOOST_TO;
        }
    } else if builder.alert > 0 {
        builder.alert -= 1;
    }
    let trigger = _min_enemy_arrival(builder) - _PRE_EMPTIVE_BUFFER;
    if builder.state.round == trigger {
        builder.alert = _ALERT_MAX;
    }
    if builder.alert > _ALERT_MAX {
        builder.alert = _ALERT_MAX;
    }
}

/// Scale-driven cap: stays near `_EXPANSION_LOW` (8) through the rapid
/// early-game scale ramp, accelerates downward later, hits 0 at
/// scale=12 (1200%).
fn _scale_cap(scale: f64) -> f64 {
    let t: f64 = (scale - 1.0) / 11.0;
    let factor: f64 = 1.0 - t * t;
    let f = pyrust::max!(0.0_f64, factor);
    _EXPANSION_LOW * f
}

/// Cluster-size-driven cap: a 10-tile cluster is a long perimeter to
/// circumnavigate, and overshooting it 8 tiles outward stretches the
/// patrol path past anything navigable. Linear: 8 below the knee,
/// drops to 4 by the half-knee, continues at the same slope past.
fn _size_cap(cluster_len: usize) -> f64 {
    let n = pyrust::float!(cluster_len);
    let over = pyrust::max!(0.0_f64, n - _SIZE_CAP_KNEE);
    let slope = (_EXPANSION_LOW - _EXPANSION_LOW / 2.0) / (_SIZE_CAP_HALF - _SIZE_CAP_KNEE);
    pyrust::max!(0.0_f64, _EXPANSION_LOW - over * slope)
}

fn _expansion_cap(scale: f64, cluster_len: usize) -> f64 {
    pyrust::min!(_scale_cap(scale), _size_cap(cluster_len))
}

pub fn alert_expansion(alert: i32, scale: f64, cluster_len: usize) -> f64 {
    let t = pyrust::float!(alert) / pyrust::float!(_ALERT_MAX);
    _expansion_cap(scale, cluster_len) * (1.0 - t)
}

/// Push `t` outward from `centroid` by `expansion` tiles along the
/// (t - centroid) ray. Clamped to the map bounds. `centroid` is a
/// float because it's the running mean of cluster members.
pub fn expand_outward(
    t: Position,
    centroid: (f64, f64),
    expansion: f64,
    w: i32,
    h: i32,
) -> Position {
    let dx = pyrust::float!(t.x) - centroid.0;
    let dy = pyrust::float!(t.y) - centroid.1;
    let len_sq = dx * dx + dy * dy;
    if len_sq <= 0.0 {
        return t;
    }
    let len = pyrust::sqrt!(len_sq);
    let factor = 1.0 + expansion / len;
    let nx = pyrust::round!((dx * factor + centroid.0)) as i32;
    let ny = pyrust::round!((dy * factor + centroid.1)) as i32;
    Position {
        x: pyrust::max!(0, pyrust::min!(nx, w - 1)),
        y: pyrust::max!(0, pyrust::min!(ny, h - 1)),
    }
}

fn _walkable_anchor(builder: &Builder, pos: Position) -> Option<Position> {
    let cost_grid = &builder.cost_grid;
    if cost_grid[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)] != INF {
        return Some(pos);
    }
    let mut best: Option<Position> = None;
    let mut best_cost = INF;
    for d in DIR4 {
        let n = pos.add(d);
        if !builder.in_bounds(n) {
            continue;
        }
        let c = cost_grid[(n.y as usize) * MAX_WIDTH + (n.x as usize)];
        if c != INF && c < best_cost {
            best_cost = c;
            best = Some(n);
        }
    }
    best
}

fn _centroid_d2(centroid: (f64, f64), p: Position) -> f64 {
    let dx = centroid.0 - pyrust::float!(p.x);
    let dy = centroid.1 - pyrust::float!(p.y);
    dx * dx + dy * dy
}

/// Sort `cluster` by polar angle around `centroid`. The resulting cycle
/// visits members in counter-clockwise order from due-east — non-self-
/// intersecting for points roughly in convex position. Angle is
/// discretised to an i64 key (×1e6) because `f64` isn't `Ord`.
fn _polar_sort(cluster: &mut Vec<Position>, centroid: (f64, f64)) {
    pyrust::sort_by_key!(cluster, |p| {
        (pyrust::atan2!(
            pyrust::float!(p.y) - centroid.1,
            pyrust::float!(p.x) - centroid.0
        ) * 1_000_000.0) as i64
    });
}

/// Insert `p` (member weight `w`) into the cluster system: join the
/// cluster with the closest centroid if d² ≤ `_CLUSTER_THRESHOLD`;
/// otherwise spawn a new cluster `[p]`. Cycle order maintained by
/// polar-sort around the (weighted) centroid after every change.
pub fn insert_into_clusters(
    clusters: &mut Vec<Vec<Position>>,
    centroids: &mut Vec<(f64, f64)>,
    weights: &mut Vec<f64>,
    p: Position,
    w: f64,
) {
    let n = pyrust::len!(clusters);
    let mut best_i: usize = 0;
    let mut best_d: f64 = f64::MAX;
    for i in 0..n {
        let d = _centroid_d2(centroids[i], p);
        if d < best_d {
            best_d = d;
            best_i = i;
        }
    }
    if n == 0 || best_d > pyrust::float!(_CLUSTER_THRESHOLD) {
        let mut q: Vec<Position> = pyrust::vec::new!();
        pyrust::vec::push!(q, p);
        pyrust::vec::push!(clusters, q);
        pyrust::vec::push!(centroids, (pyrust::float!(p.x), pyrust::float!(p.y)));
        pyrust::vec::push!(weights, w);
        return;
    }
    pyrust::vec::push!(clusters[best_i], p);
    let old_w = weights[best_i];
    let new_w = old_w + w;
    let cx = (centroids[best_i].0 * old_w + pyrust::float!(p.x) * w) / new_w;
    let cy = (centroids[best_i].1 * old_w + pyrust::float!(p.y) * w) / new_w;
    centroids[best_i] = (cx, cy);
    weights[best_i] = new_w;
    _polar_sort(&mut clusters[best_i], centroids[best_i]);
}

/// Insert `p` (member weight `w`) into the closest existing cluster IFF
/// its centroid is within `_CLUSTER_THRESHOLD`. No new cluster is
/// spawned — used for "decoration" tiles (friendly conveyors) that
/// should join an existing harvester cluster but never seed one.
pub fn insert_into_existing_cluster(
    clusters: &mut Vec<Vec<Position>>,
    centroids: &mut Vec<(f64, f64)>,
    weights: &mut Vec<f64>,
    p: Position,
    w: f64,
) {
    let n = pyrust::len!(clusters);
    if n == 0 {
        return;
    }
    let mut best_i: usize = 0;
    let mut best_d: f64 = f64::MAX;
    for i in 0..n {
        let d = _centroid_d2(centroids[i], p);
        if d < best_d {
            best_d = d;
            best_i = i;
        }
    }
    if best_d > pyrust::float!(_CLUSTER_THRESHOLD) {
        return;
    }
    pyrust::vec::push!(clusters[best_i], p);
    let old_w = weights[best_i];
    let new_w = old_w + w;
    let cx = (centroids[best_i].0 * old_w + pyrust::float!(p.x) * w) / new_w;
    let cy = (centroids[best_i].1 * old_w + pyrust::float!(p.y) * w) / new_w;
    centroids[best_i] = (cx, cy);
    weights[best_i] = new_w;
    _polar_sort(&mut clusters[best_i], centroids[best_i]);
}

/// Remove `p` (member weight `w`, must match the weight it was added
/// with) from whichever cluster contains it. Update centroid; if the
/// cluster becomes empty, drop it (and its centroid + weight).
pub fn remove_from_clusters(
    clusters: &mut Vec<Vec<Position>>,
    centroids: &mut Vec<(f64, f64)>,
    weights: &mut Vec<f64>,
    p: Position,
    w: f64,
) {
    let n = pyrust::len!(clusters);
    let mut found_i: i32 = -1;
    for i in 0..n {
        let q = &clusters[i];
        for j in 0..pyrust::len!(q) {
            if q[j] == p {
                found_i = i as i32;
                break;
            }
        }
        if found_i >= 0 {
            break;
        }
    }
    if found_i < 0 {
        return;
    }
    let i = found_i as usize;
    pyrust::vec::retain!(clusters[i], |&q| q != p);
    if pyrust::vec::is_empty!(clusters[i]) {
        clusters.remove(i);
        centroids.remove(i);
        weights.remove(i);
        return;
    }
    let old_w = weights[i];
    let new_w = old_w - w;
    let cx = (centroids[i].0 * old_w - pyrust::float!(p.x) * w) / new_w;
    let cy = (centroids[i].1 * old_w - pyrust::float!(p.y) * w) / new_w;
    centroids[i] = (cx, cy);
    weights[i] = new_w;
}

/// Cluster with the closest centroid to `pos`. Returns 0 if there are
/// no clusters (caller must guard).
fn _closest_cluster(centroids: &[(f64, f64)], pos: Position) -> usize {
    let mut best_i: usize = 0;
    let mut best_d = f64::MAX;
    for i in 0..pyrust::len!(centroids) {
        let d = _centroid_d2(centroids[i], pos);
        if d < best_d {
            best_d = d;
            best_i = i;
        }
    }
    best_i
}

/// Weighted-random cluster index, weighted by cluster size.
fn _weighted_random_cluster(builder: &mut Builder) -> usize {
    let n = pyrust::len!(builder.patrol_clusters);
    let mut population: Vec<i32> = pyrust::vec::new!();
    let mut weights: Vec<f64> = pyrust::vec::new!();
    for i in 0..n {
        pyrust::vec::push!(population, i as i32);
        pyrust::vec::push!(
            weights,
            pyrust::float!(pyrust::len!(builder.patrol_clusters[i]))
        );
    }
    *pyrust::rng_choices!(builder.state.rng, population, weights, 1)[0] as usize
}

pub fn run_patrol(builder: &mut Builder, ct: &mut Controller<'_>) -> bool {
    let n_clusters = pyrust::len!(builder.patrol_clusters);
    if n_clusters == 0 {
        return false;
    }

    // Cluster pick.
    let mut ci = builder.patrol_cluster_idx;
    let stale = ci >= n_clusters;
    let due_reroll = builder.alert == 0
        && (builder.state.round - builder.patrol_last_reroll_round) >= _REROLL_INTERVAL;
    if stale {
        ci = _closest_cluster(&builder.patrol_cluster_centroids, builder.state.my_pos);
        builder.patrol_pos_idx = usize::MAX;
    } else if due_reroll {
        ci = _weighted_random_cluster(builder);
        // Reroll direction too: half flip CW vs CCW each interval.
        let flip = builder.state.rng.random();
        builder.patrol_dir = if flip < 0.5 { 1 } else { -1 };
        builder.patrol_last_reroll_round = builder.state.round;
        builder.patrol_pos_idx = usize::MAX;
    }
    builder.patrol_cluster_idx = ci;

    let qlen = pyrust::len!(builder.patrol_clusters[ci]);
    if qlen == 0 {
        return false;
    }
    let mut idx = builder.patrol_pos_idx;
    if idx >= qlen {
        idx = (builder.state.my_id as usize) % qlen;
    }
    let raw_target = builder.patrol_clusters[ci][idx];
    let centroid = builder.patrol_cluster_centroids[ci];
    let expansion = alert_expansion(builder.alert, builder.state.scale, qlen);
    let expanded_target = expand_outward(
        raw_target,
        centroid,
        expansion,
        builder.state.width,
        builder.state.height,
    );
    let advance = builder.state.my_pos.distance_squared(expanded_target) <= 5;
    if advance {
        if builder.patrol_dir > 0 {
            idx = (idx + 1) % qlen;
        } else {
            idx = (idx + qlen - 1) % qlen;
        }
    }
    builder.patrol_pos_idx = idx;
    let raw_target = builder.patrol_clusters[ci][idx];
    let target = expand_outward(
        raw_target,
        centroid,
        expansion,
        builder.state.width,
        builder.state.height,
    );

    let mut args = Map::new();
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("target"),
        auto_wrap_position(target)
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("raw"),
        auto_wrap_position(raw_target)
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("alert"),
        Value::Number(pyrust::into!(builder.alert as i64))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("ci"),
        Value::Number(pyrust::into!(ci as i64))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("idx"),
        Value::Number(pyrust::into!(idx as i64))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("qlen"),
        Value::Number(pyrust::into!(qlen as i64))
    );
    log(
        "patrol: target {target} raw={raw} alert={alert} cluster={ci} (idx={idx}/{qlen})",
        args,
    );

    let Some(anchor) = _walkable_anchor(builder, target) else {
        return false;
    };
    make_move(builder, ct, anchor);
    true
}
