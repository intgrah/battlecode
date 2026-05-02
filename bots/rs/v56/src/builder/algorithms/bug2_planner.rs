//! Bug2 plan generator that mutates a `path_idx` list in place.
//!
//! Drains under a budget per turn — yields after each walker step, after
//! each m-line cell, and after each chosen-path cell. Caller drives the
//! generator and resumes next turn from where it left off.
//!
//! Outcome signalling: `step()` returns `Some(true)` on success (path reached
//! the goal), `Some(false)` if proven unreachable, and `None` while more steps
//! are needed. The "yielded value" is exposed as `last_yielded` (-1 for a
//! walker-step heartbeat, otherwise the flat cell index `y * MAX_WIDTH + x`).
//!
//! Cost model:
//! - `cost[i] == INF`        : impassable (wall, enemy building, harvester, ore)
//! - `cost[i] != INF`        : passable (treat as 1 for walkable, 3 for buildable
//!                             in the user's choice of cost grid; the planner
//!                             itself only checks `== INF`).
//! - `path_idx[i]`           : -1 if not on plan, else the index along the path
//!                             (monotone non-decreasing along the planned route).
//!                             Caller must initialize with -1s and write
//!                             `path_idx[start] = 0`.
//!
//! `stride` is the row stride for cell indices: `cell = y * stride + x`.
//! For the bot we pass `MAX_WIDTH`. `n_pad` is `stride * stride` (the size
//! of the flat arrays). `w`, `h` are the actual map dimensions.

use crate::util::constants::{INF, MAX_WIDTH};

const DX: [i32; 8] = [0, 1, 1, 1, 0, -1, -1, -1];
const DY: [i32; 8] = [-1, -1, 0, 1, 1, 1, 0, -1];
const IS_CARDINAL: [bool; 8] = [true, false, true, false, true, false, true, false];

/// Build the Bresenham m-line sequence from `(sx, sy)` to `(gx, gy)`.
#[must_use]
pub fn build_mline_seq(sx: i32, sy: i32, gx: i32, gy: i32) -> Vec<(i32, i32)> {
    let mut out: Vec<(i32, i32)> = pyrust::vec::new!();
    let dx = pyrust::abs!((gx - sx));
    let dy = pyrust::abs!((gy - sy));
    let sxi = if sx < gx { 1 } else { -1 };
    let syi = if sy < gy { 1 } else { -1 };
    let mut err = dx - dy;
    let mut cx = sx;
    let mut cy = sy;
    loop {
        pyrust::vec::push!(out, (cx, cy));
        if cx == gx && cy == gy {
            return out;
        }
        let e2 = err << 1;
        if e2 > -dy {
            err -= dy;
            cx += sxi;
        }
        if e2 < dx {
            err += dx;
            cy += syi;
        }
    }
}

/// Outcome of a single `step()` call.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum State {
    /// Main outer loop entry: try to advance along the m-line.
    AdvanceMLine,
    /// Walker race: alternately step CW and CCW walkers.
    WalkerRace,
    /// Emit each cell of the chosen path one at a time.
    EmitChosen { idx: usize },
    /// Emit the winning cell.
    EmitWinner,
    /// After winner emission, advance `m_i` past covered cells.
    AdvanceAfterWinner,
    /// Done — return value is in `done_value`.
    Done,
}

/// Bug2 planner state machine. One step ≈ one Python `yield`.
///
/// `cost` is supplied as a borrow on every `step()` call, mirroring the
/// Python generator that closes over the caller's mutable `cost_grid` list.
pub struct Bug2Planner {
    // Inputs captured at construction.
    w: i32,
    h: i32,
    gi: i32,
    /// Mutated in place; exposed via `path_idx()` and `into_path_idx()`.
    _path_idx: Vec<i32>,

    // Persistent state across yields.
    stride: i32,
    n_pad: i32,
    sx: i32,
    sy: i32,
    gx: i32,
    gy: i32,
    mdx: i32,
    mdy: i32,
    goal_dot: i32,
    mline_seq: Vec<(i32, i32)>,
    pos: i32,
    path_len: i32,
    m_i: usize,

    // Per-obstacle state (set in AdvanceMLine, used in WalkerRace).
    hit_d: i32,
    cw_faces: Vec<u8>,
    ccw_faces: Vec<u8>,
    cw_px: i32,
    cw_py: i32,
    cw_dir: i32,
    cw_path: Vec<i32>,
    cw_alive: bool,
    cw_cross: i32,
    cw_wox: i32,
    cw_woy: i32,
    ccw_px: i32,
    ccw_py: i32,
    ccw_dir: i32,
    ccw_path: Vec<i32>,
    ccw_alive: bool,
    ccw_cross: i32,
    ccw_wox: i32,
    ccw_woy: i32,
    winner: i32,
    win_x: i32,
    win_y: i32,
    met: bool,
    /// Phase within `WalkerRace`: 0 = run CW substep next, 1 = run CCW substep next.
    walker_phase: u8,

    /// Current state machine node.
    state: State,
    /// The "yielded" cell index from the most recent step (-1 = heartbeat,
    /// else flat index).
    pub last_yielded: i32,
    /// Final outcome (only valid in `State::Done`).
    done_value: bool,
}

impl Bug2Planner {
    /// Construct a new planner. Equivalent to entering the Python generator.
    #[must_use]
    pub fn new(cost: &[i32], w: i32, h: i32, si: i32, gi: i32, path_idx: Vec<i32>) -> Self {
        let stride = MAX_WIDTH as i32;
        let n_pad = stride * stride;
        let sx = si % stride;
        let sy = si / stride;
        let gx = gi % stride;
        let gy = gi / stride;
        let (gi, gx, gy) = if cost[gi as usize] != INF {
            (gi, gx, gy)
        } else {
            let mut best_gi = gi;
            let mut best_gx = gx;
            let mut best_gy = gy;
            let mut best_dist = i32::MAX;
            for d in 0..8usize {
                let nx = gx + DX[d];
                let ny = gy + DY[d];
                if nx < 0 || nx >= w || ny < 0 || ny >= h {
                    continue;
                }
                let ni = ny * stride + nx;
                if cost[ni as usize] == INF {
                    continue;
                }
                let ddx = nx - sx;
                let ddy = ny - sy;
                let dist = ddx * ddx + ddy * ddy;
                if dist < best_dist {
                    best_dist = dist;
                    best_gi = ni;
                    best_gx = nx;
                    best_gy = ny;
                }
            }
            (best_gi, best_gx, best_gy)
        };
        let mdx = gx - sx;
        let mdy = gy - sy;
        let goal_dot = mdx * mdx + mdy * mdy;
        let mline_seq = build_mline_seq(sx, sy, gx, gy);
        let goal_blocked = cost[gi as usize] == INF;
        let initial_state = if goal_blocked {
            State::Done
        } else {
            State::AdvanceMLine
        };
        Self {
            w,
            h,
            gi,
            _path_idx: path_idx,
            stride,
            n_pad,
            sx,
            sy,
            gx,
            gy,
            mdx,
            mdy,
            goal_dot,
            mline_seq,
            pos: si,
            path_len: 1,
            m_i: 0,
            hit_d: 0,
            cw_faces: pyrust::vec::new!(),
            ccw_faces: pyrust::vec::new!(),
            cw_px: 0,
            cw_py: 0,
            cw_dir: 0,
            cw_path: pyrust::vec::new!(),
            cw_alive: false,
            cw_cross: 0,
            cw_wox: 0,
            cw_woy: 0,
            ccw_px: 0,
            ccw_py: 0,
            ccw_dir: 0,
            ccw_path: pyrust::vec::new!(),
            ccw_alive: false,
            ccw_cross: 0,
            ccw_wox: 0,
            ccw_woy: 0,
            winner: -1,
            win_x: -1,
            win_y: -1,
            met: false,
            walker_phase: 0,
            state: initial_state,
            last_yielded: -1,
            done_value: !goal_blocked,
        }
    }

    #[pyrust::inline]
    /// Read-only borrow of the in-progress `path_idx` array.
    #[must_use]
    pub fn path_idx(&self) -> &[i32] {
        &self._path_idx
    }

    #[pyrust::inline]
    /// Take ownership of `path_idx`.
    #[must_use]
    pub fn into_path_idx(self) -> Vec<i32> {
        self._path_idx
    }

    /// Advance one yield-equivalent. Returns `Some(true)` if reached goal,
    /// `Some(false)` if proven unreachable, `None` if more steps needed.
    ///
    /// `cost` is the per-tile cost grid; the caller may mutate it between
    /// `step()` calls and the next call sees the latest values (mirrors the
    /// Python generator's closure over the caller's mutable list).
    pub fn step(&mut self, cost: &[i32]) -> Option<bool> {
        loop {
            match self.state {
                State::Done => {
                    return Some(self.done_value);
                }
                State::AdvanceMLine => {
                    if self.pos == self.gi {
                        self.state = State::Done;
                        self.done_value = true;
                        return Some(true);
                    }
                    if self.m_i + 1 >= pyrust::len!(self.mline_seq) {
                        self.state = State::Done;
                        self.done_value = false;
                        return Some(false);
                    }
                    let px = self.pos % self.stride;
                    let py = self.pos / self.stride;
                    let (nx, ny) = self.mline_seq[self.m_i + 1];
                    let nb = ny * self.stride + nx;
                    if cost[nb as usize] != INF {
                        self.pos = nb;
                        self._path_idx[nb as usize] = self.path_len;
                        self.path_len += 1;
                        self.m_i += 1;
                        self.last_yielded = nb;
                        return None;
                    }
                    // Obstacle hit; spawn CW + CCW walkers.
                    let ddx = px - self.gx;
                    let ddy = py - self.gy;
                    self.hit_d = ddx * ddx + ddy * ddy;
                    let bdx = nx - px;
                    let bdy = ny - py;
                    let init_dir = if bdx == 0 {
                        if bdy < 0 { 0 } else { 4 }
                    } else if bdx > 0 {
                        if bdy < 0 {
                            1
                        } else if bdy == 0 {
                            2
                        } else {
                            3
                        }
                    } else if bdy < 0 {
                        7
                    } else if bdy == 0 {
                        6
                    } else {
                        5
                    };
                    self.cw_faces = vec![0u8; (self.n_pad as usize) * 4];
                    self.ccw_faces = vec![0u8; (self.n_pad as usize) * 4];
                    self.cw_px = px;
                    self.cw_py = py;
                    self.cw_dir = init_dir;
                    self.cw_path.clear();
                    self.cw_alive = true;
                    self.cw_cross = (py - self.sy) * self.mdx - (px - self.sx) * self.mdy;
                    self.cw_wox = px + DX[init_dir as usize];
                    self.cw_woy = py + DY[init_dir as usize];
                    self.ccw_px = px;
                    self.ccw_py = py;
                    self.ccw_dir = init_dir;
                    self.ccw_path.clear();
                    self.ccw_alive = true;
                    self.ccw_cross = self.cw_cross;
                    self.ccw_wox = self.cw_wox;
                    self.ccw_woy = self.cw_woy;
                    self.winner = -1;
                    self.win_x = -1;
                    self.win_y = -1;
                    self.met = false;
                    self.walker_phase = 0;
                    self.state = State::WalkerRace;
                }
                State::WalkerRace => {
                    if !self.cw_alive && !self.ccw_alive {
                        if self.winner < 0 {
                            self.state = State::Done;
                            self.done_value = false;
                            return Some(false);
                        }
                        self.state = State::EmitChosen { idx: 0 };
                        continue;
                    }
                    if self.walker_phase == 0 {
                        if self.cw_alive {
                            self.cw_substep(cost);
                            // Update phase for next iteration.
                            self.walker_phase = 1;
                            if self.winner >= 0 || self.met {
                                if self.winner < 0 {
                                    self.state = State::Done;
                                    self.done_value = false;
                                    return Some(false);
                                }
                                self.state = State::EmitChosen { idx: 0 };
                                continue;
                            }
                            // Yield -1 heartbeat.
                            self.last_yielded = -1;
                            return None;
                        }
                        self.walker_phase = 1;
                        // fall through to ccw branch
                        continue;
                    }
                    // walker_phase == 1
                    if self.ccw_alive {
                        self.ccw_substep(cost);
                        self.walker_phase = 0;
                        if self.winner >= 0 || self.met {
                            if self.winner < 0 {
                                self.state = State::Done;
                                self.done_value = false;
                                return Some(false);
                            }
                            self.state = State::EmitChosen { idx: 0 };
                            continue;
                        }
                        self.last_yielded = -1;
                        return None;
                    }
                    self.walker_phase = 0;
                }
                State::EmitChosen { idx } => {
                    let chosen_path = if self.winner == 0 {
                        &self.cw_path
                    } else {
                        &self.ccw_path
                    };
                    if idx < pyrust::len!(chosen_path) {
                        let c = chosen_path[idx];
                        self._path_idx[c as usize] = self.path_len;
                        self.path_len += 1;
                        self.last_yielded = c;
                        self.state = State::EmitChosen { idx: idx + 1 };
                        return None;
                    }
                    self.state = State::EmitWinner;
                }
                State::EmitWinner => {
                    self.pos = self.win_y * self.stride + self.win_x;
                    self._path_idx[self.pos as usize] = self.path_len;
                    self.path_len += 1;
                    self.last_yielded = self.pos;
                    self.state = State::AdvanceAfterWinner;
                    return None;
                }
                State::AdvanceAfterWinner => {
                    let walker_dot =
                        (self.win_x - self.sx) * self.mdx + (self.win_y - self.sy) * self.mdy;
                    while self.m_i + 1 < pyrust::len!(self.mline_seq) {
                        let (mx, my) = self.mline_seq[self.m_i + 1];
                        if (mx - self.sx) * self.mdx + (my - self.sy) * self.mdy <= walker_dot {
                            self.m_i += 1;
                        } else {
                            break;
                        }
                    }
                    self.state = State::AdvanceMLine;
                }
            }
        }
    }

    fn cw_substep(&mut self, cost: &[i32]) {
        let mut moved = false;
        for _ in 0..8 {
            self.cw_dir = pyrust::rem_euclid!((self.cw_dir - 1), 8);
            let nx2 = self.cw_px + DX[self.cw_dir as usize];
            let ny2 = self.cw_py + DY[self.cw_dir as usize];
            if !(0 <= nx2 && nx2 < self.w && 0 <= ny2 && ny2 < self.h) {
                continue;
            }
            let cell = ny2 * self.stride + nx2;
            if cost[cell as usize] != INF {
                if 0 <= self.cw_wox
                    && self.cw_wox < self.w
                    && 0 <= self.cw_woy
                    && self.cw_woy < self.h
                {
                    let wdx = self.cw_wox - nx2;
                    let wdy = self.cw_woy - ny2;
                    if wdx == 0 || wdy == 0 {
                        let face = if wdx == -1 {
                            0
                        } else if wdx == 1 {
                            1
                        } else if wdy == 1 {
                            2
                        } else {
                            3
                        };
                        let k = ((self.cw_woy * self.stride + self.cw_wox) * 4 + face) as usize;
                        if self.ccw_faces[k] != 0 {
                            self.met = true;
                        }
                        self.cw_faces[k] = 1;
                    }
                }
                let nxt_cross = (ny2 - self.sy) * self.mdx - (nx2 - self.sx) * self.mdy;
                if (self.cw_cross > 0 && nxt_cross < 0)
                    || (self.cw_cross < 0 && nxt_cross > 0)
                    || nxt_cross == 0
                {
                    let cell_dot = (nx2 - self.sx) * self.mdx + (ny2 - self.sy) * self.mdy;
                    let ddx = nx2 - self.gx;
                    let ddy = ny2 - self.gy;
                    if 0 < cell_dot
                        && cell_dot <= self.goal_dot
                        && ddx * ddx + ddy * ddy < self.hit_d
                    {
                        self.winner = 0;
                        self.win_x = nx2;
                        self.win_y = ny2;
                        return;
                    }
                }
                self.cw_px = nx2;
                self.cw_py = ny2;
                self.cw_cross = nxt_cross;
                pyrust::vec::push!(self.cw_path, cell);
                if IS_CARDINAL[self.cw_dir as usize] {
                    self.cw_dir = pyrust::rem_euclid!((self.cw_dir + 2), 8);
                } else {
                    self.cw_dir = pyrust::rem_euclid!((self.cw_dir + 3), 8);
                }
                self.cw_wox = self.cw_px + DX[self.cw_dir as usize];
                self.cw_woy = self.cw_py + DY[self.cw_dir as usize];
                moved = true;
                if !(0 <= self.cw_wox
                    && self.cw_wox < self.w
                    && 0 <= self.cw_woy
                    && self.cw_woy < self.h)
                {
                    self.cw_alive = false;
                }
                break;
            }
            if IS_CARDINAL[self.cw_dir as usize] {
                let pdx = self.cw_px - nx2;
                let pdy = self.cw_py - ny2;
                let face = if pdx == 1 {
                    0
                } else if pdx == -1 {
                    1
                } else if pdy == -1 {
                    2
                } else {
                    3
                };
                let k = (cell * 4 + face) as usize;
                if self.ccw_faces[k] != 0 {
                    self.met = true;
                }
                self.cw_faces[k] = 1;
            }
            self.cw_wox = nx2;
            self.cw_woy = ny2;
        }
        if !moved {
            self.cw_alive = false;
        }
    }

    fn ccw_substep(&mut self, cost: &[i32]) {
        let mut moved = false;
        for _ in 0..8 {
            self.ccw_dir = pyrust::rem_euclid!((self.ccw_dir + 1), 8);
            let nx2 = self.ccw_px + DX[self.ccw_dir as usize];
            let ny2 = self.ccw_py + DY[self.ccw_dir as usize];
            if !(0 <= nx2 && nx2 < self.w && 0 <= ny2 && ny2 < self.h) {
                continue;
            }
            let cell = ny2 * self.stride + nx2;
            if cost[cell as usize] != INF {
                if 0 <= self.ccw_wox
                    && self.ccw_wox < self.w
                    && 0 <= self.ccw_woy
                    && self.ccw_woy < self.h
                {
                    let wdx = self.ccw_wox - nx2;
                    let wdy = self.ccw_woy - ny2;
                    if wdx == 0 || wdy == 0 {
                        let face = if wdx == -1 {
                            0
                        } else if wdx == 1 {
                            1
                        } else if wdy == 1 {
                            2
                        } else {
                            3
                        };
                        let k = ((self.ccw_woy * self.stride + self.ccw_wox) * 4 + face) as usize;
                        if self.cw_faces[k] != 0 {
                            self.met = true;
                        }
                        self.ccw_faces[k] = 1;
                    }
                }
                let nxt_cross = (ny2 - self.sy) * self.mdx - (nx2 - self.sx) * self.mdy;
                if (self.ccw_cross > 0 && nxt_cross < 0)
                    || (self.ccw_cross < 0 && nxt_cross > 0)
                    || nxt_cross == 0
                {
                    let cell_dot = (nx2 - self.sx) * self.mdx + (ny2 - self.sy) * self.mdy;
                    let ddx = nx2 - self.gx;
                    let ddy = ny2 - self.gy;
                    if 0 < cell_dot
                        && cell_dot <= self.goal_dot
                        && ddx * ddx + ddy * ddy < self.hit_d
                    {
                        self.winner = 1;
                        self.win_x = nx2;
                        self.win_y = ny2;
                        return;
                    }
                }
                self.ccw_px = nx2;
                self.ccw_py = ny2;
                self.ccw_cross = nxt_cross;
                pyrust::vec::push!(self.ccw_path, cell);
                if IS_CARDINAL[self.ccw_dir as usize] {
                    self.ccw_dir = pyrust::rem_euclid!((self.ccw_dir - 2), 8);
                } else {
                    self.ccw_dir = pyrust::rem_euclid!((self.ccw_dir - 3), 8);
                }
                self.ccw_wox = self.ccw_px + DX[self.ccw_dir as usize];
                self.ccw_woy = self.ccw_py + DY[self.ccw_dir as usize];
                moved = true;
                if !(0 <= self.ccw_wox
                    && self.ccw_wox < self.w
                    && 0 <= self.ccw_woy
                    && self.ccw_woy < self.h)
                {
                    self.ccw_alive = false;
                }
                break;
            }
            if IS_CARDINAL[self.ccw_dir as usize] {
                let pdx = self.ccw_px - nx2;
                let pdy = self.ccw_py - ny2;
                let face = if pdx == 1 {
                    0
                } else if pdx == -1 {
                    1
                } else if pdy == -1 {
                    2
                } else {
                    3
                };
                let k = (cell * 4 + face) as usize;
                if self.cw_faces[k] != 0 {
                    self.met = true;
                }
                self.ccw_faces[k] = 1;
            }
            self.ccw_wox = nx2;
            self.ccw_woy = ny2;
        }
        if !moved {
            self.ccw_alive = false;
        }
    }
}
