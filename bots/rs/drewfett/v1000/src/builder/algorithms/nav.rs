//! Translation of `bots/intgrah/v54.7.9/builder/algorithms/nav.py`.
//!
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

use std::collections::{HashMap, HashSet, VecDeque};

use cambc::Position;

use crate::builder::algorithms::bug2_planner::{Bug2Planner, build_mline_seq, path_is_passable};
use crate::builder::algorithms::dp_step::dp_step;
use crate::util::constants::{BOUND_RANGE, INF, STRIDE};
use crate::util::posint::idx_of;

const PLAN_BUDGET: i32 = 25;

/// WS-6: maximum number of cached `(start, target) → path` entries kept
/// across turns. FIFO-evicted on insert. Sized so memory is bounded across
/// up to ~50 living units; each entry is at most a few hundred Positions.
pub const BUG2_PATH_CACHE_CAP: usize = 32;

/// Subset of `Builder` state read by nav. Phase G6's `Builder` will populate
/// this each turn from its own fields and pass `&mut` to `step`.
pub struct NavCtx<'a> {
    pub my_pos: Position,
    pub cost_grid: &'a mut [i32; BOUND_RANGE],
    pub w: i32,
    pub h: i32,
    pub nearby_tiles: &'a [Position],
    pub all_bots: &'a HashMap<Position, i32>,
    /// WS-6: shared path cache (multi-turn). Key `(start, target)`, value
    /// is the cell sequence (start → target) that bug2 produced previously.
    pub path_cache: &'a mut HashMap<(Position, Position), Vec<Position>>,
    /// FIFO key order for bounded eviction.
    pub path_cache_order: &'a mut VecDeque<(Position, Position)>,
    /// Flat indices the planner should mask as INF on its first attempt.
    /// Populated from enemy launcher throw zones. Empty set = no mask.
    pub unsafe_tiles: &'a HashSet<usize>,
}

/// Per-builder navigation state. One instance lives on each builder.
pub struct BugNav {
    // pyrust elides single-expr getters like `pub fn active_goal(&self) ->
    // Option<Position> { self.active_goal }` into bare field access in
    // Python. Calling `.active_goal()` then becomes `None()` at runtime.
    // Mark these `pub` so external callers (dump.rs) read the field
    // directly without parens — both Rust and translated Python work.
    pub active_goal: Option<Position>,
    active_start: Option<Position>,
    /// While a plan is in progress, the planner owns `path_idx`. Once the
    /// planner finishes (or we replan), `path_idx` is moved back into
    /// `path_idx_storage`.
    planner: Option<Bug2Planner>,
    pub gen_done: bool,
    /// Canonical `path_idx` storage when no planner is active.
    path_idx_storage: Vec<i32>,
    pub unreachable: bool,
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
            path_idx_storage: vec![-1; BOUND_RANGE],
            unreachable: false,
            committed: pyrust::vec::new!(),
        }
    }

    /// Read-only access to the current `path_idx` array (whether owned by the
    /// planner or by storage).
    fn path_idx(&self) -> &[i32] {
        match &self.planner {
            Some(p) => &p.path_idx,
            None => &self.path_idx_storage,
        }
    }

    /// Return the next position to move toward `goal`, or `None` if no
    /// progress can be made (no path or already at goal).
    ///
    /// Replans iff:
    ///   - goal changed since last call, OR
    ///   - the current plan has no tile visible to the bot (drifted off).
    /// Two-pass nav: first attempt masks `ctx.unsafe_tiles` (launcher
    /// throw zones) as INF in cost_grid; if no path exists, restore the
    /// mask and retry without it (accept the danger). The bot's own
    /// position and the goal tile are never masked (so a bot trapped
    /// inside a launcher zone can still leave, and goals exactly on the
    /// danger boundary are still reachable).
    pub fn step_safe(&mut self, ctx: &mut NavCtx<'_>, goal: Position) -> Option<Position> {
        if pyrust::vec::is_empty!(ctx.unsafe_tiles) {
            return self.step(ctx, goal);
        }

        let my_i = idx_of(ctx.my_pos) as usize;
        let goal_i = idx_of(goal) as usize;

        // Apply mask: snapshot prior cost values for unsafe tiles, then INF them.
        let mut saved: Vec<(usize, i32)> = Vec::with_capacity(pyrust::len!(ctx.unsafe_tiles));
        for &i in pyrust::iter!(ctx.unsafe_tiles) {
            if i == my_i || i == goal_i {
                continue;
            }
            if ctx.cost_grid[i] != INF {
                pyrust::vec::push!(saved, (i, ctx.cost_grid[i]));
                ctx.cost_grid[i] = INF;
            }
        }

        let result = self.step(ctx, goal);

        // Restore mask.
        for (i, v) in &saved {
            ctx.cost_grid[*i] = *v;
        }

        // Fallback: if pass 1 declared unreachable, retry without mask.
        if self.unreachable {
            self.unreachable = false;
            self.active_goal = None; // force replan from un-masked grid
            return self.step(ctx, goal);
        }
        result
    }

    pub fn step(&mut self, ctx: &mut NavCtx<'_>, goal: Position) -> Option<Position> {
        let pos = ctx.my_pos;
        if pos == goal {
            return None;
        }

        let stride = STRIDE as i32;
        let si = idx_of(pos);
        let gi = idx_of(goal);

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
                for _fill_i in 0..pyrust::len!(self.path_idx_storage) {
                    self.path_idx_storage[_fill_i] = -1;
                }
                self.path_idx_storage[si as usize] = 0;
                self.unreachable = false;
                self.committed = vec![si];

                // WS-6: cache lookup before bug2 invocation. On a valid
                // hit, populate path_idx + committed directly and skip the
                // planner. On a miss (or invalid entry), spawn the planner
                // and let the result be cached on completion.
                let cached_path: Option<Vec<Position>> =
                    if let Some(p) = ctx.path_cache.get(&(pos, goal)) {
                        if path_is_passable(p, ctx.cost_grid, stride as usize, ctx.w, ctx.h) {
                            Some(pyrust::clone!(p))
                        } else {
                            None
                        }
                    } else {
                        None
                    };
                if let Some(path) = cached_path {
                    // Replay cached path into path_idx_storage / committed.
                    for (i, p) in pyrust::enumerate!(pyrust::iter!(path)) {
                        let ci = idx_of(*p);
                        self.path_idx_storage[ci as usize] = i as i32;
                        if i > 0 {
                            pyrust::vec::push!(self.committed, ci);
                        }
                    }
                    self.gen_done = true;
                    self.planner = None;
                } else {
                    // Cache miss or invalidated entry — drop stale entry,
                    // then run bug2 from scratch.
                    if pyrust::is_some!(pyrust::dict::remove!(ctx.path_cache, &(pos, goal))) {
                        let _filtered: VecDeque<(Position, Position)> =
                            pyrust::collect!(pyrust::filter!(
                                pyrust::cloned!(pyrust::iter!(ctx.path_cache_order)),
                                |k| *k != (pos, goal)
                            ));
                        *ctx.path_cache_order = _filtered;
                    }
                    let path_idx = pyrust::clone!(self.path_idx_storage);
                    self.path_idx_storage = vec![-1; BOUND_RANGE];
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
            }

            if self.unreachable {
                return None;
            }

            if !self.gen_done && pyrust::is_some!(self.planner) {
                for _ in 0..PLAN_BUDGET {
                    let Some(planner) = &mut self.planner else {
                        break;
                    };
                    match planner.step(ctx.cost_grid) {
                        Some(true) => {
                            self.gen_done = true;
                            self.path_idx_storage =
                                pyrust::expect!(pyrust::opt_take!(self.planner), "planner is Some")
                                    .into_path_idx();
                            // WS-6: store completed plan in shared cache.
                            self.cache_committed_path(ctx, goal);
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
                let fi = idx_of(*fb_pos) as usize;
                pyrust::vec::push!(saved, (fi, ctx.cost_grid[fi]));
                ctx.cost_grid[fi] = INF;
            }
            let path_idx_ref: &[i32] = match &self.planner {
                Some(p) => &p.path_idx,
                None => &self.path_idx_storage,
            };
            let cur_min = path_idx_ref[si as usize];
            let nxt = dp_step(
                STRIDE as i32,
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

    /// WS-6: insert the just-completed `committed` path into the shared
    /// cache, keyed on `(active_start, goal)`. FIFO eviction caps memory at
    /// `BUG2_PATH_CACHE_CAP` entries.
    fn cache_committed_path(&self, ctx: &mut NavCtx<'_>, goal: Position) {
        let start = match self.active_start {
            Some(s) => s,
            None => return,
        };
        if pyrust::len!(self.committed) < 2 {
            return;
        }
        let stride = STRIDE as i32;
        let path: Vec<Position> =
            pyrust::collect!(pyrust::map!(pyrust::iter!(self.committed), |i| Position {
                x: i % stride,
                y: i / stride,
            }));
        let key = (start, goal);
        if !pyrust::dict::contains!(ctx.path_cache, &key) {
            pyrust::vec::push_back!(ctx.path_cache_order, key);
            while pyrust::len!(ctx.path_cache_order) > BUG2_PATH_CACHE_CAP {
                if let Some(evict) = pyrust::vec::pop_front!(ctx.path_cache_order) {
                    pyrust::dict::remove!(ctx.path_cache, &evict);
                }
            }
        }
        pyrust::dict::insert!(ctx.path_cache, key, path);
    }

    fn any_path_tile_visible(&self, nearby: &[Position]) -> bool {
        let path_idx = self.path_idx();
        for tile in nearby {
            if path_idx[idx_of(*tile) as usize] != -1 {
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
        let stride = STRIDE as i32;
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
