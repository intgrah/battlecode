//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/`.
//!
//! Infrastructure subtree: foundry / turret placement, repair-style
//! fixes, congestion relief, dead-bridge teardown, harvester-neighbour
//! paving. High-priority structural maintenance work for ECON / DEFENSE.

pub mod build_foundry;
pub mod destroy_dead_bridge;
pub mod fix_enemy_conveyor;
pub mod guard_harvester_neighbours;
pub mod place_gunner;
pub mod resolve_congestion;

use crate::builder::tasks::_policy::{Policy, TaskGroup};

const ECON_INFRASTRUCTURE_CHILDREN: &[Policy] = &[
    Policy::Leaf {
        name: "build_foundry",
        fn_: build_foundry::build_foundry,
    },
    Policy::Leaf {
        name: "place_gunner",
        fn_: place_gunner::place_gunner,
    },
    Policy::Leaf {
        name: "fix_enemy_conveyor",
        fn_: fix_enemy_conveyor::fix_enemy_conveyor,
    },
    Policy::Leaf {
        name: "guard_harvester_neighbours",
        fn_: guard_harvester_neighbours::guard_harvester_neighbours,
    },
    Policy::Leaf {
        name: "resolve_congestion",
        fn_: resolve_congestion::resolve_congestion,
    },
];

pub static ECON_INFRASTRUCTURE_GROUP_INNER: TaskGroup = TaskGroup {
    name: "infrastructure",
    children: ECON_INFRASTRUCTURE_CHILDREN,
    gate: None,
};

pub static ECON_INFRASTRUCTURE_GROUP: Policy = Policy::Group(&ECON_INFRASTRUCTURE_GROUP_INNER);
