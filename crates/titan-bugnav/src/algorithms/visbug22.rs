//! VisBug-22 (Lumelsky & Skewis, 1990). At each step, survey every cell
//! within sensor range and jump to the best visible passable cell with `LoS`.

use std::collections::HashSet;

use crate::algorithms::bug_common::{
    VISION_R_SQ, WallFollowState, WallStepOutcome, bresenham, dir_to_goal, dist_sq, has_los,
    neighbour, sensed_cells, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    Follow,
}

pub struct VisBug22 {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    start: (i32, i32),
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    wf: WallFollowState,
    hit_point: (i32, i32),
    hit_dist_sq: i32,
    follow_visited: HashSet<((i32, i32), (i32, i32), bool)>,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

#[must_use]
pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    Box::new(VisBug22 {
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
            obstacle_on_right: true,
        },
        hit_point: start,
        hit_dist_sq: dist_sq(start, goal),
        follow_visited: HashSet::new(),
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

impl VisBug22 {
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

    fn jump_to(&mut self, target: (i32, i32)) {
        let line = bresenham(self.pos, target);
        for &p in line.iter().skip(1) {
            self.move_to(p);
        }
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
        self.hit_dist_sq = dist_sq(self.pos, self.goal);
        self.follow_visited.clear();
        self.follow_visited.insert((
            self.wf.pos,
            self.wf.current_obstacle,
            self.wf.obstacle_on_right,
        ));
    }

    fn best_visible_toward_goal(&self) -> Option<(i32, i32)> {
        let passable = self.passable_closure();
        let cur_d = dist_sq(self.pos, self.goal);
        let mut best: Option<((i32, i32), i32)> = None;
        for c in sensed_cells(self.pos) {
            if c == self.pos {
                continue;
            }
            if !passable(c.0, c.1) {
                continue;
            }
            let d = dist_sq(c, self.goal);
            if d >= cur_d {
                continue;
            }
            if !has_los(self.pos, c, &passable) {
                continue;
            }
            match best {
                None => best = Some((c, d)),
                Some((_, bd)) if d < bd => best = Some((c, d)),
                _ => {}
            }
        }
        best.map(|(c, _)| c)
    }

    fn best_mline_leave(&self) -> Option<(i32, i32)> {
        let passable = self.passable_closure();
        let mut best: Option<((i32, i32), i32)> = None;
        for c in sensed_cells(self.pos) {
            if !on_baseline(c, self.start, self.goal) {
                continue;
            }
            if !passable(c.0, c.1) {
                continue;
            }
            let d = dist_sq(c, self.goal);
            if d >= self.hit_dist_sq {
                continue;
            }
            if !has_los(self.pos, c, &passable) {
                continue;
            }
            match best {
                None => best = Some((c, d)),
                Some((_, bd)) if d < bd => best = Some((c, d)),
                _ => {}
            }
        }
        best.map(|(c, _)| c)
    }
}

impl Pathfinder for VisBug22 {
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
                let passable = self.passable_closure();
                if has_los(self.pos, self.goal, &passable) {
                    drop(passable);
                    self.jump_to(self.goal);
                    return self.status;
                }
                drop(passable);
                if let Some(best) = self.best_visible_toward_goal() {
                    self.jump_to(best);
                } else {
                    let d = dir_to_goal(self.pos, self.goal);
                    let np = neighbour(self.pos, d);
                    if self.passable(np.0, np.1) {
                        self.move_to(np);
                    } else {
                        self.enter_follow(d);
                    }
                }
            }
            Mode::Follow => {
                if let Some(leave) = self.best_mline_leave() {
                    self.jump_to(leave);
                    self.mode = Mode::MotionToGoal;
                    return self.status;
                }
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
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nhit: ({}, {})\nhit_d2: {}\nobstacle: ({}, {})\nside: {}\nsensor r²≤{}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            self.hit_point.0,
            self.hit_point.1,
            self.hit_dist_sq,
            self.wf.current_obstacle.0,
            self.wf.current_obstacle.1,
            if self.wf.obstacle_on_right { "R" } else { "L" },
            VISION_R_SQ,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "VisBug-22"
    }
}
