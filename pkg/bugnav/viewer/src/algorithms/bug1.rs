//! Bug1 (Lumelsky & Stepanov, 1987). Canonical implementation using the
//! `WallFollowState` anchored to a specific obstacle cell — prevents
//! wall-follow drift that the priority-ordered follow_dir approach suffered
//! from. Guaranteed complete on finite grids.

use std::collections::HashSet;

use crate::algorithms::bug_common::{
    WallFollowState, WallStepOutcome, bresenham, dir_to_goal, dist_sq, has_los, neighbour,
    wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    /// Walking the obstacle boundary recording `best_leave`.
    Circumnavigate,
    /// Walking the boundary again to reach `best_leave`.
    ReturnToLeave,
}

pub struct Bug1 {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    /// When true, check `has_los(pos, goal)` at every step and jump straight
    /// to goal if visible. Respects sensor radius (r²≤20) so only fires when
    /// the goal is within ~4.5 cells.
    use_los: bool,
    wf: WallFollowState,
    default_handed: bool,
    hit_point: (i32, i32),
    best_leave: (i32, i32),
    best_leave_dist_sq: i32,
    /// Running minimum of `dist²(pos, goal)` seen across the whole run.
    /// Used as the Bug1 termination criterion: if a circumnavigation's
    /// `best_leave_dist_sq` isn't strictly below this, the goal is unreachable.
    global_min_dist_sq: i32,
    /// `(pos, current_obstacle, obstacle_on_right)` states visited during
    /// the current Circumnavigate/ReturnToLeave walk. Used to detect a
    /// closed loop back to the starting state, which is equivalent to
    /// completing a full circumnavigation.
    follow_visited: HashSet<((i32, i32), (i32, i32), bool)>,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, false, true)
}

pub fn build_ccw(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, false, false)
}

pub fn build_los(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, true, true)
}

pub fn build_los_ccw(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, true, false)
}

fn build_inner(
    grid: &Grid,
    start: (i32, i32),
    goal: (i32, i32),
    use_los: bool,
    obstacle_on_right: bool,
) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    Box::new(Bug1 {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        mode: Mode::MotionToGoal,
        use_los,
        wf: WallFollowState {
            pos: start,
            current_obstacle: start,
            obstacle_on_right,
        },
        default_handed: obstacle_on_right,
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

impl Bug1 {
    fn passable(&self, x: i32, y: i32) -> bool {
        if x < 0 || y < 0 || x >= self.grid_w || y >= self.grid_h {
            return false;
        }
        !self.walls[(y * self.grid_w + x) as usize]
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.visited.insert(new_pos);
        self.snap.path.push(new_pos);
    }

    fn step_wall_follow(&mut self) -> WallStepOutcome {
        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        let passable = |x: i32, y: i32| {
            x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize]
        };
        let on_map = |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h;
        let prev_pos = self.wf.pos;
        let outcome = wall_follow_step(&mut self.wf, passable, on_map);
        if outcome == WallStepOutcome::Moved && self.wf.pos != prev_pos {
            self.move_to(self.wf.pos);
        }
        outcome
    }

    /// Begin circumnavigation of the obstacle at `pos + blocked_dir`.
    fn enter_circumnavigate(&mut self, blocked_dir: usize) {
        self.mode = Mode::Circumnavigate;
        self.wf = WallFollowState {
            pos: self.pos,
            current_obstacle: neighbour(self.pos, blocked_dir),
            obstacle_on_right: self.default_handed,
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

impl Pathfinder for Bug1 {
    fn step(&mut self) -> StepStatus {
        if self.status != StepStatus::Running {
            return self.status;
        }
        if self.pos == self.goal {
            self.status = StepStatus::Arrived;
            return self.status;
        }
        self.steps += 1;

        // LoS shortcut: if the goal is within sensor range (r²≤20) and the
        // Bresenham line is clear, jump straight to it regardless of mode.
        // This is what Bug1+LoS buys over plain Bug1 — you can abandon
        // circumnavigation as soon as the goal comes into sight.
        if self.use_los {
            let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
            let passable =
                |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize];
            if has_los(self.pos, self.goal, &passable) {
                let line = bresenham(self.pos, self.goal);
                for &p in line.iter().skip(1) {
                    self.pos = p;
                    self.snap.current = p;
                    self.snap.visited.insert(p);
                    self.snap.path.push(p);
                }
                self.status = StepStatus::Arrived;
                return self.status;
            }
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
                        // Genuinely surrounded on all sides (with edge-flip
                        // already tried inside wall_follow_step). Cannot
                        // make progress around this obstacle.
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
                let revisit = !self.follow_visited.insert(state);
                if revisit {
                    // Full circumnavigation complete (wall-follow is
                    // deterministic in `(pos, current_obstacle, side)`, so a
                    // revisit means we closed the loop).
                    if self.best_leave_dist_sq >= self.global_min_dist_sq {
                        // No progress possible past this obstacle.
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
                    // At leave point — hand off to MotionToGoal. If the
                    // direction-to-goal step is blocked, MotionToGoal will
                    // re-enter Circumnavigate with the new obstacle's
                    // hit_point. The `global_min_dist_sq` guard prevents
                    // infinite loops across nested obstacles.
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
                    // Looped without reaching best_leave — shouldn't happen
                    // if circumnavigation was clean (wall-follow is
                    // deterministic). Recover safely.
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
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nhit: ({}, {})\nbest_leave: ({}, {})\nbest_d2: {}\nglobal_min_d2: {}\nobstacle: ({}, {})\nside: {}\nfollow_visited: {}\nsteps: {}\nstatus: {:?}",
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
            self.follow_visited.len(),
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        if self.use_los { "Bug1+LoS" } else { "Bug1" }
    }
}
