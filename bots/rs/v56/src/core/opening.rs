//! Adaptive opening template (ported from drewfett v1000 WS-3).
//!
//! Classifies the map into one of four templates at `post_init`, based
//! on map shape and the inner 5x5 around our core. Both `Core` and
//! `Builder` call `classify` so the result is deterministic across
//! every friendly unit without inter-unit comms.

use cambc::{Controller, ControllerApi, Environment, Position};

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
    /// Multiplier on `Core::INITIAL_SPAWNS`. 1.0 = unchanged.
    #[must_use]
    pub const fn initial_spawn_factor(self) -> f64 {
        match self {
            Self::OpenEcon => 1.0,
            Self::Corridor => 1.0,
            Self::ChokeBunker => 0.75,
            Self::DefaultBalanced => 1.0,
        }
    }

    /// Multiplicative bias on the income/surplus thresholds. >1.0 ⇒
    /// spawn less eagerly (higher bar). <1.0 ⇒ spawn more eagerly.
    #[must_use]
    pub const fn spawn_eagerness(self) -> f64 {
        match self {
            Self::OpenEcon => 0.85,
            Self::Corridor => 1.0,
            Self::ChokeBunker => 1.15,
            Self::DefaultBalanced => 1.0,
        }
    }

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

/// Classify the map. Both Core and Builder call this with their own
/// `my_core` so each side gets a template tuned to its own opening,
/// and every friendly unit on the same team derives the same template.
#[must_use]
pub fn classify(
    width: i32,
    height: i32,
    my_core: Position,
    en_core_guess: Position,
    ct: &mut Controller<'_>,
) -> OpeningTemplate {
    let area = width * height;

    let mn = pyrust::max!(pyrust::min!(width, height), 1);
    let mx = pyrust::max!(width, height);
    let eccentricity = pyrust::float!(mx) / pyrust::float!(mn);

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
            let p = Position { x, y };
            if !pyrust::unwrap!(ct.is_in_vision(p)) {
                continue;
            }
            let env = pyrust::unwrap!(ct.get_tile_env(p));
            inner_total += 1;
            if env == Environment::Wall {
                inner_walls += 1;
            }
            if matches!(env, Environment::OreTitanium | Environment::OreAxionite) {
                inner_ore += 1;
            }
        }
    }
    let inner_wall_density =
        pyrust::float!(inner_walls) / pyrust::float!(pyrust::max!(inner_total, 1));
    let inner_ore_density =
        pyrust::float!(inner_ore) / pyrust::float!(pyrust::max!(inner_total, 1));

    let dx = pyrust::abs!((en_core_guess.x - my_core.x));
    let dy = pyrust::abs!((en_core_guess.y - my_core.y));
    let enemy_chebyshev = pyrust::max!(dx, dy);

    if inner_wall_density >= 0.30 {
        return OpeningTemplate::ChokeBunker;
    }
    if eccentricity >= 2.0 {
        return OpeningTemplate::Corridor;
    }
    if area >= 30 * 30
        && inner_wall_density <= 0.10
        && inner_ore_density >= 0.08
        && enemy_chebyshev >= 20
    {
        return OpeningTemplate::OpenEcon;
    }
    OpeningTemplate::DefaultBalanced
}
