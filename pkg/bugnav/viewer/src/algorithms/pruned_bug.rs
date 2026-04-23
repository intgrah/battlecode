//! Full-map Bug1, planned ahead, cycle-pruned.
//!
//! 1. Motion-to-goal until a neighbour in `dir_to_goal` is blocked.
//! 2. At an obstacle, wall-follow ONCE CW recording the perimeter.
//! 3. If the CW walk closes back at hit_pos (simple obstacle), the reversed
//!    sub-range is a valid walk and equals what an ACW walk would have
//!    produced. Pick the shorter of the two arcs. Done.
//! 4. If the CW walk doesn't close (edge-flip tangle on a coastline
//!    obstacle), the reversal is NOT what ACW would have found — a CW walk
//!    that edge-flips and an ACW walk that edge-flips visit different
//!    cells. Do a second walk in the ACW direction, take the shorter of
//!    the two forward arcs.
//! 5. Continue motion-to-goal from best_leave.
//! 6. One O(n) cycle-prune pass on the final path. Only fires on edge-flip
//!    tangles where the forward arc can carry repeated positions.

use std::collections::HashMap;

use crate::algorithms::bug_common::{
    DIRS, WallFollowState, WallStepOutcome, dir_to_goal, dist_sq, neighbour, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

/// Amortised O(n) stack-pop prune: on a duplicate cell, pop the stack back
/// to the first occurrence.
fn prune_cycles(path: &[(i32, i32)]) -> Vec<(i32, i32)> {
    let mut out: Vec<(i32, i32)> = Vec::with_capacity(path.len());
    let mut idx: HashMap<(i32, i32), usize> = HashMap::with_capacity(path.len());
    for &c in path {
        if let Some(&k) = idx.get(&c) {
            while out.len() > k + 1 {
                let popped = out.pop().unwrap();
                idx.remove(&popped);
            }
        } else {
            idx.insert(c, out.len());
            out.push(c);
        }
    }
    out
}

#[inline]
fn dir_of(delta: (i32, i32)) -> usize {
    for (i, &d) in DIRS.iter().enumerate() {
        if d == delta {
            return i;
        }
    }
    0
}

#[inline]
fn state_idx(w: i32, wf: &WallFollowState) -> usize {
    let pos_idx = (wf.pos.1 * w + wf.pos.0) as usize;
    let obs_dir = dir_of((
        wf.current_obstacle.0 - wf.pos.0,
        wf.current_obstacle.1 - wf.pos.1,
    ));
    let side = usize::from(wf.obstacle_on_right);
    pos_idx * 16 + obs_dir * 2 + side
}

#[inline]
fn passable(grid: &Grid, x: i32, y: i32) -> bool {
    x >= 0
        && y >= 0
        && x < grid.w
        && y < grid.h
        && !grid.walls[(y * grid.w + x) as usize]
}

struct PerimWalk {
    perim: Vec<(i32, i32)>,
    best_leave_idx: usize,
    best_leave_d: i32,
    closed: bool,
}

/// Inline Bug2 with fixed handedness. Returns None if no m-line crossing
/// closer to goal is found (classical Bug2 incomplete case).
fn bug2_path_with(
    grid: &Grid,
    start: (i32, i32),
    goal: (i32, i32),
    obstacle_on_right: bool,
) -> Option<Vec<(i32, i32)>> {
    let w = grid.w;
    let safety_cap = (2 * w * grid.h) as usize + 16;

    let state_count = (w * grid.h) as usize * 16;
    let mut seen: Vec<u32> = vec![0; state_count];
    let mut version: u32 = 0;

    let pass = |x: i32, y: i32| passable(grid, x, y);
    let onmap = |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < grid.h;

    let mut path: Vec<(i32, i32)> = Vec::with_capacity(128);
    path.push(start);
    let mut pos = start;

    let dx_t = goal.0 - start.0;
    let dy_t = goal.1 - start.1;
    let tol = dx_t.abs().max(dy_t.abs()) / 2;
    let d_start_goal = dist_sq(start, goal);
    let on_mline = |p: (i32, i32)| -> bool {
        let cx = p.0 - start.0;
        let cy = p.1 - start.1;
        if (cy * dx_t - cx * dy_t).abs() > tol {
            return false;
        }
        cx * dx_t + cy * dy_t > 0 && dist_sq(p, goal) < d_start_goal
    };

    loop {
        if pos == goal {
            return Some(path);
        }
        if path.len() > safety_cap {
            return None;
        }

        let d = dir_to_goal(pos, goal);
        let np = neighbour(pos, d);
        if pass(np.0, np.1) {
            pos = np;
            path.push(pos);
            continue;
        }

        let hit_pos = pos;
        let hit_d = dist_sq(hit_pos, goal);
        let blocked_dir = d;
        let mut wf = WallFollowState {
            pos: hit_pos,
            current_obstacle: neighbour(hit_pos, blocked_dir),
            obstacle_on_right,
        };
        version = version.wrapping_add(1);
        if version == 0 {
            for s in seen.iter_mut() {
                *s = 0;
            }
            version = 1;
        }
        seen[state_idx(w, &wf)] = version;

        loop {
            match wall_follow_step(&mut wf, pass, onmap) {
                WallStepOutcome::Moved => {}
                WallStepOutcome::Surrounded => return None,
            }
            path.push(wf.pos);
            if on_mline(wf.pos) && dist_sq(wf.pos, goal) < hit_d {
                pos = wf.pos;
                break;
            }
            let idx = state_idx(w, &wf);
            if seen[idx] == version {
                return None;
            }
            seen[idx] = version;
            if path.len() > safety_cap {
                return None;
            }
        }
    }
}

/// Bug2 trying both handedness and taking whichever completes (shorter if
/// both succeed).
pub fn bug2_path(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Option<Vec<(i32, i32)>> {
    let cw = bug2_path_with(grid, start, goal, true);
    let ccw = bug2_path_with(grid, start, goal, false);
    match (cw, ccw) {
        (Some(a), Some(b)) => Some(if a.len() <= b.len() { a } else { b }),
        (Some(a), None) | (None, Some(a)) => Some(a),
        (None, None) => None,
    }
}

/// Wall-follow one direction from `hit_pos`, returning the full perimeter
/// until state cycle, with the closest-to-goal index pre-computed.
fn walk_perim(
    grid: &Grid,
    hit_pos: (i32, i32),
    blocked_dir: usize,
    goal: (i32, i32),
    obstacle_on_right: bool,
    seen: &mut [u32],
    version: u32,
    safety_cap: usize,
) -> Option<PerimWalk> {
    let w = grid.w;
    let pass = |x: i32, y: i32| passable(grid, x, y);
    let onmap = |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < grid.h;

    let mut wf = WallFollowState {
        pos: hit_pos,
        current_obstacle: neighbour(hit_pos, blocked_dir),
        obstacle_on_right,
    };
    seen[state_idx(w, &wf)] = version;

    let mut perim: Vec<(i32, i32)> = Vec::with_capacity(64);
    perim.push(hit_pos);
    let mut best_leave_d = dist_sq(hit_pos, goal);
    let mut best_leave_idx = 0usize;

    loop {
        match wall_follow_step(&mut wf, pass, onmap) {
            WallStepOutcome::Moved => {}
            WallStepOutcome::Surrounded => return None,
        }
        perim.push(wf.pos);
        let d2 = dist_sq(wf.pos, goal);
        if d2 < best_leave_d {
            best_leave_d = d2;
            best_leave_idx = perim.len() - 1;
        }
        let idx = state_idx(w, &wf);
        if seen[idx] == version {
            break;
        }
        seen[idx] = version;
        if perim.len() > safety_cap {
            return None;
        }
    }

    Some(PerimWalk {
        closed: *perim.last().unwrap() == hit_pos,
        perim,
        best_leave_idx,
        best_leave_d,
    })
}

/// Extract the best arc from a perim walk. For a closed walk, pick min of
/// forward/backward. For a non-closed walk, return forward only.
fn best_arc(w: &PerimWalk) -> Vec<(i32, i32)> {
    let forward_len = w.best_leave_idx;
    let backward_len = w.perim.len() - 1 - w.best_leave_idx;
    if w.closed && backward_len < forward_len {
        let mut out = Vec::with_capacity(backward_len);
        for i in (w.best_leave_idx + 1..w.perim.len() - 1).rev() {
            out.push(w.perim[i]);
        }
        out.push(w.perim[w.best_leave_idx]);
        out
    } else {
        w.perim[1..=w.best_leave_idx].to_vec()
    }
}

/// Pure Bug1 with plan-ahead short-arc leaving. One CW walk per obstacle,
/// with an ACW fallback only when the CW walk doesn't close.
pub fn bug1_path(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Option<Vec<(i32, i32)>> {
    let w = grid.w;
    let safety_cap = (2 * w * grid.h) as usize + 16;

    let state_count = (w * grid.h) as usize * 16;
    let mut seen: Vec<u32> = vec![0; state_count];
    let mut version: u32 = 0;

    let pass_fn = |x: i32, y: i32| passable(grid, x, y);

    let mut path: Vec<(i32, i32)> = Vec::with_capacity(128);
    path.push(start);
    let mut pos = start;
    let mut global_min = dist_sq(start, goal);

    loop {
        if pos == goal {
            return Some(path);
        }
        if path.len() > safety_cap {
            return None;
        }

        // Motion-to-goal.
        let d = dir_to_goal(pos, goal);
        let np = neighbour(pos, d);
        if pass_fn(np.0, np.1) {
            pos = np;
            path.push(pos);
            let d2 = dist_sq(pos, goal);
            if d2 < global_min {
                global_min = d2;
            }
            continue;
        }

        let hit_pos = pos;
        let blocked_dir = d;

        // First walk: CW.
        version = version.wrapping_add(1);
        if version == 0 {
            for s in seen.iter_mut() {
                *s = 0;
            }
            version = 1;
        }
        let cw = walk_perim(
            grid,
            hit_pos,
            blocked_dir,
            goal,
            true,
            &mut seen,
            version,
            safety_cap,
        )?;

        // If CW closed cleanly, short-arc from one walk is sufficient — the
        // reversed sub-range IS what ACW would have produced.
        let chosen = if cw.closed {
            if cw.best_leave_d >= global_min {
                return None;
            }
            (cw.best_leave_d, best_arc(&cw))
        } else {
            // Edge-flip tangle: CW-reversed != ACW walk. Run ACW too.
            version = version.wrapping_add(1);
            if version == 0 {
                for s in seen.iter_mut() {
                    *s = 0;
                }
                version = 1;
            }
            let acw = walk_perim(
                grid,
                hit_pos,
                blocked_dir,
                goal,
                false,
                &mut seen,
                version,
                safety_cap,
            )?;
            let cw_ok = cw.best_leave_d < global_min;
            let acw_ok = acw.best_leave_d < global_min;
            match (cw_ok, acw_ok) {
                (false, false) => return None,
                (true, false) => (cw.best_leave_d, best_arc(&cw)),
                (false, true) => (acw.best_leave_d, best_arc(&acw)),
                (true, true) => {
                    let a = best_arc(&cw);
                    let b = best_arc(&acw);
                    if a.len() <= b.len() {
                        (cw.best_leave_d, a)
                    } else {
                        (acw.best_leave_d, b)
                    }
                }
            }
        };

        let (new_min, arc) = chosen;
        for c in &arc {
            path.push(*c);
        }
        pos = *arc.last().unwrap();
        global_min = new_min;
    }
}

// ───────────────────────────────────────────────────────────────────────────
// Pathfinder wrapper for the benchmark / viewer.
// ───────────────────────────────────────────────────────────────────────────

pub struct PrunedBug {
    path: Vec<(i32, i32)>,
    idx: usize,
    snap: Snapshot,
    status: StepStatus,
}

const MAX_SIM_ITERS: u32 = 20_000;

/// Run any `Pathfinder` to completion, return its raw path.
fn run_to_path<F>(algo: F, grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Option<Vec<(i32, i32)>>
where
    F: Fn(&Grid, (i32, i32), (i32, i32)) -> Box<dyn Pathfinder>,
{
    let mut pf = algo(grid, start, goal);
    for _ in 0..MAX_SIM_ITERS {
        match pf.step() {
            StepStatus::Running => {}
            StepStatus::Arrived => return Some(pf.snapshot().path.clone()),
            StepStatus::Unreachable => return None,
        }
    }
    None
}

fn finish(start: (i32, i32), goal: (i32, i32), path: Vec<(i32, i32)>) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    let status = if path.len() > 1 {
        StepStatus::Running
    } else if path[0] == goal {
        StepStatus::Arrived
    } else {
        StepStatus::Unreachable
    };
    Box::new(PrunedBug {
        path,
        idx: 1,
        snap,
        status,
    })
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let path = bug1_path(grid, start, goal)
        .map(|p| prune_cycles(&p))
        .unwrap_or_else(|| vec![start]);
    finish(start, goal, path)
}

pub fn build_bug2(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let path = bug2_path(grid, start, goal)
        .map(|p| prune_cycles(&p))
        .unwrap_or_else(|| vec![start]);
    finish(start, goal, path)
}

pub fn build_distbug(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let path = run_to_path(crate::algorithms::distbug::build, grid, start, goal)
        .map(|p| prune_cycles(&p))
        .unwrap_or_else(|| vec![start]);
    finish(start, goal, path)
}

pub fn build_tangentbug(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let path = run_to_path(crate::algorithms::tangentbug::build, grid, start, goal)
        .map(|p| prune_cycles(&p))
        .unwrap_or_else(|| vec![start]);
    finish(start, goal, path)
}

fn best_of(candidates: Vec<Option<Vec<(i32, i32)>>>) -> Option<Vec<(i32, i32)>> {
    let mut best: Option<Vec<(i32, i32)>> = None;
    for c in candidates {
        let Some(p) = c.map(|p| prune_cycles(&p)) else {
            continue;
        };
        if p.len() <= 1 {
            continue;
        }
        match &best {
            None => best = Some(p),
            Some(b) if p.len() < b.len() => best = Some(p),
            _ => {}
        }
    }
    best
}

/// PrunedBug1 + PrunedBug2.
pub fn build_best_of_b1_b2(grid: &Grid, s: (i32, i32), g: (i32, i32)) -> Box<dyn Pathfinder> {
    let b = best_of(vec![bug1_path(grid, s, g), bug2_path(grid, s, g)]);
    finish(s, g, b.unwrap_or_else(|| vec![s]))
}

/// PrunedBug1 + PrunedDistBug.
pub fn build_best_of_b1_db(grid: &Grid, s: (i32, i32), g: (i32, i32)) -> Box<dyn Pathfinder> {
    let b = best_of(vec![
        bug1_path(grid, s, g),
        run_to_path(crate::algorithms::distbug::build, grid, s, g),
    ]);
    finish(s, g, b.unwrap_or_else(|| vec![s]))
}

/// PrunedBug1 + PrunedBug2 + PrunedDistBug (skip the slow TangentBug).
pub fn build_best_of_3(grid: &Grid, s: (i32, i32), g: (i32, i32)) -> Box<dyn Pathfinder> {
    let b = best_of(vec![
        bug1_path(grid, s, g),
        bug2_path(grid, s, g),
        run_to_path(crate::algorithms::distbug::build, grid, s, g),
    ]);
    finish(s, g, b.unwrap_or_else(|| vec![s]))
}

/// All four — best quality, slowest (TangentBug blows the 2 ms budget).
pub fn build_best_of(grid: &Grid, s: (i32, i32), g: (i32, i32)) -> Box<dyn Pathfinder> {
    let b = best_of(vec![
        bug1_path(grid, s, g),
        bug2_path(grid, s, g),
        run_to_path(crate::algorithms::distbug::build, grid, s, g),
        run_to_path(crate::algorithms::tangentbug::build, grid, s, g),
    ]);
    finish(s, g, b.unwrap_or_else(|| vec![s]))
}

impl Pathfinder for PrunedBug {
    fn step(&mut self) -> StepStatus {
        if self.status != StepStatus::Running {
            return self.status;
        }
        if self.idx >= self.path.len() {
            self.status = StepStatus::Arrived;
            return self.status;
        }
        let p = self.path[self.idx];
        self.idx += 1;
        self.snap.current = p;
        self.snap.visited.insert(p);
        self.snap.path.push(p);
        if self.idx >= self.path.len() {
            self.status = StepStatus::Arrived;
        }
        self.status
    }

    fn snapshot(&self) -> &Snapshot {
        &self.snap
    }

    fn summary(&self) -> String {
        format!(
            "plan-ahead Bug1 + short arc\nlen: {}\nstep: {}/{}\nstatus: {:?}",
            self.path.len().saturating_sub(1),
            self.idx.min(self.path.len()).saturating_sub(1),
            self.path.len().saturating_sub(1),
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "PrunedBug1"
    }
}
