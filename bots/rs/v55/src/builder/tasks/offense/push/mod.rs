//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/push/`.
//!
//! Forward-push subtree: drop sentinels on dangling ends, fork the
//! chain behind them with splitters, plant offensive harvesters on
//! enemy-side ore, extend chains toward the enemy core. The structural
//! offensive work — high-value, gated by symmetry being known.

pub mod build_offensive_harvester;
pub mod claim_offensive_ore;
pub mod place_offensive_sentinel;
pub mod push_extend;
pub mod split_before_sentinel;

use crate::builder::tasks::_policy::{Policy, TaskGroup};

const OFFENSE_PUSH_CHILDREN: &[Policy] = &[
    Policy::Leaf {
        name: "claim_offensive_ore",
        fn_: claim_offensive_ore::claim_offensive_ore,
    },
    Policy::Leaf {
        name: "place_offensive_sentinel",
        fn_: place_offensive_sentinel::place_offensive_sentinel,
    },
    Policy::Leaf {
        name: "split_before_sentinel",
        fn_: split_before_sentinel::split_before_sentinel,
    },
    Policy::Leaf {
        name: "build_offensive_harvester",
        fn_: build_offensive_harvester::build_offensive_harvester,
    },
    Policy::Leaf {
        name: "push_extend",
        fn_: push_extend::push_extend,
    },
];

pub static OFFENSE_PUSH_GROUP_INNER: TaskGroup = TaskGroup {
    name: "push",
    children: OFFENSE_PUSH_CHILDREN,
    gate: None,
};

pub static OFFENSE_PUSH_GROUP: Policy = Policy::Group(&OFFENSE_PUSH_GROUP_INNER);
