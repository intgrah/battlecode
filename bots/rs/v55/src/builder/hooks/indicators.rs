//! Translation of `bots/intgrah/v54.7.9/builder/hooks/indicators.py`.

use cambc::Controller;

use crate::builder::Builder;
use crate::util::debug::dot;

/// Paint per-builder economy state into the replay: ore targets,
/// foundry target, chain endpoints. Only has effect when `DEBUG_LOG` is set
/// (the helpers in `util.log` are no-ops otherwise).
pub fn indicators(builder: &mut Builder, ct: &mut Controller<'_>) {
    if let Some(target) = builder.ore_target {
        dot(ct, target, 255, 220, 0);
    }
    if let Some(target) = builder.ax_ore_target {
        dot(ct, target, 200, 0, 200);
    }
    if let Some(target) = builder.offensive_ore_target {
        dot(ct, target, 255, 80, 0);
    }
    if let Some(target) = builder.foundry_target {
        dot(ct, target, 0, 200, 0);
    }
    if let Some(target) = builder.dangling_output {
        dot(ct, target, 0, 200, 200);
    }
}
