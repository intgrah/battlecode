//! drewfett v55 binary role.
//!
//! Replaces v54.7.9's 7-role taxonomy + random+transition machinery with
//! a deterministic spawn-time split: ~33% of builders are `Defender`
//! (stay near base, patrol/heal/turret), the rest are `Free`
//! (everything else, with positional gates on each task).
//!
//! Why binary:
//! - Tracking "how many defenders alive" requires global comms we don't
//!   have. Deterministic spawn pattern (every 3rd spawn → Defender)
//!   keeps the ratio approximately right without per-bot coordination.
//! - Free agents need only positional self-gating; their behaviour
//!   emerges from where they are + what's claimable. No role transitions.
//! - Defenders run a small, fixed defensive pipeline that pulls them
//!   back to our infrastructure regardless of where they currently are.

use core::fmt;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Role {
    /// Defensive bot. Patrols our economy, heals friendly damage,
    /// places defensive turrets, stalks enemies in our half.
    Defender,
    /// Everything else. Self-gates each task by position; emergent
    /// econ / push / parasitic / scout behaviour.
    Free,
}

impl fmt::Display for Role {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Defender => "defender",
            Self::Free => "free",
        })
    }
}
