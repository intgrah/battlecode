use crate::algorithms::bug_common::{
    DIR_NAMES, dir_to_goal, dist_sq, follow_step, neighbour, rot_cw_90,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    /// Full loop around the obstacle, tracking the cell closest to goal.
    Circumnavigate,
    /// Follow the boundary again (same direction) until we reach best_leave.
    ReturnToLeave,
}

pub struct Bug1 {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    follow_dir: usize,
    hit_point: (i32, i32),
    best_leave: (i32, i32),
    best_leave_dist_sq: i32,
    /// Number of steps taken in the current Follow phase; used to detect returning
    /// to `hit_point` (avoids false positives on the very first step).
    follow_steps: u32,
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
    Box::new(Bug1 {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        mode: Mode::MotionToGoal,
        follow_dir: 0,
        hit_point: start,
        best_leave: start,
        best_leave_dist_sq: dist_sq(start, goal),
        follow_steps: 0,
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

    fn wall_step(&mut self) -> bool {
        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        let passable = |x: i32, y: i32| {
            x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize]
        };
        if let Some((np, nd)) = follow_step(self.pos, self.follow_dir, passable) {
            self.follow_dir = nd;
            self.move_to(np);
            true
        } else {
            false
        }
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

        match self.mode {
            Mode::MotionToGoal => {
                let d = dir_to_goal(self.pos, self.goal);
                let np = neighbour(self.pos, d);
                if self.passable(np.0, np.1) {
                    self.move_to(np);
                } else {
                    self.mode = Mode::Circumnavigate;
                    self.follow_dir = rot_cw_90(d);
                    self.hit_point = self.pos;
                    self.best_leave = self.pos;
                    self.best_leave_dist_sq = dist_sq(self.pos, self.goal);
                    self.follow_steps = 0;
                }
            }
            Mode::Circumnavigate => {
                if !self.wall_step() {
                    self.status = StepStatus::Unreachable;
                    return self.status;
                }
                self.follow_steps += 1;
                let d2 = dist_sq(self.pos, self.goal);
                if d2 < self.best_leave_dist_sq {
                    self.best_leave = self.pos;
                    self.best_leave_dist_sq = d2;
                }
                // Completed a full loop — switch to returning to the leave point.
                if self.pos == self.hit_point && self.follow_steps > 0 {
                    if self.best_leave == self.hit_point {
                        // Closest boundary point is the hit point itself and motion-to-goal
                        // is blocked there — goal is unreachable around this obstacle.
                        self.status = StepStatus::Unreachable;
                        return self.status;
                    }
                    self.mode = Mode::ReturnToLeave;
                }
            }
            Mode::ReturnToLeave => {
                if self.pos == self.best_leave {
                    // At leave point — try to resume motion-to-goal.
                    let d = dir_to_goal(self.pos, self.goal);
                    let np = neighbour(self.pos, d);
                    if self.passable(np.0, np.1) {
                        self.mode = Mode::MotionToGoal;
                        self.move_to(np);
                    } else {
                        self.status = StepStatus::Unreachable;
                    }
                } else if !self.wall_step() {
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
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nfollow_dir: {}\nhit: ({}, {})\nbest_leave: ({}, {})\nbest_d2: {}\nfollow_steps: {}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            DIR_NAMES[self.follow_dir],
            self.hit_point.0,
            self.hit_point.1,
            self.best_leave.0,
            self.best_leave.1,
            self.best_leave_dist_sq,
            self.follow_steps,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "Bug1"
    }
}
