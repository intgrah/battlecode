use std::collections::HashSet;

use crate::algorithms::bug_common::{
    DIR_NAMES, bresenham, dir_to_goal, dist_sq, follow_step, neighbour, rot_cw_90,
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
    follow_dir: usize,
    hit_point: (i32, i32),
    hit_dist_sq: i32,
    follow_steps: u32,
    m_line: HashSet<(i32, i32)>,
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
    let m_line: HashSet<(i32, i32)> = bresenham(start, goal).into_iter().collect();
    Box::new(Bug2 {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        start,
        goal,
        pos: start,
        mode: Mode::MotionToGoal,
        follow_dir: 0,
        hit_point: start,
        hit_dist_sq: dist_sq(start, goal),
        follow_steps: 0,
        m_line,
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
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
        self.snap.visited.insert(new_pos);
        self.snap.path.push(new_pos);
    }

    fn wall_step(&mut self) -> bool {
        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        let passable =
            |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize];
        if let Some((np, nd)) = follow_step(self.pos, self.follow_dir, passable) {
            self.follow_dir = nd;
            self.move_to(np);
            true
        } else {
            false
        }
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
                    self.mode = Mode::Follow;
                    self.follow_dir = rot_cw_90(d);
                    self.hit_point = self.pos;
                    self.hit_dist_sq = dist_sq(self.pos, self.goal);
                    self.follow_steps = 0;
                }
            }
            Mode::Follow => {
                if !self.wall_step() {
                    self.status = StepStatus::Unreachable;
                    return self.status;
                }
                self.follow_steps += 1;
                // Textbook leave rule: on m-line, strictly closer than hit_dist.
                // If the next motion-to-goal step is blocked, we'll re-enter
                // Follow with the new (closer) hit — nested hits terminate
                // because hit_dist is monotonically decreasing.
                if self.m_line.contains(&self.pos)
                    && dist_sq(self.pos, self.goal) < self.hit_dist_sq
                {
                    self.mode = Mode::MotionToGoal;
                } else if self.pos == self.hit_point && self.follow_steps > 0 {
                    // Full loop around the current sub-obstacle without finding a
                    // closer m-line crossing → unreachable under Bug2's rule.
                    // (This can be a false negative — Bug2 is classically
                    // incomplete on obstacles where the m-line is tangent or
                    // re-enters non-monotonically. Use Bug1 if completeness is
                    // required.)
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
            "pos: ({}, {})\nstart: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nfollow_dir: {}\nhit: ({}, {})\nhit_d2: {}\nfollow_steps: {}\nm_line cells: {}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.start.0,
            self.start.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            DIR_NAMES[self.follow_dir],
            self.hit_point.0,
            self.hit_point.1,
            self.hit_dist_sq,
            self.follow_steps,
            self.m_line.len(),
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "Bug2"
    }
}
