//! Hybrid BFS + Bug1. Each step, first try a local BFS over the 69-cell
//! sensor window — if it finds a passable cell strictly closer to goal
//! than current pos, step along the BFS path to it. Otherwise fall back
//! to Bug1's canonical wall-following logic. The local BFS handles small
//! detours cleanly (shorter paths than pure Bug1); Bug1's circumnavigation
//! + progress check guarantees completeness when the sensor can't see
//! past an obstacle.
//!
//! BFS is the micro-planner, Bug1 is the macro-planner / completeness
//! guarantee.

use std::collections::HashSet;

use crate::algorithms::bug_common::{
    WallFollowState, WallStepOutcome, bresenham, dir_to_goal, dist_sq, has_los, local_bfs,
    neighbour, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    Circumnavigate,
    ReturnToLeave,
}

pub struct BfsBug {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    wf: WallFollowState,
    hit_point: (i32, i32),
    best_leave: (i32, i32),
    best_leave_dist_sq: i32,
    global_min_dist_sq: i32,
    follow_visited: HashSet<((i32, i32), (i32, i32), bool)>,
    /// Cells visited while in Motion mode (since the last Bug1 transition).
    /// Prevents BFS from stepping into a recently-walked cell, which
    /// would otherwise oscillate when the first-step strictness is relaxed.
    /// Cleared whenever we enter or leave Circumnavigate.
    motion_visited: HashSet<(i32, i32)>,
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
    Box::new(BfsBug {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
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
        motion_visited: {
            let mut s = HashSet::new();
            s.insert(start);
            s
        },
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

impl BfsBug {
    fn passable(&self, x: i32, y: i32) -> bool {
        if x < 0 || y < 0 || x >= self.grid_w || y >= self.grid_h {
            return false;
        }
        !self.walls[(y * self.grid_w + x) as usize]
    }

    fn passable_closure(&self) -> impl Fn(i32, i32) -> bool + use<'_> {
        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        move |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize]
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.visited.insert(new_pos);
        self.snap.path.push(new_pos);
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
        self.motion_visited.clear();
        self.motion_visited.insert(self.pos);
    }

    /// Try local BFS within sensor range. If any reachable cell is strictly
    /// closer to goal than current pos, step the first cell along the BFS
    /// path to the best such cell. Returns true on step.
    /// Run local BFS and take the first step along the path to the closest-to-goal
    /// reachable cell. Only accepts the step if:
    /// - A reachable BFS cell has `dist_sq(c, goal) < threshold`.
    /// - The first step itself has `dist_sq(next, goal) < threshold`.
    ///
    /// In Motion mode, pass `threshold = dist_sq(pos, goal)` — strict per-step
    /// progress. In ReturnToLeave mode, pass `threshold = best_leave_dist_sq`
    /// — we only abandon the retrace if BFS finds a cell strictly better than
    /// Bug1's already-identified leave point, preserving completeness.
    fn try_bfs_step(&mut self, threshold: i32) -> bool {
        let next_step: Option<(i32, i32)> = {
            let passable = self.passable_closure();
            let parent = local_bfs(self.pos, &passable);
            let mut best_target: Option<((i32, i32), i32)> = None;
            for (&c, _) in &parent {
                let d = dist_sq(c, self.goal);
                if d >= threshold {
                    continue;
                }
                match best_target {
                    None => best_target = Some((c, d)),
                    Some((_, bd)) if d < bd => best_target = Some((c, d)),
                    _ => {}
                }
            }
            best_target.and_then(|(target, _)| {
                let mut cur = target;
                let mut next = target;
                while let Some(&p) = parent.get(&cur) {
                    if p == self.pos {
                        next = cur;
                        break;
                    }
                    cur = p;
                }
                // If BFS reaches the goal itself within the sensor, take
                // the first step unconditionally — we're committing to a
                // fully-seen path to goal. Otherwise require the first
                // step to be strictly closer than threshold to avoid
                // oscillation into blind pockets.
                if target == self.goal {
                    Some(next)
                } else if dist_sq(next, self.goal) < threshold {
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
        self.motion_visited.insert(step);
        let d2 = dist_sq(self.pos, self.goal);
        if d2 < self.global_min_dist_sq {
            self.global_min_dist_sq = d2;
        }
        true
    }
}

impl Pathfinder for BfsBug {
    fn step(&mut self) -> StepStatus {
        if self.status != StepStatus::Running {
            return self.status;
        }
        if self.pos == self.goal {
            self.status = StepStatus::Arrived;
            return self.status;
        }
        self.steps += 1;

        // LoS shortcut: if goal is sensor-visible, jump straight there.
        let passable = self.passable_closure();
        if has_los(self.pos, self.goal, &passable) {
            drop(passable);
            let line = bresenham(self.pos, self.goal);
            for &p in line.iter().skip(1) {
                self.move_to(p);
            }
            self.status = StepStatus::Arrived;
            return self.status;
        }
        drop(passable);

        // BFS shortcut, mode-dependent threshold:
        // - Motion: threshold = dist(pos, goal). Strict per-step progress.
        // - Circumnavigate / ReturnToLeave: threshold = best_leave_dist_sq.
        //   Only abandon the wall-follow if BFS finds a cell strictly
        //   better than Bug1's current best leave candidate. This preserves
        //   Bug1's progress invariant (global_min strictly decreases).
        //   Cycle detection is bypassed only when BFS succeeds — which
        //   necessarily means progress, so no infinite loop risk.
        let threshold = match self.mode {
            Mode::MotionToGoal => dist_sq(self.pos, self.goal),
            // During Circumnavigate/ReturnToLeave, only break out on
            // GLOBAL progress (not just within-circumnavigation progress).
            // Using best_leave_dist_sq allowed break-outs at cells that
            // weren't strictly below global_min, letting the algorithm
            // re-enter Circumnavigate repeatedly at similar cells without
            // real progress.
            Mode::Circumnavigate | Mode::ReturnToLeave => {
                self.global_min_dist_sq.min(self.best_leave_dist_sq)
            }
        };
        if self.try_bfs_step(threshold) {
            if self.mode != Mode::MotionToGoal {
                self.mode = Mode::MotionToGoal;
                self.follow_visited.clear();
                self.motion_visited.clear();
                self.motion_visited.insert(self.pos);
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
        format!(
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nhit: ({}, {})\nbest_leave: ({}, {})\nbest_d2: {}\nglobal_min_d2: {}\nobstacle: ({}, {})\nside: {}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            self.hit_point.0,
            self.hit_point.1,
            self.best_leave.0,
            self.best_leave.1,
            self.best_leave_dist_sq,
            self.global_min_dist_sq,
            self.wf.current_obstacle.0,
            self.wf.current_obstacle.1,
            if self.wf.obstacle_on_right { "R" } else { "L" },
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "BFS+Bug1"
    }
}
