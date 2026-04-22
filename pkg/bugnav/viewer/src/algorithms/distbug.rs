//! DistBug (Kamon & Rivlin, 1997). Bug2 with a range sensor — leave the wall
//! when `d_leave - F ≤ d_min - STEP`, where `F` is the free distance along
//! the ray to goal, as seen by the sensor.

use std::collections::HashSet;

use crate::algorithms::bug_common::{
    DIRS, VISION_R_SQ, WallFollowState, WallStepOutcome, dir_to_goal, dist_sq, neighbour,
    wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

const STEP: f64 = 1.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    Follow,
}

pub struct DistBug {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    wf: WallFollowState,
    hit_point: (i32, i32),
    d_min: f64,
    follow_steps: u32,
    follow_visited: HashSet<((i32, i32), (i32, i32), bool)>,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

fn dist(a: (i32, i32), b: (i32, i32)) -> f64 {
    (dist_sq(a, b) as f64).sqrt()
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    Box::new(DistBug {
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
        d_min: dist(start, goal),
        follow_steps: 0,
        follow_visited: HashSet::new(),
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

impl DistBug {
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
            obstacle_on_right: true,
        };
        self.hit_point = self.pos;
        self.follow_steps = 0;
        self.follow_visited.clear();
        self.follow_visited.insert((
            self.wf.pos,
            self.wf.current_obstacle,
            self.wf.obstacle_on_right,
        ));
    }

    /// Free distance along the king-direction ray toward the goal, measured
    /// in cells traversed (Euclidean distance to last passable cell). Must
    /// match the direction motion-to-goal will actually use — otherwise the
    /// leave condition can fire while motion is still blocked, causing an
    /// infinite Follow↔MotionToGoal oscillation.
    fn free_distance_to_goal(&self) -> f64 {
        let d = dir_to_goal(self.pos, self.goal);
        let (dx, dy) = DIRS[d];
        let mut p = self.pos;
        loop {
            let next = (p.0 + dx, p.1 + dy);
            if dist_sq(self.pos, next) > VISION_R_SQ {
                break;
            }
            if !self.passable(next.0, next.1) {
                break;
            }
            p = next;
        }
        dist(self.pos, p)
    }
}

impl Pathfinder for DistBug {
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
                    let new_d = dist(self.pos, self.goal);
                    if new_d < self.d_min {
                        self.d_min = new_d;
                    }
                } else {
                    self.enter_follow(d);
                }
            }
            Mode::Follow => {
                let d_leave = dist(self.pos, self.goal);
                let f = self.free_distance_to_goal();
                if d_leave - f <= self.d_min - STEP {
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
                self.follow_steps += 1;
                let new_d = dist(self.pos, self.goal);
                if new_d < self.d_min {
                    self.d_min = new_d;
                }
                let state = (
                    self.wf.pos,
                    self.wf.current_obstacle,
                    self.wf.obstacle_on_right,
                );
                if !self.follow_visited.insert(state) {
                    // Full circumnavigation with no qualifying leave condition.
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
        let f = if self.mode == Mode::Follow {
            self.free_distance_to_goal()
        } else {
            0.0
        };
        format!(
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nhit: ({}, {})\nd_leave: {:.2}\nd_min: {:.2}\nF: {:.2}\nleave if: d_leave-F ≤ d_min-1 ({:.2} ≤ {:.2})\nobstacle: ({}, {})\nside: {}\nsensor r²≤{}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            self.hit_point.0,
            self.hit_point.1,
            dist(self.pos, self.goal),
            self.d_min,
            f,
            dist(self.pos, self.goal) - f,
            self.d_min - STEP,
            self.wf.current_obstacle.0,
            self.wf.current_obstacle.1,
            if self.wf.obstacle_on_right { "R" } else { "L" },
            VISION_R_SQ,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "DistBug"
    }
}
