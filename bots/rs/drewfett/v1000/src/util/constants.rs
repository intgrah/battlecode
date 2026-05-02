//! Translation of `bots/intgrah/v54.7.9/util/constants.py`.

use cambc::{EntityType, GameConstants};

/// Length of per-tile `flow_history` deques. Each entry is one observation
/// of the tile's stored resource (or `None`). Flow/volume metrics divide
/// counts by this constant to normalise to `[0, 1]`.
pub const FLOW_HISTORY_LEN: usize = 8;

/// Large number used to represent unreachable distances or hard preferences.
pub const INF: i32 = 1_000_000;

/// The cost of having to place a road on an empty tile, used for A* navigation.
pub const ROAD_COST: i32 = 3;

/// Maximum map dimension in tiles (per game rules: 20×20 to 50×50).
pub const MAX_WIDTH: usize = 50;

/// Stride for `PosInt` flat indexing: `idx = y * STRIDE + x`. Equals
/// `2 * MAX_WIDTH` so that `p - q` uniquely determines `(dy, dx)` —
/// see `util::posint`.
pub const STRIDE: usize = 100;

/// Length of all flat per-tile arrays. `STRIDE * MAX_WIDTH` (5000); half
/// the slots are unused holes (x ∈ [50, 100)).
pub const BOUND_RANGE: usize = STRIDE * MAX_WIDTH;

/// `BOUND_RANGE + STRIDE = 5100`. Defined as a const so the
/// `posint_valid` allocation site doesn't need a binary expression
/// inside `vec![0u8; ...]` — pyrust translates that to
/// `[0] * BOUND_RANGE + STRIDE` (without parens), which raises
/// `TypeError: can only concatenate list (not "int") to list`.
pub const POSINT_VALID_LEN: usize = BOUND_RANGE + STRIDE;

/// `MAX_WIDTH * MAX_WIDTH = 2500`. Number of *valid* tiles on a worst-case
/// 50×50 map. Used for sizing data structures that semantically count
/// tiles (e.g. iteration counts, capacity hints) as opposed to per-tile
/// flat arrays which use `BOUND_RANGE`.
pub const MAX_N: usize = MAX_WIDTH * MAX_WIDTH;

/// Base `(titanium, refined_axionite)` cost for each entity type, before
/// scaling. Mirrors Python `BASE_COST: dict[EntityType, tuple[int, int]]`.
///
/// Implemented as a function rather than a `HashMap` so it's `const`-friendly
/// and allocation-free. Returns `None` for entity types that aren't placeable
/// buildings (CORE, MARKER, BUILDER_BOT-on-spawn handled separately).
#[must_use]
pub const fn base_cost(et: EntityType) -> Option<(i32, i32)> {
    match et {
        EntityType::BuilderBot => Some(GameConstants::BUILDER_BOT_BASE_COST),
        EntityType::Harvester => Some(GameConstants::HARVESTER_BASE_COST),
        EntityType::Sentinel => Some(GameConstants::SENTINEL_BASE_COST),
        EntityType::Gunner => Some(GameConstants::GUNNER_BASE_COST),
        EntityType::Launcher => Some(GameConstants::LAUNCHER_BASE_COST),
        EntityType::Conveyor => Some(GameConstants::CONVEYOR_BASE_COST),
        EntityType::Bridge => Some(GameConstants::BRIDGE_BASE_COST),
        EntityType::Splitter => Some(GameConstants::SPLITTER_BASE_COST),
        EntityType::Barrier => Some(GameConstants::BARRIER_BASE_COST),
        EntityType::Road => Some(GameConstants::ROAD_BASE_COST),
        EntityType::Foundry => Some(GameConstants::FOUNDRY_BASE_COST),
        EntityType::Breach => Some(GameConstants::BREACH_BASE_COST),
        _ => None,
    }
}
