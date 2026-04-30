//! Translation of `bots/intgrah/v54.7.9/builder/algorithms/reachability.py`.
//!
//! Incremental reachability via union-find.
//!
//! `parent[i] == -1`  : tile i has not been admitted (no evidence it is
//!                      part of a reachable component).
//! `parent[i] == i`   : tile i is a component root.
//! `parent[i] != -1`  : tile i is admitted; follow parent pointers to the
//!                      root.
//!
//! Two admission triggers:
//! 1. **Seed**: when a building is observed on a tile (any team), the tile
//!    is admitted as a singleton component (parent[i] = i) and pushed to
//!    the frontier. The building proves the tile is reachable through
//!    *some* path (possibly outside our vision).
//! 2. **Flood**: when we pop a tile from the frontier and examine its
//!    8-connected neighbours, any neighbour with known non-WALL env is
//!    admitted into the popper's component and pushed to the frontier.
//!
//! The frontier persists across turns. We pop up to `K_PER_TURN` tiles per
//! turn. This bounds the per-turn cost without giving up eventual
//! completeness.
//!
//! Note that "reachable" here is map-property reachability — barriers are
//! considered reachable, since they sit on non-WALL tiles that something
//! walked onto to place them.

use cambc::Environment;

use crate::util::constants::MAX_WIDTH;

/// Hard cap on frontier pops per turn.
pub const K_PER_TURN: usize = 25;

/// 8-connected neighbour offsets in flat index space.
const DELTAS: [i32; 8] = [
    -(MAX_WIDTH as i32) - 1,
    -(MAX_WIDTH as i32),
    -(MAX_WIDTH as i32) + 1,
    -1,
    1,
    MAX_WIDTH as i32 - 1,
    MAX_WIDTH as i32,
    MAX_WIDTH as i32 + 1,
];

/// Find with path-halving. `parent[i]` must be `!= -1`.
pub fn find(parent: &mut [i32], mut i: i32) -> i32 {
    while parent[i as usize] != i {
        let p = parent[i as usize];
        parent[i as usize] = parent[p as usize];
        i = parent[i as usize];
    }
    i
}

/// Read-only find without path-halving. Walks the parent chain.
/// `parent[i]` must be `!= -1`.
pub fn find_ro(parent: &[i32], mut i: i32) -> i32 {
    while parent[i as usize] != i {
        i = parent[i as usize];
    }
    i
}

/// Union by minimum id (stable component ids).
pub fn union(parent: &mut [i32], a: i32, b: i32) {
    let ra = find(parent, a);
    let rb = find(parent, b);
    if ra == rb {
        return;
    }
    if ra < rb {
        parent[rb as usize] = ra;
    } else {
        parent[ra as usize] = rb;
    }
}

/// Pop up to K tiles from the frontier and expand 8-connected.
///
/// Neighbour rules:
/// - off-map / out of W*H interior: skip
/// - parent[n] != -1 (already admitted): union with current
/// - env[n] is non-WALL and known: admit n into current component, push
/// - otherwise (env unknown or env == WALL): skip
pub fn step_reachability(
    parent: &mut [i32],
    frontier: &mut Vec<i32>,
    env: &[Option<Environment>],
    w: i32,
    h: i32,
) {
    let stride = MAX_WIDTH as i32;
    let parent_len = parent.len() as i32;
    for _ in 0..K_PER_TURN {
        let Some(i) = frontier.pop() else {
            return;
        };
        let mut cur_root = find(parent, i);
        let cy = i / stride;
        let cx = i % stride;
        for &d in &DELTAS {
            let n = i + d;
            if n < 0 || n >= parent_len {
                continue;
            }
            let ny = n / stride;
            let nx = n % stride;
            if (ny - cy).abs() > 1 || (nx - cx).abs() > 1 {
                continue;
            }
            if nx >= w || ny >= h {
                continue;
            }
            if parent[n as usize] != -1 {
                // Already admitted — union components.
                let nr = find(parent, n);
                if nr != cur_root {
                    if nr < cur_root {
                        parent[cur_root as usize] = nr;
                        cur_root = nr;
                    } else {
                        parent[nr as usize] = cur_root;
                    }
                }
                continue;
            }
            let e = env[n as usize];
            if e.is_none() || e == Some(Environment::Wall) {
                continue;
            }
            parent[n as usize] = cur_root;
            frontier.push(n);
        }
    }
}

/// Per-turn entry point. Building admissions happen at vision time
/// (see `_add_topology`); this just drains the frontier within budget.
pub fn update_reachability(
    parent: &mut [i32],
    frontier: &mut Vec<i32>,
    env: &[Option<Environment>],
    w: i32,
    h: i32,
) {
    step_reachability(parent, frontier, env, w, h);
}
