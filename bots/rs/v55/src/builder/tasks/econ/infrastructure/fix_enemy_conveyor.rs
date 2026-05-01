//! Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/fix_enemy_conveyor.py`.
//!
//! Destroy any nearby tile that `leads_to_enemy_building` (i.e. a
//! friendly conveyor whose downstream chain ultimately reaches an enemy
//! building, leaking our resources to them) and pave a road in its place.
//! First tile in vision that qualifies wins.

use cambc::{Controller, ControllerApi};

use crate::builder::Builder;
use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

pub fn fix_enemy_conveyor(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let nearby = self_.nearby_tiles.clone();
    for pos in nearby {
        if self_.leads_to_enemy_building(pos) && ct.can_destroy(pos).unwrap() {
            ct.destroy(pos).unwrap();
            self_.apply_local_destroy(pos);
            if ct.can_build_road(pos).unwrap() {
                ct.build_road(pos).unwrap();
                return None;
            }
        }
    }
    Some(TaskRejected::new(
        "no enemy-feeding conveyor in action range",
    ))
}
