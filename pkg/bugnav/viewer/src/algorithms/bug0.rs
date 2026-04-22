use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

const DIRS: [(i32, i32); 4] = [(0, -1), (1, 0), (0, 1), (-1, 0)]; // N E S W
const DIR_NAMES: [&str; 4] = ["N", "E", "S", "W"];

const fn rot_right(d: usize) -> usize {
    (d + 1) % 4
}
const fn rot_left(d: usize) -> usize {
    (d + 3) % 4
}
const fn rot_back(d: usize) -> usize {
    (d + 2) % 4
}

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
    follow_dir: usize,
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
    Box::new(Bug0 {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        mode: Mode::MotionToGoal,
        follow_dir: 0,
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

    fn neighbour(&self, dir: usize) -> (i32, i32) {
        (self.pos.0 + DIRS[dir].0, self.pos.1 + DIRS[dir].1)
    }

    fn dir_to_goal(&self) -> usize {
        let dx = self.goal.0 - self.pos.0;
        let dy = self.goal.1 - self.pos.1;
        if dx.abs() > dy.abs() {
            if dx > 0 { 1 } else { 3 }
        } else if dy > 0 {
            2
        } else {
            0
        }
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.visited.insert(new_pos);
        self.snap.path.push(new_pos);
    }

    /// Right-hand wall-follow: try right, forward, left, back of current follow_dir.
    fn follow_step(&mut self) -> bool {
        for rot in [rot_right, |d| d, rot_left, rot_back] {
            let nd = rot(self.follow_dir);
            let np = self.neighbour(nd);
            if self.passable(np.0, np.1) {
                self.follow_dir = nd;
                self.move_to(np);
                return true;
            }
        }
        false
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
                let d = self.dir_to_goal();
                let np = self.neighbour(d);
                if self.passable(np.0, np.1) {
                    self.move_to(np);
                } else {
                    self.mode = Mode::Follow;
                    self.follow_dir = rot_right(d);
                }
            }
            Mode::Follow => {
                let d = self.dir_to_goal();
                let np = self.neighbour(d);
                if self.passable(np.0, np.1) {
                    self.mode = Mode::MotionToGoal;
                    self.move_to(np);
                } else if !self.follow_step() {
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
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nfollow_dir: {}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            DIR_NAMES[self.follow_dir],
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "Bug0"
    }
}
