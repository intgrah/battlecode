//! Parasitic-attack subtree: walk toward an enemy harvester / cached
//! target / enemy conveyor and fire from adjacent tiles. Last-resort
//! offense once the cheap fire / turret / push branches have all rejected.

pub mod approach_harvester;
pub mod chew_conveyor;
pub mod walk_to_cached_target;

use crate::builder::tasks::_policy::{Policy, TaskGroup};

const OFFENSE_PARASITIC_CHILDREN: &[Policy] = &[
    Policy::Leaf {
        name: "approach_harvester",
        fn_: approach_harvester::approach_harvester,
    },
    Policy::Leaf {
        name: "walk_to_cached_target",
        fn_: walk_to_cached_target::walk_to_cached_target,
    },
    Policy::Leaf {
        name: "chew_conveyor",
        fn_: chew_conveyor::chew_conveyor,
    },
];

pub static OFFENSE_PARASITIC_GROUP_INNER: TaskGroup = TaskGroup {
    name: "parasitic",
    children: OFFENSE_PARASITIC_CHILDREN,
    gate: None,
};

pub static OFFENSE_PARASITIC_GROUP: Policy = Policy::Group(&OFFENSE_PARASITIC_GROUP_INNER);
