//! Translation of `bots/intgrah/v54.7.9/marker/__init__.py`, extended for
//! drewfett v1000 WS-1.
//!
//! The Python source defines an `ABC` `Marker` with auto-registered
//! subclasses (one tag per class, assigned at class-definition time). v54.7.9
//! ships exactly one variant — `MarkerSymmetry` (tag 0). drewfett v1000
//! extends the protocol to a **6-tag semantic marker scheme** for team-wide
//! coordination (replay analysis of #1-ladder bots showed they use 5–11
//! distinct tags placing 1500+ markers/game).
//!
//! ## Wire format
//!
//! Every marker is a `u32` consisting of:
//! * 4 high bits — tag (0..=15)
//! * 28 low bits — payload (tag-specific encoding)
//!
//! The whole `u32` is XOR'd with `KEY = 0xDEADBEEF` so the wire format is
//! scrambled (enemy bots see allied markers but can't trivially read them).
//!
//! ## Tags
//!
//! | Tag | Variant            | Payload (28 bits)                          |
//! |-----|--------------------|--------------------------------------------|
//! | 0   | `Symmetry`         | sym (2)                                    |
//! | 1   | `OreClaim`         | bot_id (10) + round_lo (8)                 |
//! | 2   | `EnemyThreat`      | turret_count (6) + bots_seen (6) + round_lo (8) |
//! | 3   | `RendezvousAttack` | target_x (6) + target_y (6) + round_lo (8) |
//! | 4   | `DefenderHere`     | bot_id (10) + last_seen_round_lo (8)       |
//! | 5   | `KillCommit`       | enemy_core_x (6) + enemy_core_y (6) + commit_round_lo (8) |
//!
//! `round_lo` = `round & 0xFF`. Consumers reconstruct freshness via
//! `(current_round - round_lo).rem_euclid(256)`; a marker placed > 256
//! rounds ago is indistinguishable from one placed at the same `round_lo`
//! today, but in practice every workstream that reads a marker treats
//! freshness as "≤ N rounds for small N (10–30)" so the wraparound is fine.
//!
//! ## Adding new tags
//!
//! Append a variant + match arms in `encode`/`decode`. Tag values must
//! stay stable (older bots in long-running ladder games may still emit the
//! old encoding, and `decode` returns `None` for unknown tags so it's safe
//! to ignore).

use cambc::{Controller, ControllerApi, EntityType, Position, Team};

use crate::util::symmetry::Symmetry;

/// XOR key applied to the encoded `u32` to scramble the wire format.
pub const KEY: u32 = 0xDEAD_BEEF;
/// Bit position of the tag inside the unscrambled 32-bit value.
pub const TAG_SHIFT: u32 = 28;
/// Mask for the 4-bit tag field.
pub const TAG_MASK: u32 = 0xF;
/// Mask for the 28-bit payload field.
pub const PAYLOAD_MASK: u32 = (1 << TAG_SHIFT) - 1;

// Tag constants (stable wire identifiers — never reorder; only append).
pub const TAG_SYMMETRY: u32 = 0;
pub const TAG_ORE_CLAIM: u32 = 1;
pub const TAG_ENEMY_THREAT: u32 = 2;
pub const TAG_RENDEZVOUS_ATTACK: u32 = 3;
pub const TAG_DEFENDER_HERE: u32 = 4;
pub const TAG_KILL_COMMIT: u32 = 5;

// Field-width masks for sub-payload fields.
const MASK_2: u32 = 0x3;
const MASK_6: u32 = 0x3F;
const MASK_8: u32 = 0xFF;
const MASK_10: u32 = 0x3FF;

/// Reduce a round number to its 8-bit wire form.
#[inline]
#[must_use]
pub const fn round_lo(round: i32) -> u32 {
    (round as u32) & MASK_8
}

/// A marker payload exchanged between friendly units via on-tile markers.
///
/// All position fields are absolute map coordinates packed as 6-bit unsigned
/// integers (max map dimension = 50, fits in 6 bits). All `round_lo` fields
/// store `round & 0xFF` only — see module docs for freshness arithmetic.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Marker {
    /// Sender has resolved (or is asserting) the map's symmetry. Tag 0.
    Symmetry { symmetry: Symmetry },
    /// Sender (a builder) has claimed a nearby ore tile and is harvesting /
    /// going to harvest. Other Free bots considering this ore should skip
    /// it. Tag 1.
    OreClaim { bot_id: u32, round_lo: u32 },
    /// Sender has an enemy in vision; payload summarizes the local threat
    /// (turret count + visible bots). Read by Free bots (cost-grid bias)
    /// and Defenders (decide stay vs converge). Tag 2.
    EnemyThreat {
        turret_count: u32,
        bots_seen: u32,
        round_lo: u32,
    },
    /// Sender has identified a high-value enemy harvester / chain segment
    /// at `(target_x, target_y)`. Other Free bots within ~12 tiles should
    /// converge. Tag 3.
    RendezvousAttack {
        target_x: u32,
        target_y: u32,
        round_lo: u32,
    },
    /// Sender (a Defender) is patrolling near `my_core`. Other Defenders
    /// should pick a different patrol target; Core can use marker count as
    /// a defender-supply proxy for spawn pacing. Tag 4.
    DefenderHere { bot_id: u32, round_lo: u32 },
    /// Sender has detected enemy core HP < threshold. All Free bots within
    /// ~30 tiles enter override "kill commit" mode. Tag 5.
    KillCommit {
        enemy_core_x: u32,
        enemy_core_y: u32,
        round_lo: u32,
    },
}

/// Encode a `Marker` to the wire `u32` (tag-prefixed, then XOR-scrambled with `KEY`).
///
/// Free function rather than `impl Marker` method because pyrust translates
/// sum-type enums to a `TypeAliasType` union of dataclass variants — methods
/// can't attach to the union, so callers can't dispatch via `Marker::encode`.
#[must_use]
pub const fn encode(m: Marker) -> u32 {
    let (tag, payload) = match m {
            Marker::Symmetry { symmetry } => (TAG_SYMMETRY, (symmetry as u32) & MASK_2),
            Marker::OreClaim { bot_id, round_lo } => {
                let p = ((bot_id & MASK_10) << 8) | (round_lo & MASK_8);
                (TAG_ORE_CLAIM, p)
            }
            Marker::EnemyThreat {
                turret_count,
                bots_seen,
                round_lo,
            } => {
                let p = ((turret_count & MASK_6) << 14)
                    | ((bots_seen & MASK_6) << 8)
                    | (round_lo & MASK_8);
                (TAG_ENEMY_THREAT, p)
            }
            Marker::RendezvousAttack {
                target_x,
                target_y,
                round_lo,
            } => {
                let p = ((target_x & MASK_6) << 14)
                    | ((target_y & MASK_6) << 8)
                    | (round_lo & MASK_8);
                (TAG_RENDEZVOUS_ATTACK, p)
            }
            Marker::DefenderHere { bot_id, round_lo } => {
                let p = ((bot_id & MASK_10) << 8) | (round_lo & MASK_8);
                (TAG_DEFENDER_HERE, p)
            }
            Marker::KillCommit {
                enemy_core_x,
                enemy_core_y,
                round_lo,
            } => {
                let p = ((enemy_core_x & MASK_6) << 14)
                    | ((enemy_core_y & MASK_6) << 8)
                    | (round_lo & MASK_8);
                (TAG_KILL_COMMIT, p)
            }
        };
    let raw = (tag << TAG_SHIFT) | (payload & PAYLOAD_MASK);
    raw ^ KEY
}

/// Decode a wire `u32` back to a `Marker`. Returns `None` if the tag is
/// unknown (e.g. emitted by an enemy or an older bot version).
#[must_use]
pub const fn decode(encrypted: u32) -> Option<Marker> {
        let raw = encrypted ^ KEY;
        let tag = (raw >> TAG_SHIFT) & TAG_MASK;
        let payload = raw & PAYLOAD_MASK;
        // `if/else` rather than `match`: Python `case CONST:` parses as a
        // binding pattern, not a value comparison, so an idiomatic Rust
        // match-on-constants doesn't translate cleanly.
        if tag == TAG_SYMMETRY {
            let sym = match payload & MASK_2 {
                0 => Symmetry::Rot,
                1 => Symmetry::Hor,
                2 => Symmetry::Ver,
                _ => return None,
            };
            Some(Marker::Symmetry { symmetry: sym })
        } else if tag == TAG_ORE_CLAIM {
            Some(Marker::OreClaim {
                bot_id: (payload >> 8) & MASK_10,
                round_lo: payload & MASK_8,
            })
        } else if tag == TAG_ENEMY_THREAT {
            Some(Marker::EnemyThreat {
                turret_count: (payload >> 14) & MASK_6,
                bots_seen: (payload >> 8) & MASK_6,
                round_lo: payload & MASK_8,
            })
        } else if tag == TAG_RENDEZVOUS_ATTACK {
            Some(Marker::RendezvousAttack {
                target_x: (payload >> 14) & MASK_6,
                target_y: (payload >> 8) & MASK_6,
                round_lo: payload & MASK_8,
            })
        } else if tag == TAG_DEFENDER_HERE {
            Some(Marker::DefenderHere {
                bot_id: (payload >> 8) & MASK_10,
                round_lo: payload & MASK_8,
            })
        } else if tag == TAG_KILL_COMMIT {
            Some(Marker::KillCommit {
                enemy_core_x: (payload >> 14) & MASK_6,
                enemy_core_y: (payload >> 8) & MASK_6,
                round_lo: payload & MASK_8,
            })
    } else {
        None
    }
}

/// Scan `nearby_tiles` for an allied `MarkerSymmetry` and return its symmetry.
/// Returns the first one found, or `None` if no friendly symmetry marker is
/// in vision.
#[must_use] 
pub fn find_symmetry_marker(
    ct: &Controller<'_>,
    nearby_tiles: &[Position],
    my_team: Team,
) -> Option<Symmetry> {
    for &pos in nearby_tiles {
        let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(pos)) else {
            continue;
        };
        if pyrust::unwrap!(ct.get_entity_type(Some(bid))) != EntityType::Marker {
            continue;
        }
        if pyrust::unwrap!(ct.get_team(Some(bid))) != my_team {
            continue;
        }
        let value = pyrust::unwrap!(ct.get_marker_value(bid));
        if let Some(Marker::Symmetry { symmetry }) = decode(value) {
            return Some(symmetry);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn roundtrip(m: Marker) -> Marker {
        pyrust::expect!(decode(encode(m)), "decode")
    }

    #[test]
    fn symmetry_roundtrip() {
        for sym in Symmetry::ALL {
            assert_eq!(
                roundtrip(Marker::Symmetry { symmetry: sym }),
                Marker::Symmetry { symmetry: sym }
            );
        }
    }

    #[test]
    fn ore_claim_roundtrip() {
        let m = Marker::OreClaim {
            bot_id: 0x3FF,
            round_lo: 0xAB,
        };
        assert_eq!(roundtrip(m), m);
    }

    #[test]
    fn enemy_threat_roundtrip() {
        let m = Marker::EnemyThreat {
            turret_count: 0x3F,
            bots_seen: 0x2A,
            round_lo: 0x55,
        };
        assert_eq!(roundtrip(m), m);
    }

    #[test]
    fn rendezvous_roundtrip() {
        let m = Marker::RendezvousAttack {
            target_x: 49,
            target_y: 23,
            round_lo: 0xFE,
        };
        assert_eq!(roundtrip(m), m);
    }

    #[test]
    fn defender_here_roundtrip() {
        let m = Marker::DefenderHere {
            bot_id: 0x123,
            round_lo: 0x04,
        };
        assert_eq!(roundtrip(m), m);
    }

    #[test]
    fn kill_commit_roundtrip() {
        let m = Marker::KillCommit {
            enemy_core_x: 12,
            enemy_core_y: 34,
            round_lo: 0xC0,
        };
        assert_eq!(roundtrip(m), m);
    }

    #[test]
    fn round_lo_truncates() {
        assert_eq!(round_lo(0), 0);
        assert_eq!(round_lo(255), 255);
        assert_eq!(round_lo(256), 0);
        assert_eq!(round_lo(257), 1);
    }

    #[test]
    fn unknown_tag_returns_none() {
        // Tag 15 isn't allocated.
        let raw = (15u32 << TAG_SHIFT) | 0xABCD;
        assert!(decode(raw ^ KEY).is_none());
    }
}
