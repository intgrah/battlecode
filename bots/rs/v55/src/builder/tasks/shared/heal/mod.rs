//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/`.
//!
//! Heal tasks. Three flat leaves under one group:
//!   heal_buildings        — pick a damaged friendly building (deconflicted),
//!                           walk to it, heal in-range tiles before/after
//!                           the move.
//!   heal_adjacent_builder — heal a damaged friendly bot within action
//!                           range. No movement.
//!   heal_self             — heal own tile, with step-off when standing on
//!                           an enemy structure.

pub mod _helpers;
pub mod heal_adjacent_builder;
pub mod heal_buildings;
pub mod heal_self;

use crate::builder::tasks::_policy::{Policy, TaskGroup};

const HEAL_CHILDREN: &[Policy] = &[
    Policy::Leaf {
        name: "heal_buildings",
        fn_: heal_buildings::heal_buildings,
    },
    Policy::Leaf {
        name: "heal_adjacent_builder",
        fn_: heal_adjacent_builder::heal_adjacent_builder,
    },
    Policy::Leaf {
        name: "heal_self",
        fn_: heal_self::heal_self,
    },
];

pub static HEAL_GROUP_INNER: TaskGroup = TaskGroup {
    name: "heal",
    children: HEAL_CHILDREN,
    gate: None,
};

pub static HEAL_GROUP: Policy = Policy::Group(&HEAL_GROUP_INNER);
