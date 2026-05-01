use cambc::{Environment, Position};

use crate::builder::Builder;
use crate::util::constants::{INF, MAX_WIDTH, ROAD_COST};

const _REFLECT_BUDGET: usize = 25;

/// Drain the reflect queue. No-op if symmetry isn't resolved yet —
/// `update_vision` still enqueues new observations, they just sit until
/// symmetry is known. Once resolved, `_REFLECT_BUDGET` tiles per turn
/// have their mirrored env populated and the passable-neighbour /
/// cost-grid / routability flags refreshed. Reflected tiles are NOT
/// re-enqueued: the mirror of a mirror is the original, which by
/// definition is already set.
pub fn update_reflect(builder: &mut Builder) {
    let Some(sym) = builder.symmetry else {
        return;
    };
    let w = builder.state.width;
    let h = builder.state.height;
    let n = builder.reflect_queue.len().min(_REFLECT_BUDGET);
    for _ in 0..n {
        let i = pyrust::unwrap!(builder.reflect_queue.pop_front());
        let t = Position {
            x: (i % MAX_WIDTH) as i32,
            y: (i / MAX_WIDTH) as i32,
        };
        let m = sym.action(t, w, h);
        let mi = (m.y as usize) * MAX_WIDTH + (m.x as usize);
        if pyrust::is_some!(builder.env[mi]) {
            continue;
        }
        let env = builder.env[i];
        builder.env[mi] = env;
        let (cost, buildable) = match env {
            Some(Environment::Wall) => (INF, false),
            Some(Environment::Empty) => (ROAD_COST, true),
            _ => (ROAD_COST, false),
        };
        builder.cost_grid[mi] = cost;
        if builder.buildable[mi] != buildable {
            builder.buildable[mi] = buildable;
            builder.ti_routable[mi] = buildable && !builder.ti_leakage[mi];
            builder.ax_routable[mi] = buildable && !builder.ax_leakage[mi];
        }
        builder.update_pnb(mi);
    }
}
