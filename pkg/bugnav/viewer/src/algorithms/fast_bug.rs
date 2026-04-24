//! Bounded look-ahead Bug1. The bot physically wall-follows one cell per
//! round (never sits still), but the algorithm also runs an internal
//! simulation K steps ahead of the bot. When the sim detects a full
//! perimeter cycle, the bot commits to the short arc from ITS current
//! position to the perim's closest-to-goal cell — walking forward or
//! backward along the perim, whichever is shorter.
//!
//! Each round:
//! - 1 wall-follow step simulated (≤ K times)
//! - 1 bot move (one cell)
//!
//! Per-round cost = K × wall_follow_step cost + constant overhead,
//! bounded per round.
//!
//! Quality: bot's "wasted" walk = round_of_commit cells. With K sims per
//! round, sim completes full perimeter N at round N/K. Bot then walks the
//! short arc from perim[N/K] to perim[best_leave_idx] (forward or back).

use crate::algorithms::bug_common::{
    DIRS, WallFollowState, WallStepOutcome, dir_to_goal, dist_sq, neighbour, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

/// Simulation steps per round (ahead of bot's physical walk).
const K: usize = 128;

#[inline]
fn dir_of(delta: (i32, i32)) -> usize {
    for (i, &d) in DIRS.iter().enumerate() {
        if d == delta {
            return i;
        }
    }
    0
}

#[inline]
fn state_idx(w: i32, wf: &WallFollowState) -> usize {
    let pos_idx = (wf.pos.1 * w + wf.pos.0) as usize;
    let obs_dir = dir_of((
        wf.current_obstacle.0 - wf.pos.0,
        wf.current_obstacle.1 - wf.pos.1,
    ));
    let side = usize::from(wf.obstacle_on_right);
    pos_idx * 16 + obs_dir * 2 + side
}

#[inline]
fn passable(grid: &Grid, x: i32, y: i32) -> bool {
    x >= 0
        && y >= 0
        && x < grid.w
        && y < grid.h
        && !grid.walls[(y * grid.w + x) as usize]
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    Motion,
    Circum,   // bot physically walks perim; sim runs ahead
    WalkArc,  // commit phase: bot walks the chosen arc
    Done,
    Failed,
}

pub struct FastBug {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    mode: Mode,

    // Perim walked by sim (bot's physical positions follow a prefix).
    sim_wf: WallFollowState,
    hit_pos: (i32, i32),
    perim: Vec<(i32, i32)>,
    sim_done: bool,
    sim_closed: bool,
    best_idx: usize,
    best_d: i32,
    // How far along perim the bot has physically walked (index into `perim`).
    bot_idx: usize,

    seen: Vec<u32>,
    version: u32,

    // Arc walk state: direction, target index, wrap-through-hit flag.
    arc_target_idx: usize,
    arc_forward: bool,
    arc_wrap: bool,

    snap: Snapshot,
    status: StepStatus,
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let w = grid.w;
    let h = grid.h;
    let snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };

    let status = if start == goal {
        StepStatus::Arrived
    } else {
        StepStatus::Running
    };

    Box::new(FastBug {
        grid_w: w,
        grid_h: h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        mode: if start == goal { Mode::Done } else { Mode::Motion },

        sim_wf: WallFollowState {
            pos: start,
            current_obstacle: start,
            obstacle_on_right: true,
        },
        hit_pos: start,
        perim: Vec::new(),
        sim_done: false,
        sim_closed: false,
        best_idx: 0,
        best_d: 0,
        bot_idx: 0,

        seen: vec![0u32; (w * h) as usize * 16],
        version: 0,

        arc_target_idx: 0,
        arc_forward: true,
        arc_wrap: false,

        snap,
        status,
    })
}

#[inline]
fn walls_pass(walls: &[bool], w: i32, h: i32, x: i32, y: i32) -> bool {
    x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize]
}

impl FastBug {
    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.path.push(new_pos);
    }

    fn enter_circum(&mut self, blocked_dir: usize) {
        self.mode = Mode::Circum;
        self.hit_pos = self.pos;
        self.sim_wf = WallFollowState {
            pos: self.pos,
            current_obstacle: neighbour(self.pos, blocked_dir),
            obstacle_on_right: true,
        };
        self.perim.clear();
        self.perim.push(self.pos);
        self.sim_done = false;
        self.sim_closed = false;
        self.best_d = dist_sq(self.pos, self.goal);
        self.best_idx = 0;
        self.bot_idx = 0;
        self.version = self.version.wrapping_add(1);
        if self.version == 0 {
            for s in self.seen.iter_mut() {
                *s = 0;
            }
            self.version = 1;
        }
        self.seen[state_idx(self.grid_w, &self.sim_wf)] = self.version;
    }

    /// Advance the internal sim by up to `K` wall-follow steps, tracking
    /// `best_idx` and checking state-cycle termination.
    fn sim_advance(&mut self) {
        let (w, h) = (self.grid_w, self.grid_h);
        for _ in 0..K {
            if self.sim_done {
                break;
            }
            let walls = &self.walls;
            let pass = |x: i32, y: i32| walls_pass(walls, w, h, x, y);
            let onmap = |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h;
            match wall_follow_step(&mut self.sim_wf, pass, onmap) {
                WallStepOutcome::Moved => {}
                WallStepOutcome::Surrounded => {
                    self.sim_done = true;
                    return;
                }
            }
            self.perim.push(self.sim_wf.pos);
            let k = self.perim.len() - 1;
            let d2 = dist_sq(self.sim_wf.pos, self.goal);
            if d2 < self.best_d {
                self.best_d = d2;
                self.best_idx = k;
            }
            let idx = state_idx(self.grid_w, &self.sim_wf);
            if self.seen[idx] == self.version {
                self.sim_done = true;
                self.sim_closed = self.sim_wf.pos == self.hit_pos;
                return;
            }
            self.seen[idx] = self.version;
        }
    }
}

impl Pathfinder for FastBug {
    fn step(&mut self) -> StepStatus {
        if self.status != StepStatus::Running {
            return self.status;
        }
        if self.pos == self.goal {
            self.status = StepStatus::Arrived;
            return self.status;
        }

        match self.mode {
            Mode::Done => {
                self.status = StepStatus::Arrived;
                return self.status;
            }
            Mode::Failed => {
                self.status = StepStatus::Unreachable;
                return self.status;
            }
            Mode::Motion => {
                let d = dir_to_goal(self.pos, self.goal);
                let np = neighbour(self.pos, d);
                if walls_pass(&self.walls, self.grid_w, self.grid_h, np.0, np.1) {
                    self.move_to(np);
                } else {
                    self.enter_circum(d);
                }
            }
            Mode::Circum => {
                // Advance sim up to K steps ahead of bot.
                self.sim_advance();

                // Bot walks one cell along the sim's perim, tracking
                // `bot_idx`. perim[0] is hit_pos, perim[bot_idx] is bot's
                // current physical position.
                if self.bot_idx + 1 < self.perim.len() {
                    self.bot_idx += 1;
                    let next = self.perim[self.bot_idx];
                    self.move_to(next);
                }

                if self.sim_done {
                    if self.best_d >= dist_sq(self.hit_pos, self.goal) {
                        self.mode = Mode::Failed;
                        return self.status;
                    }
                    // Pick the shorter arc from bot_idx to best_idx along
                    // perim. For a closed perim (last == hit == first) we
                    // can also wrap through the start/end.
                    let n = self.perim.len();
                    let (bi, ki) = (self.bot_idx, self.best_idx);
                    let closed = self.sim_closed && n >= 2;
                    let fwd_direct = if ki >= bi { ki - bi } else { usize::MAX };
                    let bwd_direct = if ki <= bi { bi - ki } else { usize::MAX };
                    let fwd_wrap = if closed && ki < bi {
                        (n - 1 - bi) + ki
                    } else {
                        usize::MAX
                    };
                    let bwd_wrap = if closed && ki > bi {
                        bi + (n - 1 - ki)
                    } else {
                        usize::MAX
                    };
                    let (best_len, dir_fwd, wrap) = [
                        (fwd_direct, true, false),
                        (bwd_direct, false, false),
                        (fwd_wrap, true, true),
                        (bwd_wrap, false, true),
                    ]
                    .into_iter()
                    .min_by_key(|(len, _, _)| *len)
                    .unwrap();
                    let _ = best_len;
                    self.arc_target_idx = self.best_idx;
                    self.arc_forward = dir_fwd;
                    self.arc_wrap = wrap;
                    self.mode = Mode::WalkArc;
                }
            }
            Mode::WalkArc => {
                if self.bot_idx == self.arc_target_idx {
                    self.mode = Mode::Motion;
                    return self.status;
                }
                let n = self.perim.len();
                if self.arc_forward {
                    self.bot_idx += 1;
                    if self.arc_wrap && self.bot_idx >= n - 1 {
                        self.bot_idx = 0;
                    }
                } else if self.bot_idx == 0 {
                    if self.arc_wrap {
                        self.bot_idx = n - 2; // skip the duplicate hit_pos at n-1
                    }
                } else {
                    self.bot_idx -= 1;
                }
                let next = self.perim[self.bot_idx];
                self.move_to(next);
                if self.bot_idx == self.arc_target_idx {
                    self.mode = Mode::Motion;
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
            "fast-bug K={}\nmode: {:?}\nbot_idx: {}\nbest_idx: {}\nstatus: {:?}",
            K,
            self.mode,
            self.bot_idx,
            self.best_idx,
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "FastBug"
    }
}
