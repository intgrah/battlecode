//! Per-turn marker scan for drewfett v1000 WS-1.
//!
//! Walks `state.nearby_tiles` looking for friendly `Marker` buildings,
//! decodes the wire payload, and writes the decoded data into the
//! `Builder.saw_*` fields. Tag 0 (Symmetry) is intentionally skipped here —
//! it's already handled by `Unit::check_symmetry_marker` on the trait, and
//! re-handling it would be redundant.
//!
//! Each scan rebuilds the per-turn view from scratch (the fields are
//! cleared at the top); there's no carry-over from previous turns. That
//! keeps the model simple: "what allied markers can this bot currently
//! see?" Marker freshness is encoded in the payload's `round_lo`, so
//! consumer tasks reason about staleness themselves.
//!
//! This module is **only the consumer side** — the producer side
//! (placing tags 1..=5) lands in WS-4 / WS-9 (rendezvous / defender
//! coordination) and is intentionally out-of-scope for WS-1.

use cambc::{Controller, ControllerApi, EntityType, Position};

use crate::builder::Builder;
use crate::marker::{Marker, decode};
use crate::util::posint::idx_of;

/// Decode `RendezvousAttack` markers in vision into `saw_rendezvous_at`.
/// All other tags (`OreClaim`, `EnemyThreat`, `KillCommit`) were
/// populated by the original WS-1 plan but never consumed, so they're
/// dropped here to skip the per-tile decode + dict-insert overhead. The
/// `Symmetry` tag is handled separately by `Unit::check_symmetry_marker`.
pub fn update_markers(builder: &mut Builder, ct: &mut Controller<'_>) {
    builder.saw_rendezvous_at = None;
    let my_team = builder.state.my_team;
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    for pos in nearby {
        // Use cached arrays to avoid 3 Python-boundary ct calls per tile.
        let i = idx_of(pos) as usize;
        let Some(bid) = builder.building_ids[i] else {
            continue;
        };
        if builder.building_kind[i] != Some(EntityType::Marker) {
            continue;
        }
        if builder.building_team[i] != Some(my_team) {
            continue;
        }
        let value = pyrust::unwrap!(ct.get_marker_value(bid));
        let Some(marker) = decode(value) else {
            continue;
        };
        match marker {
            Marker::RendezvousAttack {
                target_x,
                target_y,
                round_lo,
            } => {
                let target = Position {
                    x: target_x as i32,
                    y: target_y as i32,
                };
                let candidate = (target, round_lo as i32);
                let keep_prev = match builder.saw_rendezvous_at {
                    Some((_, prev)) => prev >= candidate.1,
                    None => false,
                };
                if !keep_prev {
                    builder.saw_rendezvous_at = Some(candidate);
                }
            }
            _ => {}
        }
    }
}
