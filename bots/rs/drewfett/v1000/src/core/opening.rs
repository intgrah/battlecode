//! WS-3 (drewfett v1000) — adaptive opening template.
//!
//! Classifies the map into one of four opening templates based on features
//! visible at `post_init` time. Both `Core` and `Builder` call this identical
//! function so the result is deterministic across all friendly units without
//! requiring inter-unit comms.
//!
//! Inputs are restricted to:
//!   * map width / height (always known),
//!   * own core position,
//!   * enemy core guess (Chebyshev distance only — symmetry mirror works even
//!     before symmetry collapses, since both axis/rotation symmetries produce
//!     the same Chebyshev to centre),
//!   * tile environments in a 5x5 square centred on own core.
//!
//! The 5x5 inner area is chosen so that *every* spawn position on the 3x3
//! core block can read every cell within builder vision (max d² between any
//! spawn tile and any 5x5 cell is 18, comfortably ≤ 20).

use cambc::{Controller, ControllerApi, Environment, Position};

/// Opening templates. `DefaultBalanced` keeps v55 baseline behaviour.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OpeningTemplate {
    /// Large, open, ore-rich maps: faster cadence, fewer defenders.
    OpenEcon,
    /// Long/narrow maps (eccentric w/h): push-aggressive.
    Corridor,
    /// Walled-in core: bunker up with extra defenders.
    ChokeBunker,
    /// Fallback: existing v55 behaviour, no modulation.
    DefaultBalanced,
}

impl OpeningTemplate {
    /// `(round - 1) % defender_period == defender_period - 1` is a Defender.
    /// Period 4 with offset 3 reproduces v55 baseline (every 4th, first 3 Free).
    #[must_use]
    pub const fn defender_period(self) -> i32 {
        match self {
            Self::OpenEcon => 5,         // 20% defenders
            Self::Corridor => 4,         // 25% (current default)
            Self::ChokeBunker => 3,      // ~33% defenders
            Self::DefaultBalanced => 4,  // 25% (current default)
        }
    }

    /// Multiplier on `Core::INITIAL_SPAWNS` (4). 1.0 = unchanged.
    #[must_use]
    pub const fn initial_spawn_factor(self) -> f64 {
        match self {
            Self::OpenEcon => 1.0,
            Self::Corridor => 1.0,
            Self::ChokeBunker => 0.75, // slower opening
            Self::DefaultBalanced => 1.0,
        }
    }

    /// Multiplicative bias on the income/surplus thresholds. >1.0 means the
    /// core spawns *less* eagerly (higher bar to clear). <1.0 spawns more.
    #[must_use]
    pub const fn spawn_eagerness(self) -> f64 {
        match self {
            Self::OpenEcon => 0.85,
            Self::Corridor => 1.0,
            Self::ChokeBunker => 1.15,
            Self::DefaultBalanced => 1.0,
        }
    }

    /// Human-readable tag for debug logging.
    #[must_use]
    pub const fn name(self) -> &'static str {
        match self {
            Self::OpenEcon => "OPEN_ECON",
            Self::Corridor => "CORRIDOR",
            Self::ChokeBunker => "CHOKE_BUNKER",
            Self::DefaultBalanced => "DEFAULT_BALANCED",
        }
    }
}

/// Classify the map. `my_core` is the own-team core centre (3x3). Both Core
/// and Builder call this with their own `my_core` so each side gets a
/// template tuned to its own opening, and every friendly unit on the same
/// team derives the same template (deterministic, no comms).
#[must_use]
pub fn classify(
    width: i32,
    height: i32,
    my_core: Position,
    en_core_guess: Position,
    ct: &mut Controller<'_>,
) -> OpeningTemplate {
    let area = width * height;

    // Eccentricity: ratio of max(w,h)/min(w,h). 1.0 = square, >2.0 = corridor.
    let mn = pyrust::max!(pyrust::min!(width, height), 1);
    let mx = pyrust::max!(width, height);
    let eccentricity = pyrust::float!(mx) / pyrust::float!(mn);

    // Inner 5x5 wall density around our core. (Restricted radius so every
    // builder spawn position can read every cell — see module docs.)
    let mut inner_walls: i32 = 0;
    let mut inner_total: i32 = 0;
    let mut inner_ore: i32 = 0;
    for dy in -2..=2i32 {
        for dx in -2..=2i32 {
            let x = my_core.x + dx;
            let y = my_core.y + dy;
            if x < 0 || x >= width || y < 0 || y >= height {
                continue;
            }
            let env = pyrust::unwrap!(ct.get_tile_env(Position { x, y }));
            inner_total += 1;
            if env == Environment::Wall {
                inner_walls += 1;
            }
            if matches!(env, Environment::OreTitanium | Environment::OreAxionite) {
                inner_ore += 1;
            }
        }
    }
    let inner_wall_density = pyrust::float!(inner_walls) / pyrust::float!(pyrust::max!(inner_total, 1));
    let inner_ore_density = pyrust::float!(inner_ore) / pyrust::float!(pyrust::max!(inner_total, 1));

    // Chebyshev distance to enemy core guess.
    let dx = pyrust::abs!((en_core_guess.x - my_core.x));
    let dy = pyrust::abs!((en_core_guess.y - my_core.y));
    let enemy_chebyshev = pyrust::max!(dx, dy);

    // Decision tree (priority order: choke > corridor > open > default).
    if inner_wall_density >= 0.30 {
        return OpeningTemplate::ChokeBunker;
    }
    if eccentricity >= 2.0 {
        return OpeningTemplate::Corridor;
    }
    if area >= 30 * 30 && inner_wall_density <= 0.10 && inner_ore_density >= 0.08
        && enemy_chebyshev >= 20
    {
        return OpeningTemplate::OpenEcon;
    }
    OpeningTemplate::DefaultBalanced
}
