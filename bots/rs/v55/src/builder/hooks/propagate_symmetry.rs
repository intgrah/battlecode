//! Translation of `bots/intgrah/v54.7.9/builder/hooks/propagate_symmetry.py`.

use cambc::{Controller, ControllerApi, Environment};

use crate::builder::Builder;
use crate::marker::Marker;
use crate::util::constants::MAX_WIDTH;
use crate::util::directions::DIR8;

/// If we've collapsed to a single symmetry, drop a marker on a
/// nearby tile with no existing building so other units that see it
/// converge too. Markers are the lowest-priority building — we'd never
/// destroy anything to place one, so we only place on tiles that are
/// already unbuilt.
pub fn end_of_turn_propagate_symmetry(builder: &mut Builder, ct: &mut Controller<'_>) {
    let Some(symmetry) = builder.symmetry() else {
        return;
    };
    let payload = Marker::Symmetry { symmetry }.encode();
    for &d in &DIR8 {
        let target = builder.state.my_pos.add(d);
        if !builder.in_bounds(target) {
            continue;
        }
        let i = (target.y as usize) * MAX_WIDTH + (target.x as usize);
        if builder.env[i] == Some(Environment::Wall) {
            continue;
        }
        if builder.buildings[i].is_some() {
            continue;
        }
        if ct.can_place_marker(target).unwrap() {
            ct.place_marker(target, payload).unwrap();
            return;
        }
    }
}
