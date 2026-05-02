//! drewfett v55 deterministic spawn-time role assignment.
//!
//! Sets `builder.role` on the first turn based on the round the bot
//! spawned in. ~25% of spawns become `Defender`; the rest are `Free`.
//! Never re-rolls.
//!
//! Pattern: rounds 4, 8, 12, ... (i.e. `(round - 1) % 4 == 3`) are
//! Defenders. The first 3 spawns are `Free` so we get an econ-heavy
//! opening (no Ti spent on a defender that has nothing to defend yet);
//! by round 4 a Defender comes online. ~1-in-4 ratio thereafter, so a
//! lost Defender is replaced within ~16 rounds without per-bot
//! coordination.
//!
//! WS-3 (drewfett v1000): the period N is now per-template, derived
//! from `builder.opening` at `post_init` time. Template `DefaultBalanced`
//! keeps N=4 (current behaviour). `OpenEcon` -> N=5 (20% defenders),
//! `Corridor` -> N=4 (25%), `ChokeBunker` -> N=3 (~33% defenders). The
//! first N-1 spawns are always `Free` so the econ-heavy opening still
//! holds — the offset is `(round - 1) % N == N - 1`.

use crate::builder::Builder;
use crate::builder::role::Role;

pub fn update_role(builder: &mut Builder) {
    if pyrust::is_some!(builder.role) {
        return;
    }
    let n = builder.opening.defender_period();
    let r = builder.state.round - 1;
    let role = if r % n == n - 1 {
        Role::Defender
    } else {
        Role::Free
    };
    builder.role = Some(role);
}
