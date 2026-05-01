//! Translation of `bots/intgrah/v54.7.9/builder/algorithms/nav.py`.
//!
//! Movement navigation: bug2-bounded planner + dp_step path-follower.
//!
//! Replaces A*/BFS for movement. Plan-incrementally-walk reactive style:
//!
//! - The `BugNav` state holds (goal, path_idx, planner, gen_done).
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
    /// Canonical path_idx storage when no planner is active.
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

    /// Read-only access to the current path_idx array (whether owned by the
    /// planner or by storage).
    fn path_idx(&self) -> &[i32] {
        if let Some(p) = self.planner.as_ref() {
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
                if let Some(planner) = self.planner.take() {
                    self.path_idx_storage = planner.into_path_idx();
                }
                self.active_goal = Some(goal);
                self.active_start = Some(pos);
                self.path_idx_storage.fill(-1);
                self.path_idx_storage[si as usize] = 0;
                self.unreachable = false;
                self.committed = vec![si];
                let path_idx = std::mem::take(&mut self.path_idx_storage);
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
                    let planner = pyrust::expect!(self.planner.as_mut(), "planner is Some");
                    match planner.step(ctx.cost_grid) {
                        Some(true) => {
                            self.gen_done = true;
                            self.path_idx_storage = pyrust::expect!(self
                                .planner
                                .take(), "planner is Some")
                                .into_path_idx();
                            break;
                        }
                        Some(false) => {
                            self.gen_done = true;
                            self.unreachable = true;
                            self.path_idx_storage = pyrust::expect!(self
                                .planner
                                .take(), "planner is Some")
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
            for (fb_pos, _) in ctx.all_bots {
                if *fb_pos == pos {
                    continue;
                }
                let fi = (fb_pos.y * stride + fb_pos.x) as usize;
                pyrust::vec::push!(saved, (fi, ctx.cost_grid[fi]));
                ctx.cost_grid[fi] = INF;
            }
            let path_idx_ref: &[i32] = if let Some(p) = self.planner.as_ref() {
                p.path_idx()
            } else {
                &self.path_idx_storage
            };
            let cur_min = path_idx_ref[si as usize];
            let nxt = dp_step(
                MAX_WIDTH as i32,
                ctx.cost_grid,
                ctx.h,
                si,
                path_idx_ref,
                cur_min,
            );
            for (fi, prev) in saved {
                ctx.cost_grid[fi] = prev;
            }

            // dp_step returns the chosen next-step tile (one of the 8
            // immediate neighbours) or `si` if no path tile within the
            // 69-cell window is reachable. `nxt == si` is the only signal
            // that the plan is unactionable from here.
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

    #[must_use]
    pub fn active_goal(&self) -> Option<Position> {
        self.active_goal
    }

    /// True iff the planner finished (success or proven unreachable). When
    /// false, the planner is still suspended and will resume next turn.
    #[must_use]
    pub fn gen_done(&self) -> bool {
        self.gen_done
    }

    /// True iff the planner concluded the goal is unreachable. When this
    /// is true, `step()` returns `None` unconditionally until the goal
    /// changes.
    #[must_use]
    pub fn unreachable(&self) -> bool {
        self.unreachable
    }

    /// Bresenham m-line from the active plan's start to the goal. Empty
    /// if there's no active plan. Used by the state dump.
    #[must_use]
    pub fn mline(&self) -> Vec<Position> {
        let (Some(s), Some(g)) = (self.active_start, self.active_goal) else {
            return pyrust::vec::new!();
        };
        pyrust::collect!(pyrust::map!(pyrust::into_iter!(build_mline_seq(s.x, s.y, g.x, g.y)), |t| Position { x: t.0, y: t.1 }))
    }
}
