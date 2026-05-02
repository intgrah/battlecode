//! Translation of `bots/intgrah/v54.7.9/builder/tasks/defense/`.
//!
//! DEFENSE role policy tree.

pub mod patrol;
pub mod stalk_enemy;

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::tasks::_policy::{Policy, TaskGroup};
use crate::builder::tasks::defense::patrol::patrol;
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

fn _alert_high(self_: &mut Builder, _ct: &mut Controller<'_>) -> bool {
    self_.alert > 0
}

fn _alert_zero(self_: &mut Builder, _ct: &mut Controller<'_>) -> bool {
    self_.alert == 0
}

const ALERT_PATROL_CHILDREN: &[Policy] = &[Policy::Leaf {
    name: "patrol",
    fn_: patrol,
}];

pub static ALERT_PATROL_GROUP_INNER: TaskGroup = TaskGroup {
    name: "alert_patrol",
    children: ALERT_PATROL_CHILDREN,
    gate: Some(_alert_high),
};

pub static ALERT_PATROL_GROUP: Policy = Policy::Group(&ALERT_PATROL_GROUP_INNER);

const ALERT_ZERO_ECON_CHILDREN: &[Policy] = &[
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
];

pub static ALERT_ZERO_ECON_GROUP_INNER: TaskGroup = TaskGroup {
    name: "alert_zero_econ",
    children: ALERT_ZERO_ECON_CHILDREN,
    gate: Some(_alert_zero),
};

pub static ALERT_ZERO_ECON_GROUP: Policy = Policy::Group(&ALERT_ZERO_ECON_GROUP_INNER);

const DEFENSE_CHILDREN: &[Policy] = &[
    HEAL_GROUP,
    Policy::Leaf {
        name: "stalk_enemy",
        fn_: stalk_enemy,
    },
    ECON_INFRASTRUCTURE_GROUP,
    ALERT_PATROL_GROUP,
    ALERT_ZERO_ECON_GROUP,
    Policy::Leaf {
        name: "patrol_fallback",
        fn_: patrol,
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
