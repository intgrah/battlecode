use std::collections::HashSet;

use cambc::{Controller, ControllerApi};

use crate::builder::Builder;

pub fn prune_stale(builder: &mut Builder, ct: &mut Controller<'_>) {
    builder.nearby_buildings = pyrust::vec::new!();

    builder.healable_buildings = builder
        .healable_buildings
        .iter()
        .copied()
        .filter(|p| !pyrust::unwrap!(ct.is_in_vision(*p)))
        .collect();
    builder.adjacent_to_enemy_launcher = builder
        .adjacent_to_enemy_launcher
        .iter()
        .copied()
        .filter(|p| !pyrust::unwrap!(ct.is_in_vision(*p)))
        .collect::<HashSet<_>>();
    builder.enemy_turret_ray_tiles = builder
        .enemy_turret_ray_tiles
        .iter()
        .copied()
        .filter(|p| !pyrust::unwrap!(ct.is_in_vision(*p)))
        .collect::<HashSet<_>>();
    builder.friendly_turret_ray_tiles = builder
        .friendly_turret_ray_tiles
        .iter()
        .copied()
        .filter(|p| !pyrust::unwrap!(ct.is_in_vision(*p)))
        .collect::<HashSet<_>>();
}
