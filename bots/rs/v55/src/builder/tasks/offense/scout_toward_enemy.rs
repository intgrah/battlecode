//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/scout_toward_enemy.py`.
//!
//! Terminal OFFENSE fallback. Wraps `offense::helpers::scout_toward_enemy`
//! as a Task. Never rejects — guarantees the OFFENSE policy always produces
//! some movement, even when no harvester / cached target / conveyor target
//! is available.

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::tasks::offense::helpers::scout_toward_enemy as scout;
use crate::builder::tasks::rejected::TaskResult;

pub fn scout_toward_enemy(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    scout(self_, ct);
    Ok(())
}
