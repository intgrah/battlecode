//! Step-at-a-time Bug1 with Bug2 m-line candidates, short-arc selection.
//!
//! One wall-follow step per turn. The full circumnavigation still happens,
//! but spread across N turns so per-turn worst-case = ~1 wall-follow step
//! (~1 μs Rust) instead of the whole perimeter up-front.
//!
//! During the walk we track:
//!   * Bug1 candidate: perimeter cell closest to goal.
//!   * Bug2 candidates: any perimeter cell on the start→goal m-line that's
//!     strictly closer to goal than hit_pos.
//! On state-cycle termination we pick the candidate whose committed arc
//! (forward or backward from hit_pos) is shortest.
//!
//! Quality ≈ PrunedBest B1+B2 (one walk gives us both handedness-arcs
//! via reversal, and both leave criteria). No up-front path materialisation.

use crate::algorithms::bug_common::{
    DIRS, WallFollowState, WallStepOutcome, dir_to_goal, dist_sq, neighbour, wall_follow_step,
};
use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

/// Amortised O(n) stack-pop prune with a flat `Vec<i32>` pos→idx buffer
/// instead of a HashMap — no hashing, no allocation per call. The buffer
/// is owned by the caller and reset between invocations using a version
/// counter in the caller's state.
fn prune_cycles_flat(
    path: &[(i32, i32)],
    w: i32,
    pos_to_idx: &mut [i32],
    version: i32,
    pos_version: &mut [i32],
) -> Vec<(i32, i32)> {
    let mut out: Vec<(i32, i32)> = Vec::with_capacity(path.len());
    for &c in path {
        let pi = (c.1 * w + c.0) as usize;
        if pos_version[pi] == version {
            let k = pos_to_idx[pi] as usize;
            while out.len() > k + 1 {
                let popped = out.pop().unwrap();
                let ppi = (popped.1 * w + popped.0) as usize;
                pos_version[ppi] = 0;
            }
        } else {
            pos_version[pi] = version;
            pos_to_idx[pi] = out.len() as i32;
            out.push(c);
        }
    }
    out
}

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

/// Wall-follow / arc-walk steps performed per `step()` call. Trades
/// per-turn cost for total-turns-to-arrival. K=1 is "purely step-at-a-time"
/// but worst-case perimeters don't fit in 1000 turns. K larger amortises
/// more work per turn; per-turn Rust cost is roughly K × 400 ns + overhead.
const K: usize = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Mode {
    Motion,
    CircumCw,
    CircumAcw,
    WalkArc,
    Done,
    Failed,
}

pub struct StepBug {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    goal: (i32, i32),
    pos: (i32, i32),
    global_min: i32,
    mode: Mode,

    // m-line parameters, precomputed.
    mline_dx: i32,
    mline_dy: i32,
    mline_tol: i32,
    mline_d0: i32,
    mline_start: (i32, i32),

    // Circumnavigation state.
    wf: WallFollowState,
    hit_pos: (i32, i32),
    hit_d: i32,
    blocked_dir: usize,
    cw_perim: Vec<(i32, i32)>,
    cw_b1_idx: usize,
    cw_b1_d: i32,
    cw_b2: Option<usize>,
    cw_closed: bool,
    cw_done: bool,
    acw_perim: Vec<(i32, i32)>,
    acw_b1_idx: usize,
    acw_b1_d: i32,
    acw_b2: Option<usize>,
    acw_closed: bool,
    seen: Vec<u32>,
    version: u32,
    prune_pos_to_idx: Vec<i32>,
    prune_pos_version: Vec<i32>,
    prune_version: i32,

    // Arc-walking state.
    arc: Vec<(i32, i32)>,
    arc_idx: usize,
    arc_end_d: i32,

    snap: Snapshot,
    status: StepStatus,
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let w = grid.w;
    let mut snap = Snapshot {
        current: start,
        path: vec![start],
        ..Snapshot::default()
    };
    snap.visited.insert(start);

    let status = if start == goal {
        StepStatus::Arrived
    } else {
        StepStatus::Running
    };

    let dx_t = goal.0 - start.0;
    let dy_t = goal.1 - start.1;

    Box::new(StepBug {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        goal,
        pos: start,
        global_min: dist_sq(start, goal),
        mode: if start == goal { Mode::Done } else { Mode::Motion },

        mline_dx: dx_t,
        mline_dy: dy_t,
        mline_tol: dx_t.abs().max(dy_t.abs()) / 2,
        mline_d0: dist_sq(start, goal),
        mline_start: start,

        wf: WallFollowState {
            pos: start,
            current_obstacle: start,
            obstacle_on_right: true,
        },
        hit_pos: start,
        hit_d: 0,
        blocked_dir: 0,
        cw_perim: Vec::new(),
        cw_b1_idx: 0,
        cw_b1_d: i32::MAX,
        cw_b2: None,
        cw_closed: false,
        cw_done: false,
        acw_perim: Vec::new(),
        acw_b1_idx: 0,
        acw_b1_d: i32::MAX,
        acw_b2: None,
        acw_closed: false,
        seen: vec![0u32; (w * grid.h) as usize * 16],
        version: 0,
        prune_pos_to_idx: vec![0i32; (w * grid.h) as usize],
        prune_pos_version: vec![0i32; (w * grid.h) as usize],
        prune_version: 0,

        arc: Vec::new(),
        arc_idx: 0,
        arc_end_d: 0,

        snap,
        status,
    })
}

impl StepBug {
    #[inline]
    fn pass(&self, x: i32, y: i32) -> bool {
        passable_ref(&self.walls, self.grid_w, self.grid_h, x, y)
    }

    #[inline]
    fn on_map(&self, x: i32, y: i32) -> bool {
        x >= 0 && y >= 0 && x < self.grid_w && y < self.grid_h
    }

    #[inline]
    fn on_mline(&self, p: (i32, i32)) -> bool {
        let cx = p.0 - self.mline_start.0;
        let cy = p.1 - self.mline_start.1;
        if (cy * self.mline_dx - cx * self.mline_dy).abs() > self.mline_tol {
            return false;
        }
        cx * self.mline_dx + cy * self.mline_dy > 0 && dist_sq(p, self.goal) < self.mline_d0
    }

    fn move_to(&mut self, new_pos: (i32, i32)) {
        self.pos = new_pos;
        self.snap.current = new_pos;
        self.snap.path.push(new_pos);
    }

    fn enter_circum(&mut self, blocked_dir: usize) {
        self.mode = Mode::CircumCw;
        self.hit_pos = self.pos;
        self.hit_d = dist_sq(self.pos, self.goal);
        self.blocked_dir = blocked_dir;
        self.start_walk(true);
        self.cw_done = false;
        self.cw_closed = false;
        self.cw_b1_d = i32::MAX;
        self.cw_b2 = None;
        self.acw_closed = false;
        self.acw_b1_d = i32::MAX;
        self.acw_b2 = None;
    }

    fn start_walk(&mut self, obstacle_on_right: bool) {
        self.wf = WallFollowState {
            pos: self.hit_pos,
            current_obstacle: neighbour(self.hit_pos, self.blocked_dir),
            obstacle_on_right,
        };
        let perim = if obstacle_on_right {
            &mut self.cw_perim
        } else {
            &mut self.acw_perim
        };
        perim.clear();
        perim.push(self.hit_pos);
        if obstacle_on_right {
            self.cw_b1_idx = 0;
            self.cw_b1_d = self.hit_d;
        } else {
            self.acw_b1_idx = 0;
            self.acw_b1_d = self.hit_d;
        }
        self.version = self.version.wrapping_add(1);
        if self.version == 0 {
            for s in self.seen.iter_mut() {
                *s = 0;
            }
            self.version = 1;
        }
        self.seen[state_idx(self.grid_w, &self.wf)] = self.version;
    }

    /// After both CW and ACW walks complete — pick the best candidate
    /// from the union, populate arc, switch to WalkArc. Returns false if
    /// no progress is possible from either handedness.
    fn finish_circum(&mut self) -> bool {
        struct Best {
            score: i32,
            arc_cells: Vec<(i32, i32)>,
            end_d: i32,
        }
        let mut best: Option<Best> = None;
        let goal = self.goal;
        let consider = |best: &mut Option<Best>, arc_cells: Vec<(i32, i32)>, end_d: i32| {
            if arc_cells.is_empty() {
                return;
            }
            // Score = arc length + Chebyshev lower bound on remaining path
            // from leave point to goal. Admissible estimate of total cost
            // from hit_pos to goal. Picks arcs that trade length for
            // closer-to-goal leave, matching what running Bug1 and Bug2
            // side-by-side and picking the shorter finished path gives us.
            let leave = *arc_cells.last().unwrap();
            let dx = (leave.0 - goal.0).abs();
            let dy = (leave.1 - goal.1).abs();
            // Weighted octile: multiplier on the goal-distance component
            // since obstacles ahead inflate it beyond the 8-connected
            // lower bound. 15/10 = 1.5× is conservative.
            let hi = dx.max(dy);
            let lo = dx.min(dy);
            let cheb_w = 15 * hi + 6 * lo;
            let score = 10 * (arc_cells.len() as i32) + cheb_w;
            match best {
                None => *best = Some(Best { score, arc_cells, end_d }),
                Some(b) if score < b.score => *b = Best { score, arc_cells, end_d },
                _ => {}
            }
        };

        // Evaluate a single walk's candidates (forward-arc semantics — the
        // "backward" arc of the CW walk is the forward arc of the ACW walk,
        // which we ran separately).
        let eval = |perim: &[(i32, i32)],
                    b1_idx: usize,
                    b1_d: i32,
                    b2: Option<usize>,
                    gmin: i32,
                    best: &mut Option<Best>| {
            if b1_d < gmin && b1_idx > 0 {
                let arc = perim[1..=b1_idx].to_vec();
                consider(best, arc, b1_d);
            }
            // Bug2 candidates disabled: the `arc_len + octile` heuristic is
            // admissible but not accurate enough to choose between Bug1's
            // "closer-to-goal leave" and Bug2's "shorter arc, farther leave"
            // on labyrinth maps. Forcing Bug2 in hurts p100 by ~0.6. A
            // parallel Bug2 simulation with full path comparison is the
            // next step if needed.
            let _ = b2;
        };
        eval(
            &self.cw_perim,
            self.cw_b1_idx,
            self.cw_b1_d,
            self.cw_b2,
            self.global_min,
            &mut best,
        );
        // When CW closed, the reversal is a valid walk we can treat as a
        // synthetic ACW perim — gives the other arc without a second walk.
        if self.cw_closed && self.cw_perim.len() >= 2 {
            let n = self.cw_perim.len();
            let mut rev: Vec<(i32, i32)> = Vec::with_capacity(n);
            rev.push(self.hit_pos);
            for i in (1..n - 1).rev() {
                rev.push(self.cw_perim[i]);
            }
            rev.push(self.hit_pos);
            // Rescan for the candidates in reversed order.
            let mut r_b1_idx = 0usize;
            let mut r_b1_d = self.hit_d;
            let mut r_b2: Option<usize> = None;
            for (i, &c) in rev.iter().enumerate() {
                let d2 = dist_sq(c, self.goal);
                if d2 < r_b1_d {
                    r_b1_d = d2;
                    r_b1_idx = i;
                }
                if i > 0 && self.on_mline(c) && r_b2.is_none() {
                    r_b2 = Some(i);
                }
            }
            eval(&rev, r_b1_idx, r_b1_d, r_b2, self.global_min, &mut best);
        }
        eval(
            &self.acw_perim,
            self.acw_b1_idx,
            self.acw_b1_d,
            self.acw_b2,
            self.global_min,
            &mut best,
        );

        let Some(b) = best else {
            return false;
        };
        // Prune repeat positions from the arc before streaming — flat-array
        // version, no HashMap.
        let mut pruned_with_hit = Vec::with_capacity(b.arc_cells.len() + 1);
        pruned_with_hit.push(self.hit_pos);
        pruned_with_hit.extend_from_slice(&b.arc_cells);
        self.prune_version += 1;
        if self.prune_version < 0 {
            for s in self.prune_pos_version.iter_mut() {
                *s = 0;
            }
            self.prune_version = 1;
        }
        let pruned = prune_cycles_flat(
            &pruned_with_hit,
            self.grid_w,
            &mut self.prune_pos_to_idx,
            self.prune_version,
            &mut self.prune_pos_version,
        );
        self.arc = if pruned.len() > 1 {
            pruned[1..].to_vec()
        } else {
            Vec::new()
        };
        self.arc_idx = 0;
        self.arc_end_d = b.end_d;
        self.mode = Mode::WalkArc;
        true
    }
}

#[inline]
fn passable_ref(walls: &[bool], w: i32, h: i32, x: i32, y: i32) -> bool {
    x >= 0 && y >= 0 && x < w && y < h && !walls[(y * w + x) as usize]
}

impl Pathfinder for StepBug {
    fn step(&mut self) -> StepStatus {
        if self.status != StepStatus::Running {
            return self.status;
        }
        if self.pos == self.goal {
            self.status = StepStatus::Arrived;
            self.mode = Mode::Done;
            return self.status;
        }

        match self.mode {
            Mode::Done | Mode::Failed => {
                self.status = if self.mode == Mode::Done {
                    StepStatus::Arrived
                } else {
                    StepStatus::Unreachable
                };
                return self.status;
            }
            Mode::Motion => {
                let d = dir_to_goal(self.pos, self.goal);
                let np = neighbour(self.pos, d);
                if self.pass(np.0, np.1) {
                    self.move_to(np);
                    let d2 = dist_sq(self.pos, self.goal);
                    if d2 < self.global_min {
                        self.global_min = d2;
                    }
                } else {
                    self.enter_circum(d);
                }
            }
            Mode::CircumCw | Mode::CircumAcw => {
                // Do up to K simulation wall-follow steps this turn (bot
                // doesn't physically move during circumnavigation — the
                // bot just sits at hit_pos while we plan). Bounded per-turn
                // cost = K × wall_follow_step cost.
                for _ in 0..K {
                    let cw = self.mode == Mode::CircumCw;
                    let (w, h, walls) = (self.grid_w, self.grid_h, &self.walls);
                    let pass = |x: i32, y: i32| passable_ref(walls, w, h, x, y);
                    let onmap = |x: i32, y: i32| x >= 0 && y >= 0 && x < w && y < h;
                    match wall_follow_step(&mut self.wf, pass, onmap) {
                        WallStepOutcome::Moved => {}
                        WallStepOutcome::Surrounded => {
                            if cw {
                                self.cw_done = true;
                                self.start_walk(false);
                                self.mode = Mode::CircumAcw;
                                continue;
                            } else if !self.finish_circum() {
                                self.status = StepStatus::Unreachable;
                                self.mode = Mode::Failed;
                                return self.status;
                            } else {
                                break;
                            }
                        }
                    }
                    let b2_hit;
                    let d2 = dist_sq(self.wf.pos, self.goal);
                    let mline = self.on_mline(self.wf.pos);
                    let k_idx;
                    if cw {
                        self.cw_perim.push(self.wf.pos);
                        k_idx = self.cw_perim.len() - 1;
                        if d2 < self.cw_b1_d {
                            self.cw_b1_d = d2;
                            self.cw_b1_idx = k_idx;
                        }
                        b2_hit = mline && self.cw_b2.is_none();
                        if b2_hit {
                            self.cw_b2 = Some(k_idx);
                        }
                    } else {
                        self.acw_perim.push(self.wf.pos);
                        k_idx = self.acw_perim.len() - 1;
                        if d2 < self.acw_b1_d {
                            self.acw_b1_d = d2;
                            self.acw_b1_idx = k_idx;
                        }
                        b2_hit = mline && self.acw_b2.is_none();
                        if b2_hit {
                            self.acw_b2 = Some(k_idx);
                        }
                    }
                    let _ = b2_hit;
                    let idx = state_idx(self.grid_w, &self.wf);
                    if self.seen[idx] == self.version {
                        if cw {
                            self.cw_closed = self.wf.pos == self.hit_pos;
                            self.cw_done = true;
                            self.start_walk(false);
                            self.mode = Mode::CircumAcw;
                        } else {
                            self.acw_closed = self.wf.pos == self.hit_pos;
                            if !self.finish_circum() {
                                self.status = StepStatus::Unreachable;
                                self.mode = Mode::Failed;
                                return self.status;
                            }
                            break;
                        }
                    } else {
                        self.seen[idx] = self.version;
                    }
                }
            }
            Mode::WalkArc => {
                if self.arc_idx >= self.arc.len() {
                    self.global_min = self.arc_end_d;
                    self.mode = Mode::Motion;
                    self.arc.clear();
                } else {
                    let p = self.arc[self.arc_idx];
                    self.arc_idx += 1;
                    self.move_to(p);
                    if self.pos == self.goal {
                        self.status = StepStatus::Arrived;
                        self.mode = Mode::Done;
                    } else if self.arc_idx >= self.arc.len() {
                        self.global_min = self.arc_end_d;
                        self.mode = Mode::Motion;
                        self.arc.clear();
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
            "step-at-a-time Bug1+Bug2\nmode: {:?}\nsteps: {}\nstatus: {:?}",
            self.mode,
            self.snap.path.len().saturating_sub(1),
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "StepBug"
    }
}
