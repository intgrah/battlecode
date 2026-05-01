//! Translation of `bots/intgrah/v54.7.9/builder/algorithms/econ_astar.py`.
//!
//! A*-on-Dial conveyor router. The `AStarSearch` instance keeps long-lived
//! buckets / bookkeeping so a paused search can resume next turn.

use std::collections::HashMap;

use cambc::{Controller, Position, ResourceType};

use crate::builder::algorithms::reachability::find as uf_find;
use crate::util::constants::{INF, MAX_N, MAX_WIDTH};

#[pyrust::inline]
const TARGET_DRIFT_SQ: i32 = 25;
#[pyrust::inline]
const BUCKET_COUNT: usize = 32;
#[pyrust::inline]
const BIDIRECTIONAL: bool = false;
#[pyrust::inline]
/// Diagonal (r²=2) is never a cardinal conveyor and never a legal bridge
/// (bridges need r² in [3, 9]), so any diagonal step materialises as a
/// bridge skipping to the next reachable tile along the path. Costed the
/// same as a bridge so A* doesn't prefer a diagonal over a bridge unless
/// the two cardinal alternatives are genuinely blocked.
const DIAG_WEIGHT: i32 = 9;

fn bridge_deltas() -> Vec<(i32, i32, i32)> {
    let mut out: Vec<(i32, i32, i32)> = pyrust::vec::new!();
    for dx in -3..=3i32 {
        for dy in -3..=3i32 {
            let d2 = dx * dx + dy * dy;
            if pyrust::vec::contains!((3..=9), &d2) {
                pyrust::vec::push!(out, (dx, dy, 9));
            }
        }
    }
    out
}

fn conv_neighbors() -> Vec<(i32, i32, i32)> {
    let mut out: Vec<(i32, i32, i32)> = vec![
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (1, 1, DIAG_WEIGHT),
        (1, -1, DIAG_WEIGHT),
        (-1, 1, DIAG_WEIGHT),
        (-1, -1, DIAG_WEIGHT),
    ];
    pyrust::vec::extend!(out, bridge_deltas());
    out
}

fn x_of_table() -> [i32; MAX_N] {
    let mut out = [0i32; MAX_N];
    for i in 0..MAX_N {
        out[i] = (i % MAX_WIDTH) as i32;
    }
    out
}

fn y_of_table() -> [i32; MAX_N] {
    let mut out = [0i32; MAX_N];
    for i in 0..MAX_N {
        out[i] = (i / MAX_WIDTH) as i32;
    }
    out
}

/// Subset of `Builder` state read/written by the A* search. The Builder
/// struct (Phase G6) embeds an instance of this and passes it to each
/// `search` call; the algorithm code never touches the rest of the Builder.
pub struct EconAstarCtx {
    pub ax_routable: [bool; MAX_N],
    pub ti_routable: [bool; MAX_N],
    pub routing_extra: [u8; MAX_N],
    pub reach_parent: [i32; MAX_N],
    pub my_pos: Position,
    pub nearby_tiles: Vec<Position>,
    pub all_bots: HashMap<Position, i32>,
}

pub struct AStarSearch {
    pub last_fail_reason: String,
    pub last_nodes_expanded: i32,
    /// Neighbour stencil (with extra cost) per cell. Bridge + diagonal
    /// (extra=9) and cardinal (extra=0) merged.
    neighbors: [Vec<(i32, i32)>; MAX_N],
    /// Cardinal-only neighbour list (flat int) for the inner loop.
    cardinal_neighbors: [Vec<i32>; MAX_N],
    /// Diagonal + bridge neighbours (all carry extra=9).
    weighted_neighbors: [Vec<i32>; MAX_N],
    pub _dist: [i32; MAX_N],
    dist_bwd: [i32; MAX_N],
    parent_fwd: [i32; MAX_N],
    parent_bwd: [i32; MAX_N],
    closed_fwd: [bool; MAX_N],
    closed_bwd: [bool; MAX_N],
    touched_fwd: Vec<i32>,
    touched_bwd: Vec<i32>,
    buckets_fwd: [Vec<i32>; BUCKET_COUNT],
    buckets_bwd: [Vec<i32>; BUCKET_COUNT],
    x_heur_fwd: [i32; MAX_WIDTH],
    y_heur_fwd: [i32; MAX_WIDTH],
    x_heur_bwd: [i32; MAX_WIDTH],
    y_heur_bwd: [i32; MAX_WIDTH],
    reach_root_cache: [i32; MAX_N],
    reach_root_touched: Vec<i32>,
    /// `f_at[ni]` caches the f-value (g + h) of the most recent push of ni
    /// into the open list. On pop, comparing `f_at[ni] != cur_f` is a cheap
    /// stale-check.
    f_at: [i32; MAX_N],
    finished: bool,
    target: Option<Position>,
    x_of: [i32; MAX_N],
    y_of: [i32; MAX_N],
}

impl AStarSearch {
    /// Construct a fresh search with all per-tile data structures pre-allocated.
    #[must_use]
    pub fn new() -> Self {
        let neighbors_template = conv_neighbors();
        let mut neighbors: [Vec<(i32, i32)>; MAX_N] = [const { Vec::new() }; MAX_N];
        let mut cardinal_neighbors: [Vec<i32>; MAX_N] = [const { Vec::new() }; MAX_N];
        let mut weighted_neighbors: [Vec<i32>; MAX_N] = [const { Vec::new() }; MAX_N];
        for cy in 0..MAX_WIDTH as i32 {
            for cx in 0..MAX_WIDTH as i32 {
                let i = (cy * MAX_WIDTH as i32 + cx) as usize;
                for &(dx, dy, extra) in &neighbors_template {
                    let nx = cx + dx;
                    let ny = cy + dy;
                    if 0 <= nx && nx < MAX_WIDTH as i32 && 0 <= ny && ny < MAX_WIDTH as i32 {
                        let ni = ny * (MAX_WIDTH as i32) + nx;
                        pyrust::vec::push!(neighbors[i], (ni, extra));
                        if extra == 0 {
                            pyrust::vec::push!(cardinal_neighbors[i], ni);
                        } else {
                            pyrust::vec::push!(weighted_neighbors[i], ni);
                        }
                    }
                }
            }
        }
        Self {
            last_fail_reason: pyrust::string::new!(),
            last_nodes_expanded: 0,
            neighbors,
            cardinal_neighbors,
            weighted_neighbors,
            _dist: [INF; MAX_N],
            dist_bwd: [INF; MAX_N],
            parent_fwd: [-1; MAX_N],
            parent_bwd: [-1; MAX_N],
            closed_fwd: [false; MAX_N],
            closed_bwd: [false; MAX_N],
            touched_fwd: pyrust::vec::new!(),
            touched_bwd: pyrust::vec::new!(),
            buckets_fwd: [const { Vec::new() }; BUCKET_COUNT],
            buckets_bwd: [const { Vec::new() }; BUCKET_COUNT],
            x_heur_fwd: [0; MAX_WIDTH],
            y_heur_fwd: [0; MAX_WIDTH],
            x_heur_bwd: [0; MAX_WIDTH],
            y_heur_bwd: [0; MAX_WIDTH],
            reach_root_cache: [-1; MAX_N],
            reach_root_touched: pyrust::vec::new!(),
            f_at: [0; MAX_N],
            finished: true,
            target: None,
            x_of: x_of_table(),
            y_of: y_of_table(),
        }
    }

    pub fn search(
        &mut self,
        start: Position,
        target: Position,
        resource: ResourceType,
        ctx: &mut EconAstarCtx,
    ) -> Option<Vec<Position>> {
        if BIDIRECTIONAL {
            return self.search_bidirectional(start, target, resource, ctx);
        }
        self.search_unidirectional(start, target, resource, ctx)
    }

    fn search_bidirectional(
        &mut self,
        start: Position,
        target: Position,
        resource: ResourceType,
        ctx: &mut EconAstarCtx,
    ) -> Option<Vec<Position>> {
        let stride = MAX_WIDTH as i32;
        let si = start.y * stride + start.x;
        let gi = target.y * stride + target.x;
        let gx = target.x;
        let gy = target.y;
        let sx = start.x;
        let sy = start.y;
        let dx = pyrust::abs!((gx - sx));
        let dy = pyrust::abs!((gy - sy));

        if si == gi {
            self.finished = true;
            self.target = Some(target);
            pyrust::string::clear!(self.last_fail_reason);
            self.last_nodes_expanded = 0;
            return Some(vec![start]);
        }
        if dx + dy == 1 {
            self.finished = true;
            self.target = Some(target);
            pyrust::string::clear!(self.last_fail_reason);
            self.last_nodes_expanded = 0;
            return Some(vec![start, target]);
        }

        let routable: &[bool] = if matches!(
            resource,
            ResourceType::RawAxionite | ResourceType::RefinedAxionite
        ) {
            &ctx.ax_routable
        } else {
            &ctx.ti_routable
        };
        let routing_extra = &ctx.routing_extra;
        for i in 0..MAX_WIDTH {
            self.x_heur_fwd[i] = pyrust::abs!(((i as i32) - gx));
            self.y_heur_fwd[i] = pyrust::abs!(((i as i32) - gy));
            self.x_heur_bwd[i] = pyrust::abs!(((i as i32) - sx));
            self.y_heur_bwd[i] = pyrust::abs!(((i as i32) - sy));
        }
        for &idx in &self.touched_fwd {
            self._dist[idx as usize] = INF;
            self.parent_fwd[idx as usize] = -1;
            self.closed_fwd[idx as usize] = false;
        }
        self.touched_fwd.clear();
        for &idx in &self.touched_bwd {
            self.dist_bwd[idx as usize] = INF;
            self.parent_bwd[idx as usize] = -1;
            self.closed_bwd[idx as usize] = false;
        }
        self.touched_bwd.clear();
        let my_root = uf_find(&mut ctx.reach_parent, ctx.my_pos.y * stride + ctx.my_pos.x);
        for &cached_i in &self.reach_root_touched {
            self.reach_root_cache[cached_i as usize] = -1;
        }
        self.reach_root_touched.clear();
        self.last_nodes_expanded = 0;
        self.target = Some(target);
        self.finished = false;

        self._dist[si as usize] = 0;
        self.parent_fwd[si as usize] = si;
        pyrust::vec::push!(self.touched_fwd, si);
        self.dist_bwd[gi as usize] = 0;
        self.parent_bwd[gi as usize] = gi;
        pyrust::vec::push!(self.touched_bwd, gi);

        let nb_count = BUCKET_COUNT as i32;
        let bucket_mask = nb_count - 1;
        let f0 = self.x_heur_fwd[sx as usize] + self.y_heur_fwd[sy as usize];
        for bucket in &mut self.buckets_fwd {
            bucket.clear();
        }
        for bucket in &mut self.buckets_bwd {
            bucket.clear();
        }
        pyrust::vec::push!(self.buckets_fwd[(f0 & bucket_mask) as usize], si);
        pyrust::vec::push!(self.buckets_bwd[(f0 & bucket_mask) as usize], gi);
        let mut cur_fwd = f0;
        let mut cur_bwd = f0;
        let mut emp_fwd: i32 = 0;
        let mut emp_bwd: i32 = 0;
        let mut best_cost = INF;
        let mut best_meet: i32 = -1;

        while emp_fwd < nb_count && emp_bwd < nb_count {
            while emp_fwd < nb_count
                && pyrust::vec::is_empty!(self.buckets_fwd[(cur_fwd & bucket_mask) as usize])
            {
                cur_fwd += 1;
                emp_fwd += 1;
            }
            while emp_bwd < nb_count
                && pyrust::vec::is_empty!(self.buckets_bwd[(cur_bwd & bucket_mask) as usize])
            {
                cur_bwd += 1;
                emp_bwd += 1;
            }
            if emp_fwd >= nb_count || emp_bwd >= nb_count {
                break;
            }
            if best_cost != INF && cur_fwd >= best_cost && cur_bwd >= best_cost {
                break;
            }

            if cur_fwd <= cur_bwd {
                let slot_fwd = (cur_fwd & bucket_mask) as usize;
                emp_fwd = 0;
                // Index-based iteration so relaxations pushed back into
                // this same bucket (same f-value) are picked up — that's
                // the common case for Manhattan-heuristic A* where every
                // step toward the goal preserves f. Snapshotting via
                // `mem::take` would silently drop them.
                let mut idx = 0;
                while idx < pyrust::len!(self.buckets_fwd[slot_fwd]) {
                    let node_i = self.buckets_fwd[slot_fwd][idx];
                    idx += 1;
                    let gn = self._dist[node_i as usize];
                    if self.closed_fwd[node_i as usize]
                        || gn
                            + self.x_heur_fwd[self.x_of[node_i as usize] as usize]
                            + self.y_heur_fwd[self.y_of[node_i as usize] as usize]
                            != cur_fwd
                    {
                        continue;
                    }
                    self.closed_fwd[node_i as usize] = true;
                    self.last_nodes_expanded += 1;
                    let other_dist = self.dist_bwd[node_i as usize];
                    if other_dist != INF {
                        let cand = gn + other_dist;
                        if cand < best_cost {
                            best_cost = cand;
                            best_meet = node_i;
                        }
                    }
                    let nbrs = &self.neighbors[node_i as usize];
                    for &(ni, extra) in nbrs {
                        if ni != gi {
                            if !routable[ni as usize] {
                                continue;
                            }
                            let rp = ctx.reach_parent[ni as usize];
                            if rp == -1 {
                                continue;
                            }
                            if rp != my_root {
                                let mut root = self.reach_root_cache[ni as usize];
                                if root == -1 {
                                    root = uf_find(&mut ctx.reach_parent, ni);
                                    self.reach_root_cache[ni as usize] = root;
                                    pyrust::vec::push!(self.reach_root_touched, ni);
                                }
                                if root != my_root {
                                    continue;
                                }
                            }
                        }
                        let nd = gn + 1 + extra + i32::from(routing_extra[ni as usize]);
                        if nd >= self._dist[ni as usize] {
                            continue;
                        }
                        if self._dist[ni as usize] == INF {
                            pyrust::vec::push!(self.touched_fwd, ni);
                        }
                        self._dist[ni as usize] = nd;
                        self.parent_fwd[ni as usize] = node_i;
                        let h_val = self.x_heur_fwd[self.x_of[ni as usize] as usize]
                            + self.y_heur_fwd[self.y_of[ni as usize] as usize];
                        pyrust::vec::push!(
                            self.buckets_fwd[((nd + h_val) & bucket_mask) as usize],
                            ni
                        );
                        let other_dist = self.dist_bwd[ni as usize];
                        if other_dist != INF {
                            let cand = nd + other_dist;
                            if cand < best_cost {
                                best_cost = cand;
                                best_meet = ni;
                            }
                        }
                    }
                }
                self.buckets_fwd[slot_fwd].clear();
                cur_fwd += 1;
                continue;
            }
            let slot_bwd = (cur_bwd & bucket_mask) as usize;
            emp_bwd = 0;
            let mut idx = 0;
            while idx < pyrust::len!(self.buckets_bwd[slot_bwd]) {
                let node_i = self.buckets_bwd[slot_bwd][idx];
                idx += 1;
                let gn = self.dist_bwd[node_i as usize];
                if self.closed_bwd[node_i as usize]
                    || gn
                        + self.x_heur_bwd[self.x_of[node_i as usize] as usize]
                        + self.y_heur_bwd[self.y_of[node_i as usize] as usize]
                        != cur_bwd
                {
                    continue;
                }
                self.closed_bwd[node_i as usize] = true;
                self.last_nodes_expanded += 1;
                let other_dist = self._dist[node_i as usize];
                if other_dist != INF {
                    let cand = gn + other_dist;
                    if cand < best_cost {
                        best_cost = cand;
                        best_meet = node_i;
                    }
                }
                let nbrs = &self.neighbors[node_i as usize];
                for &(ni, extra) in nbrs {
                    if ni != si {
                        if !routable[ni as usize] {
                            continue;
                        }
                        let rp = ctx.reach_parent[ni as usize];
                        if rp == -1 {
                            continue;
                        }
                        if rp != my_root {
                            let mut root = self.reach_root_cache[ni as usize];
                            if root == -1 {
                                root = uf_find(&mut ctx.reach_parent, ni);
                                self.reach_root_cache[ni as usize] = root;
                                pyrust::vec::push!(self.reach_root_touched, ni);
                            }
                            if root != my_root {
                                continue;
                            }
                        }
                    }
                    let nd = gn + 1 + extra + i32::from(routing_extra[ni as usize]);
                    if nd >= self.dist_bwd[ni as usize] {
                        continue;
                    }
                    if self.dist_bwd[ni as usize] == INF {
                        pyrust::vec::push!(self.touched_bwd, ni);
                    }
                    self.dist_bwd[ni as usize] = nd;
                    self.parent_bwd[ni as usize] = node_i;
                    let h_val = self.x_heur_bwd[self.x_of[ni as usize] as usize]
                        + self.y_heur_bwd[self.y_of[ni as usize] as usize];
                    pyrust::vec::push!(self.buckets_bwd[((nd + h_val) & bucket_mask) as usize], ni);
                    let other_dist = self._dist[ni as usize];
                    if other_dist != INF {
                        let cand = nd + other_dist;
                        if cand < best_cost {
                            best_cost = cand;
                            best_meet = ni;
                        }
                    }
                }
            }
            self.buckets_bwd[slot_bwd].clear();
            cur_bwd += 1;
        }

        self.finished = true;
        if best_meet == -1 {
            self.last_fail_reason = pyrust::to_string!("exhausted");
            return None;
        }

        let mut rev_path: Vec<i32> = vec![best_meet];
        let mut node = best_meet;
        while node != si {
            node = self.parent_fwd[node as usize];
            if node == -1 {
                self.last_fail_reason = pyrust::to_string!("extraction_stuck");
                return None;
            }
            pyrust::vec::push!(rev_path, node);
        }
        pyrust::vec::reverse!(rev_path);
        node = best_meet;
        while node != gi {
            node = self.parent_bwd[node as usize];
            if node == -1 {
                self.last_fail_reason = pyrust::to_string!("extraction_stuck");
                return None;
            }
            pyrust::vec::push!(rev_path, node);
        }

        pyrust::string::clear!(self.last_fail_reason);
        Some(pyrust::collect!(pyrust::map!(
            pyrust::into_iter!(rev_path),
            |i| Position {
                x: self.x_of[i as usize],
                y: self.y_of[i as usize],
            }
        )))
    }

    fn search_unidirectional(
        &mut self,
        start: Position,
        target: Position,
        resource: ResourceType,
        ctx: &mut EconAstarCtx,
    ) -> Option<Vec<Position>> {
        let stride = MAX_WIDTH as i32;
        let si = start.y * stride + start.x;
        let mut gi = target.y * stride + target.x;
        let mut resumed_search = false;

        // Cross-turn resumption: reset `_dist` only when the previous search
        // finished or the target has drifted. Otherwise keep accumulated
        // distances so the search can continue where the last turn's CPU
        // budget ran out.
        let mut target = target;
        if self.finished
            || pyrust::is_none!(self.target)
            || target.distance_squared(pyrust::unwrap!(self.target)) > TARGET_DRIFT_SQ
        {
            pyrust::vec::fill!(self._dist, INF);
            self.target = Some(target);
        } else {
            resumed_search = true;
            target = pyrust::unwrap!(self.target);
            gi = target.y * stride + target.x;
        }

        let routable: &[bool] = if matches!(
            resource,
            ResourceType::RawAxionite | ResourceType::RefinedAxionite
        ) {
            &ctx.ax_routable
        } else {
            &ctx.ti_routable
        };
        let routing_extra = &ctx.routing_extra;
        let sx = start.x;
        let sy = start.y;
        for i in 0..MAX_WIDTH {
            self.x_heur_fwd[i] = pyrust::abs!(((i as i32) - sx));
            self.y_heur_fwd[i] = pyrust::abs!(((i as i32) - sy));
        }
        let my_root = uf_find(&mut ctx.reach_parent, ctx.my_pos.y * stride + ctx.my_pos.x);
        for &cached_i in &self.reach_root_touched {
            self.reach_root_cache[cached_i as usize] = -1;
        }
        self.reach_root_touched.clear();
        let mut nodes_expanded = 0;

        if self._dist[gi as usize] == INF {
            self._dist[gi as usize] = 0;
        }

        let nb_count = BUCKET_COUNT as i32;
        let bucket_mask = nb_count - 1;
        let gx = target.x;
        let gy = target.y;
        let f0 = self.x_heur_fwd[gx as usize] + self.y_heur_fwd[gy as usize];
        for bucket in &mut self.buckets_fwd {
            bucket.clear();
        }
        pyrust::vec::push!(self.buckets_fwd[(f0 & bucket_mask) as usize], gi);
        self.f_at[gi as usize] = f0;
        let mut cur_f = f0;
        let mut emp: i32 = 0;

        let mut found = false;
        while emp < nb_count {
            if pyrust::vec::is_empty!(self.buckets_fwd[(cur_f & bucket_mask) as usize]) {
                cur_f += 1;
                emp += 1;
                continue;
            }
            emp = 0;
            let slot = (cur_f & bucket_mask) as usize;
            // Index-based iteration: relaxations pushed back into this
            // same f-bucket (the common case for Manhattan-heuristic A*
            // since every step toward the goal preserves f) must be
            // picked up. Snapshotting via `mem::take` would drop them.
            let mut idx = 0;
            while idx < pyrust::len!(self.buckets_fwd[slot]) {
                let node_i = self.buckets_fwd[slot][idx];
                idx += 1;
                if self.f_at[node_i as usize] != cur_f {
                    continue;
                }
                nodes_expanded += 1;
                if node_i == si {
                    found = true;
                    break;
                }
                let gn = self._dist[node_i as usize];
                let base_nd = gn + 1;
                let weighted_nd = base_nd + 9;
                let cardinals = &self.cardinal_neighbors[node_i as usize];
                for &ni in cardinals {
                    if !routable[ni as usize] {
                        continue;
                    }
                    let rp = ctx.reach_parent[ni as usize];
                    if rp != my_root {
                        if rp == -1 {
                            continue;
                        }
                        let mut root = self.reach_root_cache[ni as usize];
                        if root == -1 {
                            root = uf_find(&mut ctx.reach_parent, ni);
                            self.reach_root_cache[ni as usize] = root;
                            pyrust::vec::push!(self.reach_root_touched, ni);
                        }
                        if root != my_root {
                            continue;
                        }
                    }
                    let nd = base_nd + i32::from(routing_extra[ni as usize]);
                    if nd >= self._dist[ni as usize] {
                        continue;
                    }
                    self._dist[ni as usize] = nd;
                    let nf = nd
                        + self.x_heur_fwd[self.x_of[ni as usize] as usize]
                        + self.y_heur_fwd[self.y_of[ni as usize] as usize];
                    self.f_at[ni as usize] = nf;
                    pyrust::vec::push!(self.buckets_fwd[(nf & bucket_mask) as usize], ni);
                }
                let weighted = &self.weighted_neighbors[node_i as usize];
                for &ni in weighted {
                    if !routable[ni as usize] {
                        continue;
                    }
                    let rp = ctx.reach_parent[ni as usize];
                    if rp != my_root {
                        if rp == -1 {
                            continue;
                        }
                        let mut root = self.reach_root_cache[ni as usize];
                        if root == -1 {
                            root = uf_find(&mut ctx.reach_parent, ni);
                            self.reach_root_cache[ni as usize] = root;
                            pyrust::vec::push!(self.reach_root_touched, ni);
                        }
                        if root != my_root {
                            continue;
                        }
                    }
                    let nd = weighted_nd + i32::from(routing_extra[ni as usize]);
                    if nd >= self._dist[ni as usize] {
                        continue;
                    }
                    self._dist[ni as usize] = nd;
                    let nf = nd
                        + self.x_heur_fwd[self.x_of[ni as usize] as usize]
                        + self.y_heur_fwd[self.y_of[ni as usize] as usize];
                    self.f_at[ni as usize] = nf;
                    pyrust::vec::push!(self.buckets_fwd[(nf & bucket_mask) as usize], ni);
                }
            }
            self.buckets_fwd[slot].clear();
            if found {
                break;
            }
            cur_f += 1;
        }

        self.finished = true;
        self.last_nodes_expanded = nodes_expanded;
        if !found {
            self.last_fail_reason = pyrust::to_string!("exhausted");
            return None;
        }

        let mut path: Vec<i32> = vec![si];
        let mut node = si;
        let mut cur_d = self._dist[si as usize];
        if resumed_search {
            while node != gi {
                let mut best_dist = cur_d;
                let mut best = node;
                let nbrs = &self.neighbors[node as usize];
                for &(ni, extra) in nbrs {
                    let mut d = self._dist[ni as usize];
                    if d == INF {
                        continue;
                    }
                    if ni != gi {
                        if !routable[ni as usize] {
                            continue;
                        }
                        let rp = ctx.reach_parent[ni as usize];
                        if rp == -1 {
                            continue;
                        }
                        if rp != my_root {
                            let mut root = self.reach_root_cache[ni as usize];
                            if root == -1 {
                                root = uf_find(&mut ctx.reach_parent, ni);
                                self.reach_root_cache[ni as usize] = root;
                                pyrust::vec::push!(self.reach_root_touched, ni);
                            }
                            if root != my_root {
                                continue;
                            }
                        }
                    }
                    d += extra;
                    if d < best_dist {
                        best_dist = d;
                        best = ni;
                    }
                }
                if best == node {
                    self.last_fail_reason = pyrust::to_string!("extraction_stuck");
                    return None;
                }
                pyrust::vec::push!(path, best);
                node = best;
                cur_d = best_dist;
            }
        } else {
            while node != gi {
                let mut best_dist = cur_d;
                let mut best = node;
                let nbrs = &self.neighbors[node as usize];
                for &(ni, extra) in nbrs {
                    let mut d = self._dist[ni as usize];
                    if d == INF {
                        continue;
                    }
                    d += extra;
                    if d < best_dist {
                        best_dist = d;
                        best = ni;
                    }
                }
                if best == node {
                    self.last_fail_reason = pyrust::to_string!("extraction_stuck");
                    return None;
                }
                pyrust::vec::push!(path, best);
                node = best;
                cur_d = best_dist;
            }
        }

        pyrust::string::clear!(self.last_fail_reason);
        Some(pyrust::collect!(pyrust::map!(
            pyrust::into_iter!(path),
            |i| Position {
                x: self.x_of[i as usize],
                y: self.y_of[i as usize],
            }
        )))
    }

    /// Run `search` but treat tiles occupied by other friendly bots as
    /// non-routable. Mutates `ti_routable` / `ax_routable` temporarily.
    pub fn search_blocked(
        &mut self,
        ct: &mut Controller<'_>,
        start: Position,
        goal: Position,
        ctx: &mut EconAstarCtx,
    ) -> Option<Vec<Position>> {
        let stride = MAX_WIDTH as i32;
        let mut saved: Vec<(usize, bool, bool)> = pyrust::vec::new!();
        let nearby = pyrust::clone!(ctx.nearby_tiles);
        for pos in &nearby {
            if pyrust::dict::contains!(ctx.all_bots, pos) && *pos != start {
                let idx = (pos.y * stride + pos.x) as usize;
                pyrust::vec::push!(saved, (idx, ctx.ti_routable[idx], ctx.ax_routable[idx]));
                ctx.ti_routable[idx] = false;
                ctx.ax_routable[idx] = false;
            }
        }
        let result = self.search(start, goal, ResourceType::Titanium, ctx);
        for (idx, ti_val, ax_val) in saved {
            ctx.ti_routable[idx] = ti_val;
            ctx.ax_routable[idx] = ax_val;
        }
        result
    }
}

impl Default for AStarSearch {
    fn default() -> Self {
        Self::new()
    }
}
