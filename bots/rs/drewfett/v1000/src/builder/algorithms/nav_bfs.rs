//! Backwards-BFS navigation. Port of v54's adgato/mesh `NavBfs` +
//! `PassableGrid` combined into one struct (1:1 ownership; combining
//! avoids the bidirectional grid<->nav links that don't translate
//! cleanly to Rust's borrow rules).
//!
//! Layout: padded grid of size `(w+2) * (h+2)` with `passable[pi]`
//! indexed by `pi = (y+1)*pw + (x+1)`. Borders (row 0/h+1, col 0/w+1)
//! are permanently impassable so interior tiles always have 8 valid
//! neighbours without bounds checks.
//!
//! Per-tile precomputed neighbour lists:
//! - `pnb_push[pi]` — diagonals always pushed; cardinals pushed only
//!   when neither adjacent diagonal is passable (so the cardinal isn't
//!   already reached via the diagonal wave).
//! - `pnb_set[pi]` — cardinals reached via diagonals; their dist is
//!   set without re-enqueuing them.
//!
//! BFS runs backwards from the goal, building a dist field. Subsequent
//! turns with the same goal scan the agent's 8 neighbours in O(1) and
//! pick the lowest dist (gradient descent).
//!
//! Generation counter (`gen[pi]`) avoids zeroing dist between BFS runs.

use cambc::Position;
use std::collections::HashSet;

#[pyrust::inline]
const _BFS_INF: i32 = 1_000_000;

pub struct NavBfs {
    pub w: i32,
    pub h: i32,
    /// padded width = w + 2.
    pub pw: i32,
    /// real-tile count = w * h.
    pub rn: i32,
    /// padded grid size = pw * (h + 2).
    pub n: i32,
    /// `passable[pi] != 0` iff tile is walkable.
    pub passable: Vec<u8>,
    /// `is_road[pi] != 0` iff tile holds a friendly Road. Used as a
    /// tiebreaker in `_best_step` so bots prefer existing infra over
    /// paving fresh roads on equal-dist alternatives.
    pub is_road: Vec<u8>,
    /// Padded neighbours to enqueue for BFS.
    pub pnb_push: Vec<Vec<i32>>,
    /// Padded neighbours that get dist set without enqueue.
    pub pnb_set: Vec<Vec<i32>>,
    /// Pending pnb rebuild after passability changes.
    pub pnb_dirty: HashSet<i32>,
    /// Real-tile index reached by `init_pnb_chunk` so far.
    pub pnb_init_progress: i32,
    /// Padded offsets in order: NE, SE, SW, NW, N, E, S, W.
    pub offsets: [i32; 8],

    /// Padded indices of current goals (typically 1).
    pub goals: Vec<i32>,
    pub dirty: bool,
    pub dist: Vec<i32>,
    /// Generation byte; eq to `gen_val` ⇔ dist is fresh this BFS run.
    pub gen_arr: Vec<u8>,
    pub gen_val: u8,
    /// Queue (sized `n` so it never reallocates).
    pub q: Vec<i32>,
    pub qi: i32,
    pub qlen: i32,
    /// True iff a partial BFS is parked mid-run.
    pub resumable: bool,
    pub cur_dist: i32,
    pub cur_idx: i32,

    pub running_target: Option<Position>,
    pub prev_target: Option<Position>,
    pub no_path: bool,
    pub prev_no_path: bool,
}

impl NavBfs {
    /// Construct an empty `NavBfs` matching map dimensions `w × h`.
    /// Caller must run `init_pnb_chunk` until `ready()` before the
    /// first BFS query.
    #[must_use]
    pub fn new(w: i32, h: i32) -> Self {
        let pw = w + 2;
        let rn = w * h;
        let n = pw * (h + 2);
        let n_us = n as usize;

        // Border = 0, interior = 1 (default-walkable until observed).
        let mut passable: Vec<u8> = vec![1u8; n_us];
        // Top + bottom border rows.
        for x in 0..pw {
            passable[x as usize] = 0;
            passable[((h + 1) * pw + x) as usize] = 0;
        }
        // Left + right border columns.
        for ry in 1..=h {
            passable[(ry * pw) as usize] = 0;
            passable[(ry * pw + pw - 1) as usize] = 0;
        }

        let mut pnb_push: Vec<Vec<i32>> = pyrust::vec::new!();
        let mut pnb_set: Vec<Vec<i32>> = pyrust::vec::new!();
        for _ in 0..n_us {
            pyrust::vec::push!(pnb_push, pyrust::vec::new!());
            pyrust::vec::push!(pnb_set, pyrust::vec::new!());
        }

        let offsets: [i32; 8] = [
            -pw + 1,  // NE
            pw + 1,   // SE
            pw - 1,   // SW
            -pw - 1,  // NW
            -pw,      // N
            1,        // E
            pw,       // S
            -1,       // W
        ];

        Self {
            w,
            h,
            pw,
            rn,
            n,
            passable,
            is_road: vec![0u8; n_us],
            pnb_push,
            pnb_set,
            pnb_dirty: pyrust::set::new!(),
            pnb_init_progress: 0,
            offsets,
            goals: pyrust::vec::new!(),
            dirty: true,
            dist: vec![0i32; n_us],
            gen_arr: vec![0u8; n_us],
            gen_val: 1,
            q: vec![0i32; n_us],
            qi: 0,
            qlen: 0,
            resumable: false,
            cur_dist: -1,
            cur_idx: -1,
            running_target: None,
            prev_target: None,
            no_path: false,
            prev_no_path: false,
        }
    }

    /// Convert real `y * w + x` index to padded `pi = (y+1)*pw + (x+1)`.
    #[must_use]
    pub fn real_to_padded(&self, i: i32) -> i32 {
        i + 2 * (i / self.w) + self.pw + 1
    }

    /// Padded index from a `Position`.
    #[must_use]
    pub fn pi_of(&self, pos: Position) -> i32 {
        (pos.y + 1) * self.pw + (pos.x + 1)
    }

    /// True once the initial pnb build has finished.
    #[must_use]
    pub fn ready(&self) -> bool {
        self.pnb_init_progress >= self.rn
    }

    /// True iff at least one tile changed passability since last rebuild.
    #[must_use]
    pub fn has_dirty_pnb(&self) -> bool {
        !pyrust::set::is_empty!(self.pnb_dirty)
    }

    /// Update road-tile flag. Used only for tiebreak preference.
    pub fn set_road(&mut self, i: i32, is_road: bool) {
        let pi = self.real_to_padded(i);
        self.is_road[pi as usize] = if is_road { 1u8 } else { 0u8 };
    }

    /// Update one real-tile passability. Marks pnb dirty and forces a
    /// fresh BFS.
    pub fn set_passable(&mut self, i: i32, passable: bool) {
        let pi = self.real_to_padded(i);
        let old = self.passable[pi as usize];
        let new_val: u8 = if passable { 1u8 } else { 0u8 };
        if old == new_val {
            return;
        }
        self.passable[pi as usize] = new_val;
        if passable {
            pyrust::set::add!(self.pnb_dirty, pi);
        } else {
            pyrust::set::remove!(self.pnb_dirty, &pi);
        }
        // Mark walkable neighbours dirty too — their pnb depends on `pi`.
        for &off in &self.offsets {
            let ni = pi + off;
            if ni >= 0 && (ni as usize) < self.n as usize && self.passable[ni as usize] != 0 {
                pyrust::set::add!(self.pnb_dirty, ni);
            }
        }
        // Conservative: any passability change invalidates dist.
        self.dirty = true;
    }

    /// Build pnb tables incrementally; assumes every interior tile is
    /// passable. Yields after `chunk` real tiles. Returns true once
    /// complete.
    pub fn init_pnb_chunk(&mut self, chunk: i32) -> bool {
        let w = self.w;
        let pw = self.pw;
        let total = self.rn;
        let mut progress = self.pnb_init_progress;
        let processed_target = pyrust::min!(progress + chunk, total);

        let ne = self.offsets[0];
        let se = self.offsets[1];
        let sw = self.offsets[2];
        let nw = self.offsets[3];
        let n_off = self.offsets[4];
        let e_off = self.offsets[5];
        let s_off = self.offsets[6];
        let w_off = self.offsets[7];

        let mut ry = progress / w;
        let mut rx = progress % w;
        let mut pi = (ry + 1) * pw + (rx + 1);

        while progress < processed_target {
            let mut push: Vec<i32> = pyrust::vec::new!();
            pyrust::vec::push!(push, pi + ne);
            pyrust::vec::push!(push, pi + se);
            pyrust::vec::push!(push, pi + sw);
            pyrust::vec::push!(push, pi + nw);
            self.pnb_push[pi as usize] = push;
            let mut set: Vec<i32> = pyrust::vec::new!();
            pyrust::vec::push!(set, pi + n_off);
            pyrust::vec::push!(set, pi + e_off);
            pyrust::vec::push!(set, pi + s_off);
            pyrust::vec::push!(set, pi + w_off);
            self.pnb_set[pi as usize] = set;
            progress += 1;
            rx += 1;
            if rx == w {
                rx = 0;
                ry += 1;
                pi += 3; // skip right border + left border of next row
            } else {
                pi += 1;
            }
        }

        self.pnb_init_progress = progress;
        progress >= total
    }

    /// Rebuild pnb lists for every tile in `pnb_dirty`.
    pub fn rebuild_pnb(&mut self) {
        let dirty: Vec<i32> = pyrust::collect!(pyrust::copied!(pyrust::iter!(self.pnb_dirty)));
        let ne = self.offsets[0];
        let se = self.offsets[1];
        let sw = self.offsets[2];
        let nw = self.offsets[3];
        let n_off = self.offsets[4];
        let e_off = self.offsets[5];
        let s_off = self.offsets[6];
        let w_off = self.offsets[7];

        for pi in &dirty {
            let pi = *pi;
            let pi_us = pi as usize;
            self.pnb_push[pi_us] = pyrust::vec::new!();
            self.pnb_set[pi_us] = pyrust::vec::new!();
            if self.passable[pi_us] == 0 {
                continue;
            }
            let pne = pi + ne;
            let pse = pi + se;
            let psw = pi + sw;
            let pnw = pi + nw;
            let pn = pi + n_off;
            let pe = pi + e_off;
            let ps = pi + s_off;
            let pw_idx = pi + w_off;

            let has_ne = self.passable[pne as usize] != 0;
            let has_se = self.passable[pse as usize] != 0;
            let has_sw = self.passable[psw as usize] != 0;
            let has_nw = self.passable[pnw as usize] != 0;
            let mut push: Vec<i32> = pyrust::vec::new!();
            let mut set: Vec<i32> = pyrust::vec::new!();
            if has_ne {
                pyrust::vec::push!(push, pne);
            }
            if has_se {
                pyrust::vec::push!(push, pse);
            }
            if has_sw {
                pyrust::vec::push!(push, psw);
            }
            if has_nw {
                pyrust::vec::push!(push, pnw);
            }
            if self.passable[pn as usize] != 0 {
                if has_ne && has_nw {
                    pyrust::vec::push!(set, pn);
                } else {
                    pyrust::vec::push!(push, pn);
                }
            }
            if self.passable[pe as usize] != 0 {
                if has_ne && has_se {
                    pyrust::vec::push!(set, pe);
                } else {
                    pyrust::vec::push!(push, pe);
                }
            }
            if self.passable[ps as usize] != 0 {
                if has_se && has_sw {
                    pyrust::vec::push!(set, ps);
                } else {
                    pyrust::vec::push!(push, ps);
                }
            }
            if self.passable[pw_idx as usize] != 0 {
                if has_sw && has_nw {
                    pyrust::vec::push!(set, pw_idx);
                } else {
                    pyrust::vec::push!(push, pw_idx);
                }
            }
            self.pnb_push[pi_us] = push;
            self.pnb_set[pi_us] = set;
        }
        pyrust::set::clear!(self.pnb_dirty);
    }

    pub fn mark_dirty(&mut self) {
        self.dirty = true;
    }

    pub fn change_goal(&mut self, goals: Vec<Position>) {
        let pw = self.pw;
        let mut gv: Vec<i32> = pyrust::vec::new!();
        for g in &goals {
            pyrust::vec::push!(gv, (g.y + 1) * pw + (g.x + 1));
        }
        self.goals = gv;
        self.dirty = true;
    }

    fn _restart(&mut self) {
        let mut g = self.gen_val + 1;
        if g > 200 {
            g = 1;
            let n_us = self.n as usize;
            for i in 0..n_us {
                self.gen_arr[i] = 0;
            }
        }
        self.gen_val = g;
        let mut qlen: i32 = 0;
        for &gi in &self.goals {
            self.dist[gi as usize] = 0;
            self.gen_arr[gi as usize] = g;
            self.q[qlen as usize] = gi;
            qlen += 1;
        }
        self.qi = 0;
        self.qlen = qlen;
        self.resumable = true;
    }

    /// Run/resume backwards BFS until `max_pops` nodes are processed
    /// or the queue empties or we've expanded one wave past the agent.
    /// Returns true if BFS is complete (or sufficient for current
    /// agent position) for this call.
    ///
    /// Destructure-borrow at top: each neighbour list (`pnb_push`,
    /// `pnb_set`) is iterated *by reference* rather than via
    /// `pyrust::clone!`, which translates to `list(...)` in Python and
    /// allocates a fresh list per popped node. On a 50×50 labyrinth this
    /// was the single largest CPython hotspot (~720μs / call). Identity
    /// `pyrust::iter!` is a no-op in Python, so the loop iterates the
    /// existing list directly.
    fn _compute(&mut self, max_pops: i32) -> bool {
        let g = self.gen_val;
        let cur_idx = self.cur_idx;
        let Self {
            pnb_push,
            pnb_set,
            q,
            dist,
            gen_arr,
            ..
        } = self;
        let cd = if cur_idx >= 0 && gen_arr[cur_idx as usize] == g {
            dist[cur_idx as usize]
        } else {
            -1
        };
        let mut stop_at = if cd != -1 { cd + 1 } else { _BFS_INF };
        let mut pops: i32 = 0;
        let mut qi = self.qi;
        let mut qlen = self.qlen;
        while qi < qlen {
            let node = q[qi as usize];
            qi += 1;
            pops += 1;
            let d = dist[node as usize] + 1;
            if node == cur_idx {
                stop_at = d;
            }
            if d > stop_at {
                self.qi = qi - 1;
                self.qlen = qlen;
                return true;
            }
            // pnb_push neighbours: enqueue.
            for &ni in pyrust::iter!(pnb_push[node as usize]) {
                if gen_arr[ni as usize] == g {
                    continue;
                }
                gen_arr[ni as usize] = g;
                dist[ni as usize] = d;
                q[qlen as usize] = ni;
                qlen += 1;
            }
            // pnb_set neighbours: just write dist, no enqueue.
            for &ni in pyrust::iter!(pnb_set[node as usize]) {
                if gen_arr[ni as usize] == g {
                    continue;
                }
                if ni == cur_idx {
                    stop_at = d + 1;
                }
                gen_arr[ni as usize] = g;
                dist[ni as usize] = d;
            }
            if pops >= max_pops {
                self.qi = qi;
                self.qlen = qlen;
                return false;
            }
        }
        self.qi = qi;
        self.qlen = qlen;
        true
    }

    /// Pick the lowest-dist 8-neighbour. Returns None if no neighbour
    /// has been touched by BFS or all are blocked.
    fn _best_step(&self, start: Position) -> Option<Position> {
        let g = self.gen_val;
        let pw = self.pw;
        let ci = (start.y + 1) * pw + (start.x + 1);
        // Deltas matching offsets order (NE, SE, SW, NW, N, E, S, W).
        let deltas: [(i32, i32); 8] = [
            (1, -1),
            (1, 1),
            (-1, 1),
            (-1, -1),
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 0),
        ];
        let mut best_d: i32 = _BFS_INF;
        let mut best_dx: i32 = 0;
        let mut best_dy: i32 = 0;
        let mut best_road: bool = false;
        for ii in 0..8usize {
            let off = self.offsets[ii];
            let (dx, dy) = deltas[ii];
            let ni = ci + off;
            if ni < 0 || (ni as usize) >= self.n as usize {
                continue;
            }
            if self.passable[ni as usize] == 0 {
                continue;
            }
            if self.gen_arr[ni as usize] != g {
                continue;
            }
            let d = self.dist[ni as usize];
            let is_road = self.is_road[ni as usize] != 0;
            // Strict-better dist always wins. On equal dist, prefer a
            // road tile over a non-road tile (saves Ti by reusing infra).
            let strictly_better = d < best_d;
            let same_d_road_wins = d == best_d && is_road && !best_road;
            if strictly_better || same_d_road_wins {
                best_d = d;
                best_dx = dx;
                best_dy = dy;
                best_road = is_road;
            }
        }
        if best_d >= _BFS_INF {
            return None;
        }
        Some(Position {
            x: start.x + best_dx,
            y: start.y + best_dy,
        })
    }

    /// Same contract as v1000's existing nav: returns `Some([start, next_step])`
    /// or None if no path / no progress yet.
    pub fn search(
        &mut self,
        start: Position,
        target: Position,
        budget_pops: i32,
    ) -> Option<Vec<Position>> {
        // Caller must have made `ready()` true via init_pnb_chunk before
        // calling — short-circuit otherwise.
        if !self.ready() {
            return None;
        }
        if self.has_dirty_pnb() {
            self.rebuild_pnb();
        }
        let goal_pi = self.pi_of(target);
        let goals_match =
            !pyrust::vec::is_empty!(self.goals) && self.goals[0] == goal_pi;
        if !goals_match {
            let mut gv: Vec<i32> = pyrust::vec::new!();
            pyrust::vec::push!(gv, goal_pi);
            self.goals = gv;
            self.dirty = true;
        }
        self.cur_idx = self.pi_of(start);
        if self.dirty {
            self._restart();
            self.dirty = false;
        } else if !self.resumable
            && self.gen_arr[self.cur_idx as usize] != self.gen_val
            && self.qi < self.qlen
        {
            self.resumable = true;
        }
        if self.resumable {
            let finished = self._compute(budget_pops);
            if finished {
                self.resumable = self.qi < self.qlen;
            }
        }
        let g = self.gen_val;
        self.cur_dist = if self.gen_arr[self.cur_idx as usize] == g {
            self.dist[self.cur_idx as usize]
        } else {
            -1
        };
        self.running_target = Some(target);
        self.prev_target = Some(target);
        if self.cur_dist < 0 {
            self.no_path = true;
            self.prev_no_path = true;
            return None;
        }
        let next_step = self._best_step(start);
        let Some(next_step) = next_step else {
            self.no_path = true;
            self.prev_no_path = true;
            return None;
        };
        self.no_path = false;
        self.prev_no_path = false;
        let mut path: Vec<Position> = pyrust::vec::new!();
        pyrust::vec::push!(path, start);
        pyrust::vec::push!(path, next_step);
        Some(path)
    }
}
