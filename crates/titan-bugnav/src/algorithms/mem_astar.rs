//! Memory+A* — identical structure to Memory+BFS but expands cells in order
//! of f = g + h (Chebyshev heuristic). Goal-directed, so fewer expansions
//! reach the same depth; same BFS budget buys a longer effective horizon.

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashSet};

use crate::algorithms::bug_common::{
    VISION_R_SQ, WallFollowState, WallStepOutcome, bresenham, dir_to_goal, dist_sq, has_los,
    neighbour, sensed_cells, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

const EXPAND_BUDGET: u32 = 500;
const DIST_INF: u16 = u16::MAX;

const DIRS8: [(i32, i32); 8] = [
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    Circumnavigate,
    ReturnToLeave,
}

pub struct MemAstar {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    discovered: Vec<bool>,
    pnb: Vec<Vec<u16>>,
    g: Vec<u16>,
    g_reset: Vec<u16>,
    heap: BinaryHeap<Reverse<(u32, u16)>>,
    mode: Mode,
    wf: WallFollowState,
    hit_point: (i32, i32),
    best_leave: (i32, i32),
    best_leave_dist_sq: i32,
    global_min_dist_sq: i32,
    follow_visited: HashSet<((i32, i32), (i32, i32), bool)>,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

#[must_use]
pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let w = grid.w;
    let h = grid.h;
    let n = (w * h) as usize;

    let mut pnb: Vec<Vec<u16>> = vec![Vec::with_capacity(8); n];
    for y in 0..h {
        for x in 0..w {
            let i = (y * w + x) as usize;
            for (dx, dy) in DIRS8 {
                let nx = x + dx;
                let ny = y + dy;
                if nx >= 0 && nx < w && ny >= 0 && ny < h {
                    let ni = (ny * w + nx) as u16;
                    pnb[i].push(ni);
                }
            }
        }
    }

    let g_reset = vec![DIST_INF; n];
    let g = g_reset.clone();

    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);

    Box::new(MemAstar {
        grid_w: w,
        grid_h: h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        discovered: vec![false; n],
        pnb,
        g,
        g_reset,
        heap: BinaryHeap::with_capacity(4096),
        mode: Mode::MotionToGoal,
        wf: WallFollowState {
            pos: start,
            current_obstacle: start,
            obstacle_on_right: true,
        },
        hit_point: start,
        best_leave: start,
        best_leave_dist_sq: dist_sq(start, goal),
        global_min_dist_sq: dist_sq(start, goal),
        follow_visited: HashSet::new(),
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

impl MemAstar {
    #[inline]
    const fn idx(&self, x: i32, y: i32) -> Option<usize> {
        if x < 0 || y < 0 || x >= self.grid_w || y >= self.grid_h {
            None
        } else {
            Some((y * self.grid_w + x) as usize)
        }
    }

    #[inline]
    const fn cell_of(&self, i: usize) -> (i32, i32) {
        let w = self.grid_w;
        ((i as i32) % w, (i as i32) / w)
    }

    #[inline]
    fn h(&self, idx: usize) -> u32 {
        let (nx, ny) = self.cell_of(idx);
        let dx = (nx - self.goal.0).unsigned_abs();
        let dy = (ny - self.goal.1).unsigned_abs();
        dx.max(dy)
    }

    fn sense(&mut self) {
        for c in sensed_cells(self.pos) {
            let Some(i) = self.idx(c.0, c.1) else {
                continue;
            };
            if self.discovered[i] {
                continue;
            }
            self.discovered[i] = true;
            if self.walls[i] {
                let (x, y) = self.cell_of(i);
                let i_u16 = i as u16;
                for (dx, dy) in DIRS8 {
                    let nx = x + dx;
                    let ny = y + dy;
                    if nx >= 0 && nx < self.grid_w && ny >= 0 && ny < self.grid_h {
                        let ni = (ny * self.grid_w + nx) as usize;
                        self.pnb[ni].retain(|&c| c != i_u16);
                    }
                }
                self.pnb[i].clear();
            }
        }
    }

    fn passable(&self, x: i32, y: i32) -> bool {
        let Some(i) = self.idx(x, y) else {
            return false;
        };
        !self.walls[i]
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.visited.insert(new_pos);
        self.snap.path.push(new_pos);
    }

    /// Bounded A* over `pnb` starting at `self.pos`. Returns the first-step
    /// cell along the path to the cell that minimises `dist_sq(c, goal)`
    /// subject to `< threshold`. Unconditionally commits if goal reached.
    fn try_astar_step(&mut self, threshold: i32) -> bool {
        let pos_idx = self
            .idx(self.pos.0, self.pos.1)
            .expect("pos must be in-bounds");

        self.g.copy_from_slice(&self.g_reset);
        self.g[pos_idx] = 0;

        self.heap.clear();
        self.heap.push(Reverse((self.h(pos_idx), pos_idx as u16)));

        let mut expansions: u32 = 0;
        let mut best_idx: Option<usize> = None;
        let mut best_d: i32 = threshold;
        let mut reached_goal = false;
        let goal_idx = self.idx(self.goal.0, self.goal.1);

        while let Some(Reverse((f, node_u16))) = self.heap.pop() {
            let node = node_u16 as usize;
            let node_g = self.g[node];
            if node_g == DIST_INF {
                continue;
            }
            // Stale entry (node was relaxed after this was pushed).
            if f as u16 > node_g.saturating_add(self.h(node) as u16) {
                continue;
            }

            expansions += 1;
            if expansions > EXPAND_BUDGET {
                break;
            }

            if Some(node) == goal_idx {
                reached_goal = true;
                best_idx = Some(node);
                break;
            }
            let (nx, ny) = self.cell_of(node);
            let dx = nx - self.goal.0;
            let dy = ny - self.goal.1;
            let d = dx * dx + dy * dy;
            if d < best_d {
                best_d = d;
                best_idx = Some(node);
            }

            let g_new = node_g + 1;
            let pnb_len = self.pnb[node].len();
            for k in 0..pnb_len {
                let ni_u16 = self.pnb[node][k];
                let ni = ni_u16 as usize;
                if g_new < self.g[ni] {
                    self.g[ni] = g_new;
                    let f_ni = u32::from(g_new) + self.h(ni);
                    self.heap.push(Reverse((f_ni, ni_u16)));
                }
            }
        }

        let Some(target) = best_idx else {
            return false;
        };

        // Gradient-descent on g back to a cell adjacent to pos.
        let mut cur = target;
        while self.g[cur] > 1 {
            let cur_g = self.g[cur];
            let mut next_cell: Option<usize> = None;
            for &ni_u16 in &self.pnb[cur] {
                let ni = ni_u16 as usize;
                if self.g[ni] == cur_g - 1 {
                    next_cell = Some(ni);
                    break;
                }
            }
            let Some(n) = next_cell else {
                return false;
            };
            cur = n;
        }
        if self.g[cur] == DIST_INF {
            return false;
        }
        if cur == pos_idx {
            return false;
        }
        let first_step = self.cell_of(cur);

        if !reached_goal {
            let fs_d = dist_sq(first_step, self.goal);
            if fs_d >= threshold {
                return false;
            }
        }

        self.move_to(first_step);
        let d2 = dist_sq(self.pos, self.goal);
        if d2 < self.global_min_dist_sq {
            self.global_min_dist_sq = d2;
        }
        true
    }

    fn step_wall_follow(&mut self) -> WallStepOutcome {
        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        let passable =
            |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize];
        let on_map = |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h;
        let outcome = wall_follow_step(&mut self.wf, passable, on_map);
        if outcome == WallStepOutcome::Moved {
            self.move_to(self.wf.pos);
        }
        outcome
    }

    fn enter_circumnavigate(&mut self, blocked_dir: usize) {
        self.mode = Mode::Circumnavigate;
        self.wf = WallFollowState {
            pos: self.pos,
            current_obstacle: neighbour(self.pos, blocked_dir),
            obstacle_on_right: true,
        };
        self.hit_point = self.pos;
        self.best_leave = self.pos;
        self.best_leave_dist_sq = dist_sq(self.pos, self.goal);
        self.follow_visited.clear();
        self.follow_visited.insert((
            self.wf.pos,
            self.wf.current_obstacle,
            self.wf.obstacle_on_right,
        ));
    }
}

impl Pathfinder for MemAstar {
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

        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        let passable_closure = move |x: i32, y: i32| {
            x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize]
        };
        if has_los(self.pos, self.goal, passable_closure) {
            let line = bresenham(self.pos, self.goal);
            for &p in line.iter().skip(1) {
                self.move_to(p);
            }
            self.status = StepStatus::Arrived;
            return self.status;
        }

        let threshold = match self.mode {
            Mode::MotionToGoal => dist_sq(self.pos, self.goal),
            Mode::Circumnavigate | Mode::ReturnToLeave => {
                self.global_min_dist_sq.min(self.best_leave_dist_sq)
            }
        };
        if self.try_astar_step(threshold) {
            if self.mode != Mode::MotionToGoal {
                self.mode = Mode::MotionToGoal;
                self.follow_visited.clear();
            }
            return self.status;
        }

        match self.mode {
            Mode::MotionToGoal => {
                let d = dir_to_goal(self.pos, self.goal);
                let np = neighbour(self.pos, d);
                if self.passable(np.0, np.1) {
                    self.move_to(np);
                    let d2 = dist_sq(self.pos, self.goal);
                    if d2 < self.global_min_dist_sq {
                        self.global_min_dist_sq = d2;
                    }
                } else {
                    self.enter_circumnavigate(d);
                }
            }
            Mode::Circumnavigate => {
                match self.step_wall_follow() {
                    WallStepOutcome::Moved => {}
                    WallStepOutcome::Surrounded => {
                        self.status = StepStatus::Unreachable;
                        return self.status;
                    }
                }
                let d2 = dist_sq(self.pos, self.goal);
                if d2 < self.best_leave_dist_sq {
                    self.best_leave = self.pos;
                    self.best_leave_dist_sq = d2;
                }
                let state = (
                    self.wf.pos,
                    self.wf.current_obstacle,
                    self.wf.obstacle_on_right,
                );
                if !self.follow_visited.insert(state) {
                    if self.best_leave_dist_sq >= self.global_min_dist_sq {
                        self.status = StepStatus::Unreachable;
                        return self.status;
                    }
                    self.global_min_dist_sq = self.best_leave_dist_sq;
                    self.mode = Mode::ReturnToLeave;
                    self.follow_visited.clear();
                    self.follow_visited.insert((
                        self.wf.pos,
                        self.wf.current_obstacle,
                        self.wf.obstacle_on_right,
                    ));
                }
            }
            Mode::ReturnToLeave => {
                if self.pos == self.best_leave {
                    self.mode = Mode::MotionToGoal;
                    return self.status;
                }
                match self.step_wall_follow() {
                    WallStepOutcome::Moved => {}
                    WallStepOutcome::Surrounded => {
                        self.status = StepStatus::Unreachable;
                        return self.status;
                    }
                }
                let state = (
                    self.wf.pos,
                    self.wf.current_obstacle,
                    self.wf.obstacle_on_right,
                );
                if !self.follow_visited.insert(state) {
                    self.status = StepStatus::Unreachable;
                }
            }
        }
        self.status
    }

    fn snapshot(&self) -> &Snapshot {
        &self.snap
    }

    fn summary(&self) -> String {
        let discovered_count = self.discovered.iter().filter(|&&d| d).count();
        let total = self.discovered.len();
        format!(
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\ndiscovered: {}/{} ({:.1}%)\nA* budget: {}\nsensor r²≤{}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            discovered_count,
            total,
            100.0 * discovered_count as f64 / total as f64,
            EXPAND_BUDGET,
            VISION_R_SQ,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "Memory+A*"
    }
}
