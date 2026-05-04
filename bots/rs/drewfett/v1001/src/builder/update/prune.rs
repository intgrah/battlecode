use cambc::Controller;

use crate::builder::Builder;
use crate::util::posint::idx_of;

pub fn prune_stale(builder: &mut Builder, ct: &mut Controller<'_>) {
    builder.nearby_buildings = pyrust::vec::new!();
    builder.visible_ti_ore = pyrust::vec::new!();
    builder.visible_ax_ore = pyrust::vec::new!();
    builder.visible_harvesters = pyrust::vec::new!();

    let mask = pyrust::clone!(builder.vision_mask);
    builder.healable_buildings = pyrust::collect!(pyrust::filter!(
        pyrust::copied!(pyrust::iter!(builder.healable_buildings)),
        |p| mask[idx_of(*p) as usize] == 0
    ));
    let prev_launcher = pyrust::set::clone!(builder.adjacent_to_enemy_launcher);
    pyrust::set::clear!(builder.adjacent_to_enemy_launcher);
    for &p in pyrust::iter!(&prev_launcher) {
        if mask[p as usize] == 0 {
            pyrust::set::add!(builder.adjacent_to_enemy_launcher, p);
        }
    }
    let prev_enemy = pyrust::set::clone!(builder.enemy_turret_ray_tiles);
    pyrust::set::clear!(builder.enemy_turret_ray_tiles);
    for &p in pyrust::iter!(&prev_enemy) {
        if mask[p as usize] == 0 {
            pyrust::set::add!(builder.enemy_turret_ray_tiles, p);
        }
    }
    let prev_friendly = pyrust::set::clone!(builder.friendly_turret_ray_tiles);
    pyrust::set::clear!(builder.friendly_turret_ray_tiles);
    for &p in pyrust::iter!(&prev_friendly) {
        if mask[p as usize] == 0 {
            pyrust::set::add!(builder.friendly_turret_ray_tiles, p);
        }
    }
}
