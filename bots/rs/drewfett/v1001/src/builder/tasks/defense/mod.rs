//! Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/`.
//!
//! DEFENSE role policy tree.

pub mod clear_enemy_turret;
pub mod patrol_cheap;
pub mod patrol_late;
pub mod stalk_enemy;

use crate::builder::tasks::_policy::{Policy, TaskGroup};
use crate::builder::tasks::defense::patrol_cheap::patrol_cheap;
use crate::builder::tasks::defense::patrol_late::patrol_late;
use crate::builder::tasks::defense::stalk_enemy::stalk_enemy;
use crate::builder::tasks::econ::chains::extend_chain_approach::extend_chain_approach;
use crate::builder::tasks::econ::chains::extend_chain_in_range::extend_chain_in_range;
use crate::builder::tasks::econ::infrastructure::ECON_INFRASTRUCTURE_GROUP;
use crate::builder::tasks::econ::ore::build_harvester::build_harvester;
use crate::builder::tasks::econ::ore::claim_ore::claim_ore;
use crate::builder::tasks::shared::explore::explore;
use crate::builder::tasks::shared::heal::HEAL_GROUP;
use crate::builder::tasks::shared::opportunistic_attack::opportunistic_attack;
use crate::builder::tasks::shared::wander::wander;

const DEFENSE_CHILDREN: &[Policy] = &[
    ECON_INFRASTRUCTURE_GROUP,
    Policy::Leaf {
        name: "extend_chain_in_range",
        fn_: extend_chain_in_range,
    },
    HEAL_GROUP,
    Policy::Leaf {
        name: "stalk_enemy",
        fn_: stalk_enemy,
    },
    Policy::Leaf {
        name: "patrol_cheap",
        fn_: patrol_cheap,
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
        name: "opportunistic_attack",
        fn_: opportunistic_attack,
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

pub static DEFENSE_GROUP_INNER: TaskGroup = TaskGroup {
    name: "defense",
    children: DEFENSE_CHILDREN,
    gate: None,
};

pub static DEFENSE_GROUP: Policy = Policy::Group(&DEFENSE_GROUP_INNER);
