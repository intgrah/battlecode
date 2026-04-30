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
    let my_pos = ct.get_position(None).unwrap();
    if ct.can_heal(my_pos).unwrap() && ct.get_hp(None).unwrap() < ct.get_max_hp(None).unwrap() {
        log(&format!("end_of_turn_heal: self at {my_pos:?}"), Map::new());
        ct.heal(my_pos).unwrap();
    }
    for unit in ct.get_nearby_units(None).unwrap() {
        if ct.get_team(Some(unit)).unwrap() != builder.state.my_team {
            continue;
        }
        if ct.get_hp(Some(unit)).unwrap() >= ct.get_max_hp(Some(unit)).unwrap() {
            continue;
        }
        if ct.get_entity_type(Some(unit)).unwrap() == EntityType::Core {
            for &d in &DIR8 {
                let heal_pos = ct.get_position(Some(unit)).unwrap().add(d);
                if ct.can_heal(heal_pos).unwrap() {
                    log(
                        &format!("end_of_turn_heal: core at {heal_pos:?}"),
                        Map::new(),
                    );
                    ct.heal(heal_pos).unwrap();
                    break;
                }
            }
        } else if ct.can_heal(ct.get_position(Some(unit)).unwrap()).unwrap() {
            let unit_pos = ct.get_position(Some(unit)).unwrap();
            log(
                &format!("end_of_turn_heal: friendly unit at {unit_pos:?}"),
                Map::new(),
            );
            ct.heal(unit_pos).unwrap();
        }
    }
}
