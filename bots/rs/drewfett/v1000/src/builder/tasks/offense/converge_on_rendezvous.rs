//! drewfett v1000 WS-4: converge on a `RendezvousAttack` marker.
//!
//! When a friendly bot has previously placed a Tag-3 `RendezvousAttack`
//! marker pointing at a high-value enemy harvester, other Free bots that
//! see the marker walk toward the target so the harassment turns into a
//! coordinated 2-3 bot strike. Once adjacent, the bot fires / places a
//! turret if possible, and refreshes the rendezvous marker so the next
//! arriving bot can chain.
//!
//! Marker placement here is **best-effort** — if `can_place_marker`
//! refuses (1-marker/round budget exhausted, no empty tile, etc.) we
//! drop silently and continue with movement / firing.

use cambc::{Controller, ControllerApi, Environment, Position};

use crate::builder::Builder;
use crate::builder::helpers::{make_move, try_attack};
use crate::marker::{Marker, decode, encode, round_lo};
use crate::util::metrics::chebyshev;
use crate::util::posint::{DIR8_INT, idx_of, pos_of};

use crate::builder::tasks::rejected::{TaskRejected, TaskResult};

/// Maximum chebyshev distance at which a bot still bothers to converge
/// on a rendezvous marker. Beyond this the bot probably has higher-value
/// local work and shouldn't drop everything to march across the map.
const CONVERGE_RANGE: i32 = 12;

pub fn converge_on_rendezvous(self_: &mut Builder, ct: &mut Controller<'_>) -> TaskResult {
    let Some((target, _round_lo)) = self_.saw_rendezvous_at else {
        return Some(TaskRejected::new("no rendezvous marker in vision"));
    };
    if !self_.in_bounds(target) {
        return Some(TaskRejected::new("rendezvous target out of bounds"));
    }
    let d = chebyshev(self_.my_pos, target);
    if d > CONVERGE_RANGE {
        return Some(TaskRejected::new("rendezvous target out of converge range"));
    }
    if d == 0 {
        // We're standing on the target — fire-on / turret tasks already
        // handled this; nothing useful to do here.
        return Some(TaskRejected::new("standing on rendezvous target"));
    }

    if d == 1 {
        // Adjacent: fire if we can, then refresh the marker. Best-effort:
        // if can_fire errors (e.g. target moved out of vision mid-turn),
        // skip the attack but still refresh the marker.
        if pyrust::unwrap_or!(ct.can_fire(target), false) {
            try_attack(ct, target);
        }
        refresh_rendezvous_marker(self_, ct, target);
        return None;
    }

    // Not adjacent: walk toward the target. Best-effort marker refresh
    // along the way so trailing bots see a fresh marker.
    make_move(self_, ct, target);
    refresh_rendezvous_marker(self_, ct, target);
    None
}

/// Drop a fresh `RendezvousAttack(target, round_lo)` marker on the first
/// adjacent empty tile that accepts one. Best-effort: returns silently
/// on any failure (no empty tile, can_place_marker refuses, target dead).
fn refresh_rendezvous_marker(self_: &Builder, ct: &mut Controller<'_>, target: Position) {
    let payload = encode(Marker::RendezvousAttack {
        target_x: target.x as u32,
        target_y: target.y as u32,
        round_lo: round_lo(self_.state.round),
    });
    place_marker_best_effort(self_, ct, payload);
}

/// Try to drop `payload` on the first adjacent empty (no building, not
/// wall) tile that `can_place_marker` accepts. Silently no-ops on
/// failure — caller does not retry.
pub fn place_marker_best_effort(self_: &Builder, ct: &mut Controller<'_>, payload: u32) {
    let my_p = idx_of(self_.state.my_pos);
    for &dp in &DIR8_INT {
        let cp = my_p + dp;
        if cp < 0 || (cp as usize) >= self_.posint_valid.len() || self_.posint_valid[cp as usize] == 0 {
            continue;
        }
        let i = cp as usize;
        if self_.env[i] == Some(Environment::Wall) {
            continue;
        }
        if pyrust::is_some!(self_.building_kind[i]) {
            continue;
        }
        let cand = pos_of(cp);
        if !pyrust::unwrap_or!(ct.can_place_marker(cand), false) {
            continue;
        }
        // best-effort: ignore any error from place_marker
        let _ = ct.place_marker(cand, payload);
        return;
    }
}
