//! ECON role policy tree.

pub mod chains;
pub mod infrastructure;
pub mod ore;

use crate::builder::tasks::_policy::{Policy, TaskGroup};
use crate::builder::tasks::econ::chains::extend_chain_approach::extend_chain_approach;
use crate::builder::tasks::econ::chains::extend_chain_in_range::extend_chain_in_range;
use crate::builder::tasks::econ::infrastructure::ECON_INFRASTRUCTURE_GROUP;
use crate::builder::tasks::econ::ore::build_harvester::build_harvester;
use crate::builder::tasks::econ::ore::claim_ore::claim_ore;
use crate::builder::tasks::shared::explore::explore;
use crate::builder::tasks::shared::heal::HEAL_GROUP;
use crate::builder::tasks::shared::wander::wander;

const ECON_CHILDREN: &[Policy] = &[
    ECON_INFRASTRUCTURE_GROUP,
    Policy::Leaf {
        name: "extend_chain_in_range",
        fn_: extend_chain_in_range,
    },
    HEAL_GROUP,
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
        name: "explore",
        fn_: explore,
    },
    Policy::Leaf {
        name: "wander",
        fn_: wander,
    },
];

pub static ECON_GROUP_INNER: TaskGroup = TaskGroup {
    name: "econ",
    children: ECON_CHILDREN,
    gate: None,
};

pub static ECON_GROUP: Policy = Policy::Group(&ECON_GROUP_INNER);
