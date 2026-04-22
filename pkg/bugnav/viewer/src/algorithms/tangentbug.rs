//! TangentBug (Kamon, Rivlin, Rimon, 1998). Range-sensor bug that picks
//! visible tangent points as subgoals and switches to boundary-following at
//! local minima of the heuristic `h(c) = d(pos, c) + d(c, goal)`.

use std::collections::HashSet;

use crate::algorithms::bug_common::{
    VISION_R_SQ, WallFollowState, WallStepOutcome, bresenham, dir_to_goal, dist_sq, has_los,
    neighbour, sensed_cells, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    MotionToGoal,
    Follow,
}

pub struct TangentBug {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,
    wf: WallFollowState,
    hit_point: (i32, i32),
    d_followed: f64,
    follow_visited: HashSet<((i32, i32), (i32, i32), bool)>,
    steps: u32,
    snap: Snapshot,
    status: StepStatus,
}

fn distf(a: (i32, i32), b: (i32, i32)) -> f64 {
    (dist_sq(a, b) as f64).sqrt()
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);
    Box::new(TangentBug {
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
        d_followed: f64::INFINITY,
        follow_visited: HashSet::new(),
        steps: 0,
        snap,
        status: StepStatus::Running,
    })
}

impl TangentBug {
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

    fn move_one_toward(&mut self, target: (i32, i32)) -> bool {
        let dx = (target.0 - self.pos.0).signum();
        let dy = (target.1 - self.pos.1).signum();
        if dx == 0 && dy == 0 {
            return false;
        }
        let np = (self.pos.0 + dx, self.pos.1 + dy);
        if self.passable(np.0, np.1) {
            self.move_to(np);
            true
        } else {
            false
        }
    }

    fn best_heuristic_subgoal(&self) -> Option<((i32, i32), f64)> {
        let passable = self.passable_closure();
        let mut best: Option<((i32, i32), f64)> = None;
        for c in sensed_cells(self.pos) {
            if c == self.pos {
                continue;
            }
            if !passable(c.0, c.1) {
                continue;
            }
            if !has_los(self.pos, c, &passable) {
                continue;
            }
            let h = distf(self.pos, c) + distf(c, self.goal);
            match best {
                None => best = Some((c, h)),
                Some((_, bh)) if h < bh => best = Some((c, h)),
                _ => {}
            }
        }
        best
    }

    /// Best visible BOUNDARY cell (passable, LoS, at least one blocked/OOB
    /// neighbour). Returns `(cell, d(cell, goal))`.
    fn best_visible_boundary(&self) -> Option<((i32, i32), f64)> {
        let passable = self.passable_closure();
        let mut best: Option<((i32, i32), f64)> = None;
        for c in sensed_cells(self.pos) {
            if !passable(c.0, c.1) {
                continue;
            }
            if !has_los(self.pos, c, &passable) {
                continue;
            }
            let mut is_boundary = false;
            'n: for dy in -1..=1 {
                for dx in -1..=1 {
                    if dx == 0 && dy == 0 {
                        continue;
                    }
                    if !passable(c.0 + dx, c.1 + dy) {
                        is_boundary = true;
                        break 'n;
                    }
                }
            }
            if !is_boundary {
                continue;
            }
            let d = distf(c, self.goal);
            match best {
                None => best = Some((c, d)),
                Some((_, bd)) if d < bd => best = Some((c, d)),
                _ => {}
            }
        }
        best
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

    fn enter_follow(&mut self, d_pos_goal: f64) {
        self.mode = Mode::Follow;
        let d = dir_to_goal(self.pos, self.goal);
        self.wf = WallFollowState {
            pos: self.pos,
            current_obstacle: neighbour(self.pos, d),
            obstacle_on_right: true,
        };
        self.hit_point = self.pos;
        self.d_followed = d_pos_goal;
        self.follow_visited.clear();
        self.follow_visited.insert((
            self.wf.pos,
            self.wf.current_obstacle,
            self.wf.obstacle_on_right,
        ));
    }
}

impl Pathfinder for TangentBug {
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
                    let _ = self.move_one_toward(self.goal);
                    return self.status;
                }
                drop(passable);

                let d_pos_goal = distf(self.pos, self.goal);
                match self.best_heuristic_subgoal() {
                    Some((best, h)) if h < d_pos_goal => {
                        if !self.move_one_toward(best) {
                            self.enter_follow(d_pos_goal);
                        }
                    }
                    _ => {
                        self.enter_follow(d_pos_goal);
                    }
                }
            }
            Mode::Follow => {
                if let Some((best, d_reach)) = self.best_visible_boundary()
                    && d_reach < self.d_followed
                {
                    self.mode = Mode::MotionToGoal;
                    let line = bresenham(self.pos, best);
                    for &p in line.iter().skip(1) {
                        self.pos = p;
                        self.snap.current = p;
                        self.snap.visited.insert(p);
                        self.snap.path.push(p);
                    }
                    return self.status;
                }

                match self.step_wall_follow() {
                    WallStepOutcome::Moved => {}
                    WallStepOutcome::Surrounded => {
                        self.status = StepStatus::Unreachable;
                        return self.status;
                    }
                }
                let cur = distf(self.pos, self.goal);
                if cur < self.d_followed {
                    self.d_followed = cur;
                }
                let state = (
                    self.wf.pos,
                    self.wf.current_obstacle,
                    self.wf.obstacle_on_right,
                );
                if !self.follow_visited.insert(state) {
                    // Full loop of the current obstacle with no closer
                    // boundary cell seen — TangentBug's textbook termination.
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
        let d_reach = self
            .best_visible_boundary()
            .map_or(f64::INFINITY, |(_, d)| d);
        format!(
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nhit: ({}, {})\nd(pos, goal): {:.2}\nd_followed: {:.2}\nd_reach: {:.2}\nobstacle: ({}, {})\nside: {}\nsensor r²≤{}\nsteps: {}\nstatus: {:?}",
            self.pos.0,
            self.pos.1,
            self.goal.0,
            self.goal.1,
            self.mode,
            self.hit_point.0,
            self.hit_point.1,
            distf(self.pos, self.goal),
            self.d_followed,
            d_reach,
            self.wf.current_obstacle.0,
            self.wf.current_obstacle.1,
            if self.wf.obstacle_on_right { "R" } else { "L" },
            VISION_R_SQ,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "TangentBug"
    }
}
