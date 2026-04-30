//! VisBug-21 (Lumelsky & Skewis, 1990). Bug2 with range-sensor jumps —
//! motion-to-goal jumps along the direction-to-goal ray; wall-follow takes
//! a single anchored step (no multi-cell wall jump, which overshoots
//! corners). The sensor shortcut in motion-to-goal gives Bug2's path the
//! main speedup.

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

pub struct VisBug21 {
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
    Box::new(VisBug21 {
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

impl VisBug21 {
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
        self.hit_dist_sq = dist_sq(self.pos, self.goal);
        self.follow_visited.clear();
        self.follow_visited.insert((
            self.wf.pos,
            self.wf.current_obstacle,
            self.wf.obstacle_on_right,
        ));
    }

    /// VisBug-21 motion-to-goal step: jump to the farthest visible cell on
    /// Bug2's planned path (the m-line from start to goal) that's closer to
    /// goal than current pos, with `LoS` and within sensor range. This is
    /// the paper's "farthest visible Ti on T" rule. Preserves m-line
    /// adherence, unlike a raw direction-to-goal jump which drifts off the
    /// baseline and breaks Follow's leave condition.
    fn jump_along_mline(&mut self) -> bool {
        let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
        let passable =
            |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize];
        let cur_d = dist_sq(self.pos, self.goal);
        let mut best: Option<((i32, i32), i32)> = None;
        for c in sensed_cells(self.pos) {
            if c == self.pos {
                continue;
            }
            if !on_baseline(c, self.start, self.goal) {
                continue;
            }
            if !passable(c.0, c.1) {
                continue;
            }
            let d = dist_sq(c, self.goal);
            if d >= cur_d {
                continue;
            }
            if !has_los(self.pos, c, passable) {
                continue;
            }
            // Prefer the cell with the smallest dist-to-goal (farthest along
            // the m-line toward goal).
            match best {
                None => best = Some((c, d)),
                Some((_, bd)) if d < bd => best = Some((c, d)),
                _ => {}
            }
        }
        if let Some((target, _)) = best {
            let line = bresenham(self.pos, target);
            for &p in line.iter().skip(1) {
                self.move_to(p);
            }
            true
        } else {
            false
        }
    }
}

impl Pathfinder for VisBug21 {
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
                // Try the VisBug-21 m-line jump first.
                if self.jump_along_mline() {
                    return self.status;
                }
                // No visible m-line cell closer to goal — fall back to
                // Bug2's 1-cell direction-to-goal step.
                let d = dir_to_goal(self.pos, self.goal);
                let np = neighbour(self.pos, d);
                if self.passable(np.0, np.1) {
                    self.move_to(np);
                } else {
                    self.enter_follow(d);
                }
            }
            Mode::Follow => {
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
            "pos: ({}, {})\ngoal: ({}, {})\nmode: {:?}\nhit: ({}, {})\nhit_d2: {}\nobstacle: ({}, {})\nside: {}\non_baseline: {}\nsensor r²≤{}\nsteps: {}\nstatus: {:?}",
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
            on_baseline(self.pos, self.start, self.goal),
            VISION_R_SQ,
            self.steps,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "VisBug-21"
    }
}
