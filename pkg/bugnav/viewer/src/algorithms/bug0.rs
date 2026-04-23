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

pub struct Bug0 {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    wf: WallFollowState,
    default_handed: bool,
    hit_dist_sq: i32,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    build_inner(grid, start, goal, true)
}

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
    Box::new(Bug0 {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        mode: Mode::MotionToGoal,
        wf: WallFollowState {
            pos: start,
            current_obstacle: start,
            obstacle_on_right,
        },
        default_handed: obstacle_on_right,
        hit_dist_sq: dist_sq(start, goal),
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

impl Bug0 {
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
            obstacle_on_right: self.default_handed,
        };
        self.hit_dist_sq = dist_sq(self.pos, self.goal);
    }
}

impl Pathfinder for Bug0 {
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
                let d = dir_to_goal(self.pos, self.goal);
                let np = neighbour(self.pos, d);
                if self.passable(np.0, np.1) && dist_sq(np, self.goal) < self.hit_dist_sq {
                    self.mode = Mode::MotionToGoal;
                    self.move_to(np);
                } else {
                    match self.step_wall_follow() {
                        WallStepOutcome::Moved => {}
                        WallStepOutcome::Surrounded => {
                            self.status = StepStatus::Unreachable;
                        }
                    }
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
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nobstacle: ({}, {})\nside: {}\nhit_dist2: {}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            self.wf.current_obstacle.0,
            self.wf.current_obstacle.1,
            if self.wf.obstacle_on_right { "R" } else { "L" },
            self.hit_dist_sq,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "Bug0"
    }
}
