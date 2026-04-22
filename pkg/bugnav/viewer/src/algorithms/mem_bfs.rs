//! Bounded-memory BFS — memory-aware pathfinding with a hard per-turn cost.
//!
//! Each turn:
//! 1. Sense (reveal cells within `r² ≤ VISION_R_SQ` from current pos).
//! 2. BFS from pos over the belief graph, capped at `BFS_BUDGET` cell
//!    expansions. Belief: in-bounds AND (undiscovered OR not-wall).
//!    Undiscovered is optimistic (treated as passable).
//! 3. Among cells reached by the bounded BFS, pick the one closest to
//!    goal. If strictly closer than current pos, step first cell along
//!    BFS path to it. Else fall back to Bug1.
//!
//! Worst-case per turn: O(BFS_BUDGET) — does not grow with map size or run
//! length. No caching, no replan bursts. This is the pattern production
//! bots use: fixed-budget local search, memory provides the passability
//! graph rather than amortizing work across turns.

use std::collections::{HashMap, HashSet, VecDeque};

use crate::algorithms::bug_common::{
    VISION_R_SQ, WallFollowState, WallStepOutcome, bresenham, dir_to_goal, dist_sq, has_los,
    neighbour, sensed_cells, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

/// Maximum cells BFS is allowed to expand per turn. Larger = better
/// plan quality; smaller = tighter WCET. 500 is ~20× the sensor window
/// and fits in ~sub-ms on a modern CPU.
const BFS_BUDGET: usize = 500;

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

pub struct MemBfs {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    discovered: Vec<bool>,
    // Bug1 state for fallback.
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

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    let discovered = vec![false; (grid.w * grid.h) as usize];
    Box::new(MemBfs {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        discovered,
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

impl MemBfs {
    fn idx(&self, x: i32, y: i32) -> Option<usize> {
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

    /// Belief passability: in-bounds AND (undiscovered OR not-wall).
    fn believed_passable(&self, x: i32, y: i32) -> bool {
        let Some(i) = self.idx(x, y) else { return false };
        !self.discovered[i] || !self.walls[i]
    }

    /// Ground-truth passability (only legitimate for cells within current
    /// sensor range — otherwise we're cheating). Used by Bug1 wall-follow,
    /// which only touches neighbour cells (always sensor-adjacent).
    fn passable(&self, x: i32, y: i32) -> bool {
        let Some(i) = self.idx(x, y) else { return false };
        !self.walls[i]
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.visited.insert(new_pos);
        self.snap.path.push(new_pos);
    }

    /// Bounded BFS over memory + optimistic-unknown, capped at BFS_BUDGET
    /// cell expansions. Returns the first-step cell of the path to the
    /// BFS-reachable cell closest to goal that is strictly closer than pos.
    /// Returns None if no such cell exists within the budget.
    fn try_bfs_step(&mut self, threshold: i32) -> bool {
        let next_step: Option<(i32, i32)> = {
            let mut queue: VecDeque<(i32, i32)> = VecDeque::new();
            let mut parent: HashMap<(i32, i32), (i32, i32)> = HashMap::new();
            queue.push_back(self.pos);
            parent.insert(self.pos, self.pos);
            let mut expansions = 0;
            let mut best: Option<((i32, i32), i32)> = None;
            while let Some(p) = queue.pop_front() {
                expansions += 1;
                if expansions > BFS_BUDGET {
                    break;
                }
                let d = dist_sq(p, self.goal);
                if d < threshold
                    && let Some((_, bd)) = best
                    && d < bd
                {
                    best = Some((p, d));
                } else if d < threshold && best.is_none() {
                    best = Some((p, d));
                }
                for (dx, dy) in DIRS8 {
                    let n = (p.0 + dx, p.1 + dy);
                    if !self.believed_passable(n.0, n.1) {
                        continue;
                    }
                    if parent.contains_key(&n) {
                        continue;
                    }
                    parent.insert(n, p);
                    queue.push_back(n);
                }
            }
            best.and_then(|(target, _)| {
                let mut cur = target;
                let mut next = target;
                while let Some(&p) = parent.get(&cur) {
                    if p == self.pos {
                        next = cur;
                        break;
                    }
                    if p == cur {
                        break; // reached pos (parent of itself)
                    }
                    cur = p;
                }
                if dist_sq(next, self.goal) < threshold {
                    Some(next)
                } else {
                    None
                }
            })
        };
        let Some(step) = next_step else {
            return false;
        };
        self.move_to(step);
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

impl Pathfinder for MemBfs {
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

        // LoS shortcut — within sensor range, memory equals ground truth.
        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        let passable_closure =
            move |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize];
        if has_los(self.pos, self.goal, &passable_closure) {
            let line = bresenham(self.pos, self.goal);
            for &p in line.iter().skip(1) {
                self.move_to(p);
            }
            self.status = StepStatus::Arrived;
            return self.status;
        }

        let threshold = match self.mode {
            Mode::MotionToGoal => dist_sq(self.pos, self.goal),
            Mode::Circumnavigate | Mode::ReturnToLeave => self.best_leave_dist_sq,
        };
        if self.try_bfs_step(threshold) {
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
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\ndiscovered: {}/{} ({:.1}%)\nBFS budget: {}\nsensor r²≤{}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            discovered_count,
            total,
            100.0 * discovered_count as f64 / total as f64,
            BFS_BUDGET,
            VISION_R_SQ,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "Memory+BFS"
    }
}
