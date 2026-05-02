//! drewfett v55 task dispatch.
//!
//! Two pipelines:
//! - `DEFENDER_GROUP` — bots whose role is `Defender`. Pulls them back
//!   to our infrastructure; runs defensive tasks (heal / patrol / stalk
//!   / place_gunner) before falling through to econ.
//! - `FREE_GROUP` — bots whose role is `Free`. Opportunistic. Each task
//!   self-gates positionally; behaviour emerges from where the bot is +
//!   what's claimable.
//!
//! Deferred / dropped from v54.7.9:
//! - The 7-role taxonomy + random + transition matrix (replaced by
//!   binary deterministic split — see `role.rs`).
//! - PARASITIC / PUSH role-specific pipelines (folded into FREE_GROUP
//!   ordered after econ tasks; bots in enemy half naturally fall
//!   through to push/parasitic when their econ tasks reject).

pub mod _policy;
pub mod defense;
pub mod econ;
pub mod offense;
pub mod rejected;
pub mod shared;

use crate::builder::role::Role;
use crate::builder::tasks::_policy::{Policy, TaskGroup};
use crate::builder::tasks::defense::clear_enemy_turret::clear_enemy_turret;
use crate::builder::tasks::defense::patrol_cheap::patrol_cheap;
use crate::builder::tasks::defense::patrol_late::patrol_late;
use crate::builder::tasks::defense::stalk_enemy::stalk_enemy;
use crate::builder::tasks::econ::chains::extend_chain_approach::extend_chain_approach;
use crate::builder::tasks::econ::chains::extend_chain_in_range::extend_chain_in_range;
use crate::builder::tasks::econ::infrastructure::ECON_INFRASTRUCTURE_GROUP;
use crate::builder::tasks::econ::ore::build_harvester::build_harvester;
use crate::builder::tasks::econ::ore::claim_ore::claim_ore;
use crate::builder::tasks::offense::converge_on_rendezvous::converge_on_rendezvous;
use crate::builder::tasks::offense::fire_on_enemy_tile::fire_on_enemy_tile;
use crate::builder::tasks::offense::parasitic::OFFENSE_PARASITIC_GROUP;
use crate::builder::tasks::offense::push::OFFENSE_PUSH_GROUP;
use crate::builder::tasks::offense::push::split_before_sentinel::split_before_sentinel;
use crate::builder::tasks::offense::scout_toward_enemy::scout_toward_enemy;
use crate::builder::tasks::offense::turret_around_harvester::turret_around_harvester;
use crate::builder::tasks::shared::explore::explore;
use crate::builder::tasks::shared::heal::HEAL_GROUP;
use crate::builder::tasks::shared::opportunistic_attack::opportunistic_attack;
use crate::builder::tasks::shared::wander::wander;

// =====================================================================
// DEFENDER pipeline.
// =====================================================================
//
// Bots whose role is `Defender`. Goal: stay near our infrastructure,
// keep it alive, intercept threats. Falls through to econ when nothing
// defensive is claimable so a Defender bot near a free harvester still
// builds it.

const DEFENDER_CHILDREN: &[Policy] = &[
    Policy::Leaf {
        name: "fire_on_enemy_tile",
        fn_: fire_on_enemy_tile,
    },
    Policy::Leaf {
        name: "opportunistic_attack",
        fn_: opportunistic_attack,
    },
    HEAL_GROUP,
    ECON_INFRASTRUCTURE_GROUP,
    // Defensive turret-clearing — runs above stalk_enemy so when a
    // defender sees an enemy turret in our half, killing it via a
    // sentinel placed at a dangling chain tip takes priority over
    // chasing the launcher's bot.
    Policy::Leaf {
        name: "clear_enemy_turret",
        fn_: clear_enemy_turret,
    },
    // Right after placing a sentinel via clear_enemy_turret, upgrade the
    // upstream conveyor into a splitter so flow continues to core via
    // splitter side outputs. Without this, the chain dies at the sentinel.
    Policy::Leaf {
        name: "split_before_sentinel",
        fn_: split_before_sentinel,
    },
    Policy::Leaf {
        name: "stalk_enemy",
        fn_: stalk_enemy,
    },
    Policy::Leaf {
        name: "extend_chain_in_range",
        fn_: extend_chain_in_range,
    },
    Policy::Leaf {
        name: "claim_ore",
        fn_: claim_ore,
    },
    Policy::Leaf {
        name: "build_harvester",
        fn_: build_harvester,
    },
    Policy::Leaf {
        name: "extend_chain_approach",
        fn_: extend_chain_approach,
    },
    Policy::Leaf {
        name: "patrol_late",
        fn_: patrol_late,
    },
    Policy::Leaf {
        name: "patrol_cheap",
        fn_: patrol_cheap,
    },
    Policy::Leaf {
        name: "explore",
        fn_: explore,
    },
    Policy::Leaf {
        name: "wander",
        fn_: wander,
    },
];

pub static DEFENDER_GROUP_INNER: TaskGroup = TaskGroup {
    name: "defender",
    children: DEFENDER_CHILDREN,
    gate: None,
};

pub static DEFENDER_GROUP: Policy = Policy::Group(&DEFENDER_GROUP_INNER);

// =====================================================================
// FREE pipeline.
// =====================================================================
//
// Bots whose role is `Free`. Opportunistic; each task self-gates by
// position + claim-by-proximity. Order:
//   1. Reflexes (heal_self via HEAL_GROUP, opportunistic_attack, fire)
//   2. Defensive infra placement (place_gunner / etc.) when adjacent to
//      friendly harvester — incidental defense while passing through
//   3. Heal damaged friendlies (claim-by-proximity)
//   4. Offensive turret near enemy harvester (positional gate)
//   5. Econ (claim_ore, build_harvester, extend_chain)
//   6. Parasitic / push (visible enemy chain / enemy-side ore)
//   7. Stalk / deny / scout
//   8. Wander as final fallback
//
// Rationale: a Free bot near a friendly harvester might place a gunner
// (good) but won't patrol home if it wandered far (Defender's job).

const FREE_CHILDREN: &[Policy] = &[
    Policy::Leaf {
        name: "fire_on_enemy_tile",
        fn_: fire_on_enemy_tile,
    },
    Policy::Leaf {
        name: "opportunistic_attack",
        fn_: opportunistic_attack,
    },
    HEAL_GROUP,
    ECON_INFRASTRUCTURE_GROUP,
    // Defensive turret-clearing also runs in FREE pipeline — Free bots
    // near our chain that see an enemy launcher should kill it before
    // extending or pushing.
    Policy::Leaf {
        name: "clear_enemy_turret",
        fn_: clear_enemy_turret,
    },
    // Right after placing a sentinel via clear_enemy_turret, upgrade the
    // upstream conveyor into a splitter so flow continues to core via
    // splitter side outputs. Without this, the chain dies at the sentinel.
    Policy::Leaf {
        name: "split_before_sentinel",
        fn_: split_before_sentinel,
    },
    Policy::Leaf {
        name: "turret_around_harvester",
        fn_: turret_around_harvester,
    },
    Policy::Leaf {
        name: "extend_chain_in_range",
        fn_: extend_chain_in_range,
    },
    Policy::Leaf {
        name: "claim_ore",
        fn_: claim_ore,
    },
    Policy::Leaf {
        name: "build_harvester",
        fn_: build_harvester,
    },
    Policy::Leaf {
        name: "extend_chain_approach",
        fn_: extend_chain_approach,
    },
    Policy::Leaf {
        name: "converge_on_rendezvous",
        fn_: converge_on_rendezvous,
    },
    OFFENSE_PARASITIC_GROUP,
    OFFENSE_PUSH_GROUP,
    Policy::Leaf {
        name: "stalk_enemy",
        fn_: stalk_enemy,
    },
    Policy::Leaf {
        name: "scout_toward_enemy",
        fn_: scout_toward_enemy,
    },
    Policy::Leaf {
        name: "explore",
        fn_: explore,
    },
    Policy::Leaf {
        name: "wander",
        fn_: wander,
    },
];

pub static FREE_GROUP_INNER: TaskGroup = TaskGroup {
    name: "free",
    children: FREE_CHILDREN,
    gate: None,
};

pub static FREE_GROUP: Policy = Policy::Group(&FREE_GROUP_INNER);

/// Resolve a role to its top-level policy tree.
#[must_use]
pub fn policy_for_role(role: Role) -> &'static Policy {
    match role {
        Role::Defender => &DEFENDER_GROUP,
        Role::Free => &FREE_GROUP,
    }
}
