//! Translation of `bots/intgrah/v54.7.9/builder/hooks/heal.py`.

use cambc::{Controller, ControllerApi, EntityType};
use serde_json::Map;

use crate::builder::Builder;
use crate::util::debug::debug as log;
use crate::util::directions::DIR8;

/// Opportunistic end-of-turn healing. Heal is a separate action from
/// the task action, so we spend it after whatever the task chose. Order:
/// 1. Self, if damaged (healing is targeted at the builder's own tile).
/// 2. Visible friendly non-core unit (bot / turret) on a healable tile,
///    if damaged — heal is applied to the unit's position.
/// 3. Core — 3x3 block, heal is tile-targeted but core shares HP across
///    all 9 tiles, so we pick any DIR8 cardinal of the core centre that's
///    in action range.
pub fn end_of_turn_heal(builder: &mut Builder, ct: &mut Controller<'_>) {
    let my_pos = pyrust::unwrap!(ct.get_position(None));
    if pyrust::unwrap!(ct.can_heal(my_pos)) && pyrust::unwrap!(ct.get_hp(None)) < pyrust::unwrap!(ct.get_max_hp(None)) {
        log(&format!("end_of_turn_heal: self at {my_pos:?}"), Map::new());
        pyrust::unwrap!(ct.heal(my_pos));
    }
    for unit in pyrust::unwrap!(ct.get_nearby_units(None)) {
        if pyrust::unwrap!(ct.get_team(Some(unit))) != builder.state.my_team {
            continue;
        }
        if pyrust::unwrap!(ct.get_hp(Some(unit))) >= pyrust::unwrap!(ct.get_max_hp(Some(unit))) {
            continue;
        }
        if pyrust::unwrap!(ct.get_entity_type(Some(unit))) == EntityType::Core {
            for &d in &DIR8 {
                let heal_pos = pyrust::unwrap!(ct.get_position(Some(unit))).add(d);
                if pyrust::unwrap!(ct.can_heal(heal_pos)) {
                    log(
                        &format!("end_of_turn_heal: core at {heal_pos:?}"),
                        Map::new(),
                    );
                    pyrust::unwrap!(ct.heal(heal_pos));
                    break;
                }
            }
        } else if pyrust::unwrap!(ct.can_heal(pyrust::unwrap!(ct.get_position(Some(unit))))) {
            let unit_pos = pyrust::unwrap!(ct.get_position(Some(unit)));
            log(
                &format!("end_of_turn_heal: friendly unit at {unit_pos:?}"),
                Map::new(),
            );
            pyrust::unwrap!(ct.heal(unit_pos));
        }
    }
}
