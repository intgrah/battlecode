//! Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/_helpers.py`.
//!
//! Shared helpers for the heal leaves: enemy-attacker counting,
//! multi-builder deconfliction, healer-count math, wounded-enemy detection,
//! and the "I'm low-HP on an enemy tile, fight to death instead of heal"
//! bail-out gate that all three leaves consult.

use cambc::{Controller, ControllerApi, EntityType, Position};

use crate::builder::Builder;
use crate::util::metrics::chebyshev;

/// Count enemy builder bots currently in attack range of `target`
/// (builder bots fire at their own tile, so anyone within 1 king-step
/// of target is potentially dealing 2 dmg/turn to it).
#[must_use] 
pub fn count_visible_attackers(self_: &Builder, target: Position) -> i32 {
    let mut n = 0;
    for &p in &self_.enemy_bots {
        if p.distance_squared(target) <= 2 {
            n += 1;
        }
    }
    n
}

/// Count visible friendly builder bots with STRICT priority to heal
/// `target` over us — strictly closer by chebyshev, or tied with a
/// smaller id. Every bot running this with the same visible self gets
/// the same answer, so the top-N closest consistently commit and the
/// rest defer.
pub fn deconflict_rank(
    self_: &Builder,
    ct: &mut Controller<'_>,
    my_pos: Position,
    target: Position,
) -> i32 {
    let my_d = chebyshev(my_pos, target);
    let mut rank = 0;
    for uid in pyrust::unwrap!(ct.get_nearby_units(None)) {
        if uid == self_.my_id {
            continue;
        }
        if pyrust::unwrap!(ct.get_entity_type(Some(uid))) != EntityType::BuilderBot {
            continue;
        }
        if pyrust::unwrap!(ct.get_team(Some(uid))) != self_.my_team {
            continue;
        }
        let fp = pyrust::unwrap!(ct.get_position(Some(uid)));
        let fd = chebyshev(fp, target);
        if fd < my_d || (fd == my_d && uid < self_.my_id) {
            rank += 1;
        }
    }
    rank
}

/// Healers required to outpace `attackers` hitting a single tile.
///
/// Attackers deal 2 dmg/turn each, healers restore 4 hp/turn each, so
/// break-even is ceil(attackers/2). Always at least 1 — one bot still
/// comes for chip damage even with no visible attacker.
#[must_use]
pub const fn healers_needed(attackers: i32) -> i32 {
    if attackers <= 1 {
        return 1;
    }
    (attackers + 1) / 2
}

/// True iff `position` hosts a damaged enemy building. Used to
/// detect tiles where a friendly builder is mid-kill and shouldn't be
/// pulled away by a heal.
#[must_use] 
pub fn has_wounded_enemy(self_: &Builder, position: Position) -> bool {
    let Some((_kind, team)) = self_.get_building(position) else {
        return false;
    };
    let i = self_.idx(position);
    team != self_.my_team && self_.hp[i] < self_.max_hp[i]
}

/// True iff we're standing on an enemy building at low HP and
/// should spend our remaining actions firing rather than healing.
/// Mirrors the gate at the top of `_heal_builders` in the legacy file:
/// bail out of any heal when we're at HP<=2 (on enemy tile), or HP<=6
/// while still mostly intact (>18 HP max means we're probably a fresh
/// bot still committing to the kill).
pub fn fight_to_death(self_: &Builder, ct: &mut Controller<'_>) -> bool {
    let Some((_kind, team)) = self_.get_building(self_.my_pos) else {
        return false;
    };
    if team == self_.my_team {
        return false;
    }
    let i = self_.idx(self_.my_pos);
    if self_.hp[i] <= 2 {
        return true;
    }
    self_.hp[i] <= 6 && pyrust::unwrap!(ct.get_hp(None)) > 18
}
