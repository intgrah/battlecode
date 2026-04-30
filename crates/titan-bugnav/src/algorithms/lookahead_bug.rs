//! The algorithm:
//!   1. Maintain a simulated position `bug_pos` that runs ahead of the real
//!      agent by up to 6 steps per call. Simulation is greedy (pick neighbour
//!      closest to target with penalty tie-break), switching to bug mode
//!      (wall-follow CW or CCW) when stuck.
//!   2. After simulating, run a small BFS flood (3 iterations) seeded at
//!      `bug_pos`, computing distances to each of the real agent's
//!      8 neighbours + self.
//!   3. Pick the neighbour direction that minimises `(penalty, bfs_dist,
//!      bug_dist)`, rejecting directions that don't improve BFS distance
//!      over staying put. Fallbacks: walk the bug-path trail backward,
//!      step toward the average trail centroid, or any passable direction.
//!
//! Passability is PESSIMISTIC on unseen cells: only seen-and-not-wall is
//! considered passable.

use std::collections::{HashMap, HashSet, VecDeque};

use crate::algorithms::bug_common::{DIRS, VISION_R_SQ, dist_sq, sensed_cells};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

const SIM_STEPS: u32 = 6;
const MAX_PATH_BACKUP: usize = 50;
const BFS_ITERS: u32 = 3;
const INF_DIST: u32 = 100_000;

pub struct LookaheadBug {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    discovered: Vec<bool>,
    // Simulation state
    bug_pos: (i32, i32),
    bug_dir: usize, // direction index 0..8
    clockwise: bool,
    should_guess_rotation: bool,
    best_bug_dist: i32,
    should_bug: bool,
    bug_path: Vec<(i32, i32)>,
    full_map: bool,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

#[must_use]
pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, false)
}

/// Variant that starts with all cells discovered — simulates a bot that
/// has already explored the whole map via prior exploration tasks.
#[must_use]
pub fn build_full_map(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, true)
}

fn build_inner(
    grid: &Grid,
    start: (i32, i32),
    goal: (i32, i32),
    full_map: bool,
) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    let n = (grid.w * grid.h) as usize;
    Box::new(LookaheadBug {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        discovered: vec![full_map; n],
        bug_pos: start,
        bug_dir: 0,
        clockwise: false,
        should_guess_rotation: true,
        best_bug_dist: i32::MAX,
        should_bug: false,
        bug_path: Vec::with_capacity(MAX_PATH_BACKUP),
        full_map,
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

const fn dir_to_cell(from: (i32, i32), to: (i32, i32)) -> usize {
    let dx = (to.0 - from.0).signum();
    let dy = (to.1 - from.1).signum();
    match (dx, dy) {
        (0, -1) => 0,
        (1, -1) => 1,
        (1, 0) => 2,
        (1, 1) => 3,
        (0, 1) => 4,
        (-1, 1) => 5,
        (-1, 0) => 6,
        (-1, -1) => 7,
        _ => 0,
    }
}

const fn rotate_right(d: usize) -> usize {
    (d + 1) % 8
}
const fn rotate_left(d: usize) -> usize {
    (d + 7) % 8
}

const fn adjacent(a: (i32, i32), b: (i32, i32)) -> bool {
    dist_sq(a, b) <= 2
}

impl LookaheadBug {
    const fn idx(&self, x: i32, y: i32) -> Option<usize> {
        if x < 0 || y < 0 || x >= self.grid_w || y >= self.grid_h {
            None
        } else {
            Some((y * self.grid_w + x) as usize)
        }
    }

    fn sense(&mut self) {
        for c in sensed_cells(self.pos) {
            if let Some(i) = self.idx(c.0, c.1) {
                self.discovered[i] = true;
            }
        }
    }

    /// PESSIMISTIC: unseen cells are considered impassable. Matches
    fn believed_passable(&self, p: (i32, i32)) -> bool {
        if p == self.pos {
            return true;
        }
        let Some(i) = self.idx(p.0, p.1) else {
            return false;
        };
        self.discovered[i] && !self.walls[i]
    }

    const fn in_vision(&self, p: (i32, i32)) -> bool {
        dist_sq(self.pos, p) <= VISION_R_SQ
    }

    const fn score_tile(&self, _p: (i32, i32)) -> i32 {
        0
    }

    fn reset(&mut self, target: (i32, i32)) {
        self.best_bug_dist = i32::MAX;
        self.should_bug = false;
        self.goal = target;
        self.bug_pos = self.pos;
        self.bug_dir = 0;
        self.should_guess_rotation = true;
        self.clockwise = false;
        self.bug_path.clear();
    }

    fn append_trail(&mut self) {
        if self.bug_path.len() >= MAX_PATH_BACKUP {
            return;
        }
        if self.bug_path.last() == Some(&self.bug_pos) {
            return;
        }
        self.bug_path.push(self.bug_pos);
    }

    /// Walk the trail backward and pick the most-recent position still in
    /// vision. If none, reset.
    fn resync_bug_pos(&mut self) {
        for i in (0..self.bug_path.len()).rev() {
            if self.in_vision(self.bug_path[i]) {
                self.bug_pos = self.bug_path[i];
                return;
            }
        }
        // None visible → full reset
        let g = self.goal;
        self.reset(g);
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.visited.insert(new_pos);
        self.snap.path.push(new_pos);
    }

    /// Try to advance the simulated position one step via greedy distance +
    /// penalty tie-break. Returns true if the simulation should stop (hit
    /// vision edge) — the caller should break out of the loop.
    fn greedy_step(&mut self) -> bool {
        let target = self.goal;
        let mut best_dist = dist_sq(self.bug_pos, target);
        let mut best_penalty = self.score_tile(self.bug_pos);
        let mut best_loc = self.bug_pos;

        for di in 0..8 {
            let new_loc = (self.bug_pos.0 + DIRS[di].0, self.bug_pos.1 + DIRS[di].1);
            if !self.in_vision(new_loc) {
                // Edge of vision — stop simulating.
                return true;
            }
            if !self.believed_passable(new_loc) {
                continue;
            }
            let nd = dist_sq(new_loc, target);
            let penalty = self.score_tile(new_loc);
            let should_update = if nd == best_dist {
                penalty < best_penalty
            } else {
                nd < best_dist
            };
            if should_update {
                best_dist = nd;
                best_penalty = penalty;
                best_loc = new_loc;
            }
        }

        if best_loc == self.bug_pos {
            // Greedy stuck → switch to bug mode.
            self.best_bug_dist = dist_sq(self.bug_pos, target);
            self.bug_dir = dir_to_cell(self.bug_pos, target);
            self.should_bug = true;
        } else {
            self.bug_pos = best_loc;
        }
        false
    }

    fn bug_step(&mut self) -> bool {
        let target = self.goal;

        if self.should_guess_rotation {
            self.should_guess_rotation = false;
            // Probe left: rotate CCW until passable
            let mut dir_l = self.bug_dir;
            for _ in 0..8 {
                let test = (
                    self.bug_pos.0 + DIRS[dir_l].0,
                    self.bug_pos.1 + DIRS[dir_l].1,
                );
                if self.believed_passable(test) {
                    break;
                }
                dir_l = rotate_left(dir_l);
            }
            // Probe right: rotate CW until passable
            let mut dir_r = self.bug_dir;
            for _ in 0..8 {
                let test = (
                    self.bug_pos.0 + DIRS[dir_r].0,
                    self.bug_pos.1 + DIRS[dir_r].1,
                );
                if self.believed_passable(test) {
                    break;
                }
                dir_r = rotate_right(dir_r);
            }
            let loc_l = (
                self.bug_pos.0 + DIRS[dir_l].0,
                self.bug_pos.1 + DIRS[dir_l].1,
            );
            let loc_r = (
                self.bug_pos.0 + DIRS[dir_r].0,
                self.bug_pos.1 + DIRS[dir_r].1,
            );
            self.clockwise = dist_sq(loc_r, target) < dist_sq(loc_l, target);
        }

        // Try current bug direction
        let mut current_loc: Option<(i32, i32)> = None;
        let new_loc = (
            self.bug_pos.0 + DIRS[self.bug_dir].0,
            self.bug_pos.1 + DIRS[self.bug_dir].1,
        );
        if !self.in_vision(new_loc) {
            return true;
        }
        if self.believed_passable(new_loc) {
            current_loc = Some(new_loc);
        }

        if current_loc.is_none() {
            for _ in 0..8 {
                self.bug_dir = if self.clockwise {
                    rotate_right(self.bug_dir)
                } else {
                    rotate_left(self.bug_dir)
                };
                let probe = (
                    self.bug_pos.0 + DIRS[self.bug_dir].0,
                    self.bug_pos.1 + DIRS[self.bug_dir].1,
                );
                if !self.in_vision(probe) {
                    return true;
                }
                if self.believed_passable(probe) {
                    current_loc = Some(probe);
                    break;
                }
            }
        }

        if let Some(cur) = current_loc
            && cur != self.bug_pos
        {
            self.bug_pos = cur;
            // Rotate direction back toward the wall
            self.bug_dir = if self.clockwise {
                rotate_left(self.bug_dir)
            } else {
                rotate_right(self.bug_dir)
            };
            let d = dist_sq(self.bug_pos, target);
            if d < self.best_bug_dist {
                // Improved — leave bug mode
                self.should_bug = false;
            }
        }
        false
    }

    /// BFS flood from `bug_pos`, up to `BFS_ITERS` iterations. Returns a map
    /// from direction-index (0..8 plus 8 for CENTRE) to BFS distance from
    /// `bug_pos` to (pos + direction).
    fn validator_on_direction(&self) -> [u32; 9] {
        let mut result = [INF_DIST; 9];
        // Build neighbour positions of self.pos for each direction + centre.
        let mut neighbour_positions: [Option<(i32, i32)>; 9] = [None; 9];
        for di in 0..8 {
            let p = (self.pos.0 + DIRS[di].0, self.pos.1 + DIRS[di].1);
            if self.idx(p.0, p.1).is_some() {
                neighbour_positions[di] = Some(p);
            }
        }
        neighbour_positions[8] = Some(self.pos); // CENTRE

        let start = self.bug_pos;
        let mut visited: HashSet<(i32, i32)> = HashSet::new();
        visited.insert(start);
        let mut frontier: Vec<(i32, i32)> = vec![start];

        // Check if start itself matches a neighbour position.
        for (di, np_opt) in neighbour_positions.iter().enumerate() {
            if let Some(np) = np_opt
                && *np == start
            {
                result[di] = 0;
            }
        }

        for iteration in 1..=BFS_ITERS {
            let mut next_frontier: Vec<(i32, i32)> = Vec::new();
            for &(cx, cy) in &frontier {
                for dd in 0..8 {
                    let nx = cx + DIRS[dd].0;
                    let ny = cy + DIRS[dd].1;
                    let n = (nx, ny);
                    if visited.contains(&n) {
                        continue;
                    }
                    if !self.believed_passable(n) {
                        continue;
                    }
                    visited.insert(n);
                    next_frontier.push(n);
                    for (di, np_opt) in neighbour_positions.iter().enumerate() {
                        if let Some(np) = np_opt
                            && *np == n
                            && iteration < result[di]
                        {
                            result[di] = iteration;
                        }
                    }
                }
            }
            frontier = next_frontier;
            if frontier.is_empty() {
                break;
            }
            // Early exit: all neighbour positions reached.
            let mut all_reached = true;
            for (di, np_opt) in neighbour_positions.iter().enumerate() {
                if np_opt.is_some() && result[di] == INF_DIST {
                    all_reached = false;
                    break;
                }
            }
            if all_reached {
                break;
            }
        }
        result
    }
}

impl Pathfinder for LookaheadBug {
    fn step(&mut self) -> StepStatus {
        if self.status != StepStatus::Running {
            return self.status;
        }
        if self.pos == self.goal {
            self.status = StepStatus::Arrived;
            return self.status;
        }
        self.steps += 1;

        self.sense();

        // Adjacent short-circuit
        if adjacent(self.pos, self.goal) {
            let d = dir_to_cell(self.pos, self.goal);
            let np = (self.pos.0 + DIRS[d].0, self.pos.1 + DIRS[d].1);
            if self.believed_passable(np) {
                self.move_to(np);
                return self.status;
            }
        }

        // Re-sync simulated position from trail.
        self.resync_bug_pos();

        // Cap trail at MAX_PATH_BACKUP by resetting when full.
        if self.bug_path.len() >= MAX_PATH_BACKUP {
            let g = self.goal;
            self.reset(g);
        }

        // Simulation loop
        for _ in 0..SIM_STEPS {
            if adjacent(self.bug_pos, self.goal) {
                break;
            }
            let stop = if self.should_bug {
                self.bug_step()
            } else {
                self.greedy_step()
            };
            if stop {
                break;
            }
            self.append_trail();
        }

        // BFS flood
        let bfs_dists = self.validator_on_direction();
        let center_bfs = bfs_dists[8];
        let center_bug_dist = dist_sq(self.pos, self.bug_pos);

        // Direction selection
        let mut best_dir: Option<usize> = None;
        let mut backup_dir: Option<usize> = None;
        let mut best_penalty: i32 = i32::MAX;
        let mut best_dist: u32 = INF_DIST;
        let mut best_bug_d: i32 = i32::MAX;

        for d in 0..8 {
            let n_pos = (self.pos.0 + DIRS[d].0, self.pos.1 + DIRS[d].1);
            if !self.believed_passable(n_pos) {
                continue;
            }
            backup_dir = Some(d);

            let dist_val = bfs_dists[d];
            let penalty = self.score_tile(n_pos);
            let bug_d = dist_sq(n_pos, self.bug_pos);

            // Must improve on staying put.
            if dist_val >= center_bfs {
                continue;
            }
            if dist_val == center_bfs && bug_d >= center_bug_dist {
                continue;
            }

            // Tie-break: (penalty, bfs_dist, bug_dist)
            let should_update = if penalty != best_penalty {
                penalty < best_penalty
            } else if dist_val != best_dist {
                dist_val < best_dist
            } else {
                bug_d < best_bug_d
            };
            if should_update {
                best_dir = Some(d);
                best_dist = dist_val;
                best_bug_d = bug_d;
                best_penalty = penalty;
            }
        }

        let mut chosen_dir = best_dir;

        // Fallback 1: trail replay (walk backward along simulated trail)
        if chosen_dir.is_none() && self.bug_path.len() >= 2 {
            for i in (0..self.bug_path.len() - 1).rev() {
                if self.bug_path[i] != self.pos {
                    continue;
                }
                let next_pos = self.bug_path[i + 1];
                let candidate = dir_to_cell(self.pos, next_pos);
                let step = (
                    self.pos.0 + DIRS[candidate].0,
                    self.pos.1 + DIRS[candidate].1,
                );
                if step != next_pos {
                    continue;
                }
                if !self.believed_passable(next_pos) {
                    continue;
                }
                chosen_dir = Some(candidate);
                break;
            }
        }

        // Fallback 2: average trail centroid direction
        if chosen_dir.is_none() && !self.bug_path.is_empty() {
            let half = &self.bug_path[self.bug_path.len() / 2..];
            if !half.is_empty() {
                let mut sx = 0i64;
                let mut sy = 0i64;
                for &(x, y) in half {
                    sx += i64::from(x);
                    sy += i64::from(y);
                }
                let avg = (
                    (sx / half.len() as i64) as i32,
                    (sy / half.len() as i64) as i32,
                );
                let candidate = dir_to_cell(self.pos, avg);
                let step = (
                    self.pos.0 + DIRS[candidate].0,
                    self.pos.1 + DIRS[candidate].1,
                );
                if self.believed_passable(step) {
                    chosen_dir = Some(candidate);
                }
                let g = self.goal;
                self.reset(g);
            }
        }

        // Fallback 3: any passable direction
        if chosen_dir.is_none() {
            chosen_dir = backup_dir;
        }

        if let Some(d) = chosen_dir {
            let np = (self.pos.0 + DIRS[d].0, self.pos.1 + DIRS[d].1);
            if self.believed_passable(np) {
                self.move_to(np);
            }
        }
        self.status
    }

    fn snapshot(&self) -> &Snapshot {
        &self.snap
    }

    fn summary(&self) -> String {
        let discovered_count = self.discovered.iter().filter(|&&d| d).count();
        format!(
            "pos: ({}, {})\ngoal: ({}, {})\nbug_pos: ({}, {})\nshould_bug: {}\nclockwise: {}\nbest_bug_dist: {}\ntrail: {}\ndiscovered: {}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.bug_pos.0,
            self.bug_pos.1,
            self.should_bug,
            self.clockwise,
            self.best_bug_dist,
            self.bug_path.len(),
            discovered_count,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        if self.full_map {
            "LookaheadBug+FullMap"
        } else {
            "LookaheadBug"
        }
    }
}

// Silence unused warning (HashMap/VecDeque kept imported for potential
// future non-HashSet variants).
const _: fn() -> (HashMap<(i32, i32), (i32, i32)>, VecDeque<(i32, i32)>) =
    || (HashMap::new(), VecDeque::new());
