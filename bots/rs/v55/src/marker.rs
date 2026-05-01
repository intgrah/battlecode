//! Translation of `bots/intgrah/v54.7.9/marker/__init__.py`.
//!
//! Python defines an `ABC` `Marker` with auto-registered subclasses (one tag
//! per class, assigned at class-definition time). Since the only concrete
//! variant in v54.7.9 is `MarkerSymmetry`, the Rust translation is a single
//! enum: adding a new variant means adding a new arm here, in declaration
//! order (matching Python's `_registry` ordering — `MarkerSymmetry` is tag 0).

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

/// Tag for `MarkerSymmetry` (matches Python `_registry` order: 0 = first
/// subclass to be declared).
const TAG_SYMMETRY: u32 = 0;

/// A marker payload exchanged between friendly units via on-tile markers.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Marker {
    /// Sender has resolved (or is asserting) the map's symmetry.
    Symmetry { symmetry: Symmetry },
}

impl Marker {
    /// Encode to the wire `u32` (tag-prefixed, then XOR-scrambled with `KEY`).
    #[must_use]
    pub const fn encode(self) -> u32 {
        let (tag, payload) = match self {
            Marker::Symmetry { symmetry } => (TAG_SYMMETRY, symmetry as u32),
        };
        let raw = (tag << TAG_SHIFT) | (payload & PAYLOAD_MASK);
        raw ^ KEY
    }

    /// Decode a wire `u32` back to a `Marker`. Returns `None` if the tag is
    /// unknown (e.g. emitted by an enemy or an older bot version).
    #[must_use]
    pub const fn decode(encrypted: u32) -> Option<Self> {
        let raw = encrypted ^ KEY;
        let tag = (raw >> TAG_SHIFT) & TAG_MASK;
        let payload = raw & PAYLOAD_MASK;
        // `if/else` rather than `match`: Python `case CONST:` parses as a
        // binding pattern, not a value comparison, so an idiomatic Rust
        // match-on-constants doesn't translate cleanly.
        if tag == TAG_SYMMETRY {
            let sym = match payload & 0x3 {
                0 => Symmetry::Rot,
                1 => Symmetry::Hor,
                2 => Symmetry::Ver,
                _ => return None,
            };
            Some(Marker::Symmetry { symmetry: sym })
        } else {
            None
        }
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
        if let Some(Marker::Symmetry { symmetry }) = Marker::decode(value) {
            return Some(symmetry);
        }
    }
    None
}
