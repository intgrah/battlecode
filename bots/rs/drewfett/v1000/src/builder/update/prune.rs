use cambc::{Controller, ControllerApi};

use crate::builder::Builder;
use crate::util::posint::pos_of;

pub fn prune_stale(builder: &mut Builder, ct: &mut Controller<'_>) {
    builder.nearby_buildings = pyrust::vec::new!();
    builder.visible_ti_ore = pyrust::vec::new!();
    builder.visible_ax_ore = pyrust::vec::new!();
    builder.visible_harvesters = pyrust::vec::new!();

    builder.healable_buildings = pyrust::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(builder.healable_buildings)),
        |p| !pyrust::unwrap!(ct.is_in_vision(*p))
    ));
    let prev_launcher = pyrust::set::clone!(builder.adjacent_to_enemy_launcher);
    pyrust::set::clear!(builder.adjacent_to_enemy_launcher);
    for &p in pyrust::iter!(&prev_launcher) {
        if !pyrust::unwrap!(ct.is_in_vision(pos_of(p))) {
            pyrust::set::add!(builder.adjacent_to_enemy_launcher, p);
        }
    }
    let prev_enemy = pyrust::set::clone!(builder.enemy_turret_ray_tiles);
    pyrust::set::clear!(builder.enemy_turret_ray_tiles);
    for &p in pyrust::iter!(&prev_enemy) {
        if !pyrust::unwrap!(ct.is_in_vision(pos_of(p))) {
            pyrust::set::add!(builder.enemy_turret_ray_tiles, p);
        }
    }
    let prev_friendly = pyrust::set::clone!(builder.friendly_turret_ray_tiles);
    pyrust::set::clear!(builder.friendly_turret_ray_tiles);
    for &p in pyrust::iter!(&prev_friendly) {
        if !pyrust::unwrap!(ct.is_in_vision(pos_of(p))) {
            pyrust::set::add!(builder.friendly_turret_ray_tiles, p);
        }
    }
}
