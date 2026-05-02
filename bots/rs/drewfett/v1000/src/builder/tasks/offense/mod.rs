//! Translation of `bots/intgrah/v54.7.9/builder/tasks/offense/`.
//!
//! Offense role policy trees.

pub mod converge_on_rendezvous;
pub mod fire_on_enemy_tile;
pub mod helpers;
pub mod parasitic;
pub mod push;
pub mod scout_toward_enemy;
pub mod turret_around_harvester;

use crate::builder::tasks::_policy::{Policy, TaskGroup};
use crate::builder::tasks::offense::fire_on_enemy_tile::fire_on_enemy_tile;
use crate::builder::tasks::offense::parasitic::OFFENSE_PARASITIC_GROUP;
use crate::builder::tasks::offense::push::OFFENSE_PUSH_GROUP;
use crate::builder::tasks::offense::scout_toward_enemy::scout_toward_enemy;
use crate::builder::tasks::offense::turret_around_harvester::turret_around_harvester;
use crate::builder::tasks::shared::heal::HEAL_GROUP;

const PUSH_ROLE_CHILDREN: &[Policy] = &[
    HEAL_GROUP,
    Policy::Leaf {
        name: "fire_on_enemy_tile",
        fn_: fire_on_enemy_tile,
    },
    Policy::Leaf {
        name: "turret_around_harvester",
        fn_: turret_around_harvester,
    },
    OFFENSE_PUSH_GROUP,
    Policy::Leaf {
        name: "scout_toward_enemy",
        fn_: scout_toward_enemy,
    },
];

pub static PUSH_ROLE_GROUP_INNER: TaskGroup = TaskGroup {
    name: "push",
    children: PUSH_ROLE_CHILDREN,
    gate: None,
};

pub static PUSH_ROLE_GROUP: Policy = Policy::Group(&PUSH_ROLE_GROUP_INNER);

const PARASITIC_ROLE_CHILDREN: &[Policy] = &[
    HEAL_GROUP,
    Policy::Leaf {
        name: "fire_on_enemy_tile",
        fn_: fire_on_enemy_tile,
    },
    Policy::Leaf {
        name: "turret_around_harvester",
        fn_: turret_around_harvester,
    },
    OFFENSE_PARASITIC_GROUP,
    Policy::Leaf {
        name: "scout_toward_enemy",
        fn_: scout_toward_enemy,
    },
];

pub static PARASITIC_ROLE_GROUP_INNER: TaskGroup = TaskGroup {
    name: "parasitic",
    children: PARASITIC_ROLE_CHILDREN,
    gate: None,
};

pub static PARASITIC_ROLE_GROUP: Policy = Policy::Group(&PARASITIC_ROLE_GROUP_INNER);
