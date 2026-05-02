use std::collections::HashSet;

use crate::algorithms::bug_common::{
    WallFollowState, WallStepOutcome, dir_to_goal, dist_sq, neighbour, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    Follow,
}

pub struct Bug2 {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    start: (i32, i32),
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    wf: WallFollowState,
    default_handed: bool,
    hit_point: (i32, i32),
    hit_dist_sq: i32,
    /// Seen wall-follow states to detect closed loops.
    follow_visited: HashSet<((i32, i32), (i32, i32), bool)>,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

#[must_use]
pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, true)
}

#[must_use]
pub fn build_ccw(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, false)
}

fn build_inner(
    grid: &Grid,
    start: (i32, i32),
    goal: (i32, i32),
    obstacle_on_right: bool,
) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    Box::new(Bug2 {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        start,
        goal,
        pos: start,
        mode: Mode::MotionToGoal,
        wf: WallFollowState {
            pos: start,
            current_obstacle: start,
            obstacle_on_right,
        },
        default_handed: obstacle_on_right,
        hit_point: start,
        hit_dist_sq: dist_sq(start, goal),
        follow_visited: HashSet::new(),
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

/// Fat m-line test via cross-product tolerance: `pos` is within 0.5 cells of
/// the continuous line from `start` to `goal`, on the forward side, and
/// strictly closer than `start`.
fn on_baseline(pos: (i32, i32), start: (i32, i32), goal: (i32, i32)) -> bool {
    let dx_t = goal.0 - start.0;
    let dy_t = goal.1 - start.1;
    let dx_c = pos.0 - start.0;
    let dy_c = pos.1 - start.1;
    let cross = (dy_c * dx_t - dx_c * dy_t).abs();
    let tol = dx_t.abs().max(dy_t.abs()) / 2;
    if cross > tol {
        return false;
    }
    let dot = dx_c * dx_t + dy_c * dy_t;
    dot > 0 && dist_sq(pos, goal) < dist_sq(start, goal)
}

impl Bug2 {
    fn passable(&self, x: i32, y: i32) -> bool {
        if x < 0 || y < 0 || x >= self.grid_w || y >= self.grid_h {
            return false;
        }
        !self.walls[(y * self.grid_w + x) as usize]
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
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

    fn enter_follow(&mut self, blocked_dir: usize) {
        self.mode = Mode::Follow;
        self.wf = WallFollowState {
            pos: self.pos,
            current_obstacle: neighbour(self.pos, blocked_dir),
            obstacle_on_right: self.default_handed,
        };
        self.hit_point = self.pos;
        self.hit_dist_sq = dist_sq(self.pos, self.goal);
        self.follow_visited.clear();
        self.follow_visited.insert((
            self.wf.pos,
            self.wf.current_obstacle,
            self.wf.obstacle_on_right,
        ));
    }
}

impl Pathfinder for Bug2 {
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
                    self.enter_follow(d);
                }
            }
            Mode::Follow => {
                // King-adjacency shortcut.
                if dist_sq(self.pos, self.goal) <= 2 && self.passable(self.goal.0, self.goal.1) {
                    self.mode = Mode::MotionToGoal;
                    self.move_to(self.goal);
                    return self.status;
                }
                match self.step_wall_follow() {
                    WallStepOutcome::Moved => {}
                    WallStepOutcome::Surrounded => {
                        self.status = StepStatus::Unreachable;
                        return self.status;
                    }
                }
                if on_baseline(self.pos, self.start, self.goal)
                    && dist_sq(self.pos, self.goal) < self.hit_dist_sq
                {
                    self.mode = Mode::MotionToGoal;
                    return self.status;
                }
                let state = (
                    self.wf.pos,
                    self.wf.current_obstacle,
                    self.wf.obstacle_on_right,
                );
                if !self.follow_visited.insert(state) {
                    // Full loop without a closer m-line crossing — Bug2's
                    // textbook termination.
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
            "pos: ({}, {})\nstart: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nhit: ({}, {})\nhit_d2: {}\nobstacle: ({}, {})\nside: {}\non_baseline: {}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.start.0,
            self.start.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            self.hit_point.0,
            self.hit_point.1,
            self.hit_dist_sq,
            self.wf.current_obstacle.0,
            self.wf.current_obstacle.1,
            if self.wf.obstacle_on_right { "R" } else { "L" },
            on_baseline(self.pos, self.start, self.goal),
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "Bug2"
    }
}
