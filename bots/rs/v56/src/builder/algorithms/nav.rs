//! Movement navigation: bug2-bounded planner + `dp_step` path-follower.
//!
//! Replaces A*/BFS for movement. Plan-incrementally-walk reactive style:
//!
//! - The `BugNav` state holds (goal, `path_idx`, planner, `gen_done`).
//! - Each turn, when the bot wants to move toward a goal:
//!   - If `goal` differs from cached, reset state and start a new plan.
//!   - Else if no path-tile is currently visible, the cached plan is stale
//!     (we drifted off-plan); reset and start a new plan.
//!   - Else: drain BUDGET planner steps to extend the plan.
//! - Then `dp_step(cost, pos, path_idx)` picks the next move: the visible
//!   cell with maximum `path_idx` (closest goalward, with cost-aware tiebreak).

use std::collections::HashMap;

use cambc::Position;

use crate::builder::algorithms::bug2_planner::{Bug2Planner, build_mline_seq};
use crate::builder::algorithms::dp_step::dp_step;
use crate::util::constants::{INF, MAX_N, MAX_WIDTH};

#[pyrust::inline]
const PLAN_BUDGET: i32 = 25;

/// Subset of `Builder` state read by nav. Phase G6's `Builder` will populate
/// this each turn from its own fields and pass `&mut` to `step`.
pub struct NavCtx<'a> {
    pub my_pos: Position,
    pub cost_grid: &'a mut [i32; MAX_N],
    pub w: i32,
    pub h: i32,
    pub nearby_tiles: &'a [Position],
    pub all_bots: &'a HashMap<Position, i32>,
}

/// Per-builder navigation state. One instance lives on each builder.
pub struct BugNav {
    active_goal: Option<Position>,
    active_start: Option<Position>,
    /// While a plan is in progress, the planner owns `path_idx`. Once the
    /// planner finishes (or we replan), `path_idx` is moved back into
    /// `path_idx_storage`.
    planner: Option<Bug2Planner>,
    gen_done: bool,
    /// Canonical `path_idx` storage when no planner is active.
    path_idx_storage: Vec<i32>,
    unreachable: bool,
    /// Cell indices the planner has committed to the path so far,
    /// in the order they were laid down. Reset on replan.
    committed: Vec<i32>,
}

impl Default for BugNav {
    fn default() -> Self {
        Self::new()
    }
}

impl BugNav {
    #[must_use]
    pub fn new() -> Self {
        Self {
            active_goal: None,
            active_start: None,
            planner: None,
            gen_done: false,
            path_idx_storage: vec![-1; MAX_N],
            unreachable: false,
            committed: pyrust::vec::new!(),
        }
    }

    /// Read-only access to the current `path_idx` array (whether owned by the
    /// planner or by storage).
    fn path_idx(&self) -> &[i32] {
        if let Some(p) = pyrust::as_ref!(self.planner) {
            p.path_idx()
        } else {
            &self.path_idx_storage
        }
    }

    /// Return the next position to move toward `goal`, or `None` if no
    /// progress can be made (no path or already at goal).
    ///
    /// Replans iff:
    ///   - goal changed since last call, OR
    ///   - the current plan has no tile visible to the bot (drifted off).
    pub fn step(&mut self, ctx: &mut NavCtx<'_>, goal: Position) -> Option<Position> {
        let pos = ctx.my_pos;
        if pos == goal {
            return None;
        }

        let stride = MAX_WIDTH as i32;
        let si = pos.y * stride + pos.x;
        let gi = goal.y * stride + goal.x;

        // Run the plan-then-dp pipeline at most twice. First attempt
        // uses the cached plan (if any). If dp_step says the plan is
        // unactionable from here, force a replan and try once more.
        for attempt in 0..2 {
            let force_replan = attempt == 1;
            let replan = force_replan
                || Some(goal) != self.active_goal
                || !self.any_path_tile_visible(ctx.nearby_tiles);

            if replan {
                // Reclaim path_idx from any in-flight planner.
                if let Some(planner) = pyrust::opt_take!(self.planner) {
                    self.path_idx_storage = planner.into_path_idx();
                }
                self.active_goal = Some(goal);
                self.active_start = Some(pos);
                pyrust::vec::fill!(self.path_idx_storage, -1);
                self.path_idx_storage[si as usize] = 0;
                self.unreachable = false;
                self.committed = vec![si];
                let path_idx = pyrust::vec::take!(self.path_idx_storage);
                self.planner = Some(Bug2Planner::new(
                    ctx.cost_grid,
                    ctx.w,
                    ctx.h,
                    si,
                    gi,
                    path_idx,
                ));
                self.gen_done = false;
            }

            if self.unreachable {
                return None;
            }

            if !self.gen_done && pyrust::is_some!(self.planner) {
                for _ in 0..PLAN_BUDGET {
                    let planner = pyrust::expect!(pyrust::as_mut!(self.planner), "planner is Some");
                    match planner.step(ctx.cost_grid) {
                        Some(true) => {
                            self.gen_done = true;
                            self.path_idx_storage =
                                pyrust::expect!(pyrust::opt_take!(self.planner), "planner is Some")
                                    .into_path_idx();
                            break;
                        }
                        Some(false) => {
                            self.gen_done = true;
                            self.unreachable = true;
                            self.path_idx_storage =
                                pyrust::expect!(pyrust::opt_take!(self.planner), "planner is Some")
                                    .into_path_idx();
                            break;
                        }
                        None => {
                            let yielded = planner.last_yielded;
                            if yielded != -1 {
                                pyrust::vec::push!(self.committed, yielded);
                            }
                        }
                    }
                }
                if self.unreachable {
                    return None;
                }
            }

            // Overlay other-builder positions as INF in cost_grid so dp_step
            // routes around them. Restore after the call.
            let mut saved: Vec<(usize, i32)> = pyrust::vec::new!();
            for fb_pos in ctx.all_bots.keys() {
                if *fb_pos == pos {
                    continue;
                }
                let fi = (fb_pos.y * stride + fb_pos.x) as usize;
                pyrust::vec::push!(saved, (fi, ctx.cost_grid[fi]));
                ctx.cost_grid[fi] = INF;
            }
            let path_idx_ref: &[i32] = if let Some(p) = pyrust::as_ref!(self.planner) {
                p.path_idx()
            } else {
                &self.path_idx_storage
            };
            let cur_min = path_idx_ref[si as usize];
            let dp_nxt = dp_step(
                MAX_WIDTH as i32,
                ctx.cost_grid,
                ctx.h,
                si,
                path_idx_ref,
                cur_min,
            );

            // Use P[1] as lookahead: pick the neighbour minimising Chebyshev
            // distance to it, tie-breaking by cost so roads beat bare tiles.
            let mut nxt = dp_nxt;
            if dp_nxt != si {
                let dp_nxt_idx = path_idx_ref[dp_nxt as usize];
                let mut lookahead = dp_nxt;
                if dp_nxt_idx >= 0 && (dp_nxt_idx as usize + 1) < pyrust::len!(self.committed) {
                    lookahead = self.committed[dp_nxt_idx as usize + 1];
                }
                let lx = lookahead % stride;
                let ly = lookahead / stride;
                let cheby_to_lookahead =
                    pyrust::max!(pyrust::abs!((pos.x - lx)), pyrust::abs!((pos.y - ly)));
                if cheby_to_lookahead == 1 && ctx.cost_grid[lookahead as usize] != INF {
                    nxt = lookahead;
                } else {
                    let mut best_cheby = i32::MAX;
                    let mut best_cost = i32::MAX;
                    for (dx, dy) in [
                        (-1i32, -1i32),
                        (0, -1),
                        (1, -1),
                        (-1, 0),
                        (1, 0),
                        (-1, 1),
                        (0, 1),
                        (1, 1),
                    ] {
                        let nx = pos.x + dx;
                        let ny = pos.y + dy;
                        if nx < 0 || nx >= ctx.w || ny < 0 || ny >= ctx.h {
                            continue;
                        }
                        let ni = (ny * stride + nx) as usize;
                        if ctx.cost_grid[ni] == INF {
                            continue;
                        }
                        let cheby = pyrust::max!(pyrust::abs!((nx - lx)), pyrust::abs!((ny - ly)));
                        let c = ctx.cost_grid[ni];
                        if cheby < best_cheby || (cheby == best_cheby && c < best_cost) {
                            best_cheby = cheby;
                            best_cost = c;
                            nxt = ny * stride + nx;
                        }
                    }
                }
            }

            for (fi, prev) in saved {
                ctx.cost_grid[fi] = prev;
            }

            if nxt == si {
                continue;
            }

            return Some(Position {
                x: nxt % stride,
                y: nxt / stride,
            });
        }

        None
    }

    fn any_path_tile_visible(&self, nearby: &[Position]) -> bool {
        let stride = MAX_WIDTH as i32;
        let path_idx = self.path_idx();
        for tile in nearby {
            if path_idx[(tile.y * stride + tile.x) as usize] != -1 {
                return true;
            }
        }
        false
    }

    #[pyrust::inline]
    /// Raw flat path-index array. Cell value = position-along-path,
    /// `-1` if not on plan. Used by the state dump as an `I16Grid`.
    #[must_use]
    pub fn path_idx_array(&self) -> &[i32] {
        self.path_idx()
    }

    /// Cells the planner has committed to the path so far, in order
    /// (start → goalward). Used by the state dump as a `DumpPath`.
    #[must_use]
    pub fn committed_positions(&self) -> Vec<Position> {
        let stride = MAX_WIDTH as i32;
        pyrust::collect!(pyrust::map!(pyrust::iter!(self.committed), |i| Position {
            x: i % stride,
            y: i / stride,
        }))
    }

    #[pyrust::inline]
    #[must_use]
    pub const fn active_goal(&self) -> Option<Position> {
        self.active_goal
    }

    #[pyrust::inline]
    /// True iff the planner finished (success or proven unreachable). When
    /// false, the planner is still suspended and will resume next turn.
    #[must_use]
    pub const fn gen_done(&self) -> bool {
        self.gen_done
    }

    #[pyrust::inline]
    /// True iff the planner concluded the goal is unreachable. When this
    /// is true, `step()` returns `None` unconditionally until the goal
    /// changes.
    #[must_use]
    pub const fn unreachable(&self) -> bool {
        self.unreachable
    }

    /// Bresenham m-line from the active plan's start to the goal. Empty
    /// if there's no active plan. Used by the state dump.
    #[must_use]
    pub fn mline(&self) -> Vec<Position> {
        let (Some(s), Some(g)) = (self.active_start, self.active_goal) else {
            return pyrust::vec::new!();
        };
        pyrust::collect!(pyrust::map!(
            pyrust::into_iter!(build_mline_seq(s.x, s.y, g.x, g.y)),
            |t| Position { x: t.0, y: t.1 }
        ))
    }
}
