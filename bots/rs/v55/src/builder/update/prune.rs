use std::collections::HashSet;

use cambc::{Controller, ControllerApi};

use crate::builder::Builder;

pub fn prune_stale(builder: &mut Builder, ct: &mut Controller<'_>) {
    builder.nearby_buildings = pyrust::vec::new!();

    builder.healable_buildings = pyrust::collect!(pyrust::filter!(pyrust::copied!(pyrust::iter!(builder
        .healable_buildings)), |p| !pyrust::unwrap!(ct.is_in_vision(*p))));
    builder.adjacent_to_enemy_launcher = pyrust::collect!(pyrust::filter!(pyrust::copied!(pyrust::iter!(builder
        .adjacent_to_enemy_launcher)), |p| !pyrust::unwrap!(ct.is_in_vision(*p))));
    builder.enemy_turret_ray_tiles = pyrust::collect!(pyrust::filter!(pyrust::copied!(pyrust::iter!(builder
        .enemy_turret_ray_tiles)), |p| !pyrust::unwrap!(ct.is_in_vision(*p))));
    builder.friendly_turret_ray_tiles = pyrust::collect!(pyrust::filter!(pyrust::copied!(pyrust::iter!(builder
        .friendly_turret_ray_tiles)), |p| !pyrust::unwrap!(ct.is_in_vision(*p))));
}
