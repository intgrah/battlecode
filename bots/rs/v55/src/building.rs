//! Translation of `bots/intgrah/v54.7.9/building.py`.
//!
//! The Python ADT uses 14 frozen dataclasses unioned via `type Building = ...`.
//! In Rust this is a single sum-type enum with named-field variants — type-safe
//! and zero-cost. Pyrust will eventually translate this to the original 14
//! dataclasses + union (when the sum-type-enum extension lands).

use cambc::{Controller, ControllerApi, Direction, EntityType, Position, Team};

/// A building in the bot's vision. Construct via `make_building`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Building {
    Core { team: Team },
    Harvester { team: Team },
    Conveyor { team: Team, direction: Direction },
    ArmouredConveyor { team: Team, direction: Direction },
    Splitter { team: Team, direction: Direction },
    Bridge { team: Team, target: Position },
    Foundry { team: Team },
    Barrier { team: Team },
    Road { team: Team },
    Gunner { team: Team, direction: Direction },
    Sentinel { team: Team, direction: Direction },
    Breach { team: Team, direction: Direction },
    Launcher { team: Team },
    Marker { team: Team, value: u32 },
}

impl Building {
    /// The team that owns this building.
    #[must_use]
    pub const fn team(&self) -> Team {
        match *self {
            Building::Core { team }
            | Building::Harvester { team }
            | Building::Conveyor { team, .. }
            | Building::ArmouredConveyor { team, .. }
            | Building::Splitter { team, .. }
            | Building::Bridge { team, .. }
            | Building::Foundry { team }
            | Building::Barrier { team }
            | Building::Road { team }
            | Building::Gunner { team, .. }
            | Building::Sentinel { team, .. }
            | Building::Breach { team, .. }
            | Building::Launcher { team }
            | Building::Marker { team, .. } => team,
        }
    }
}

/// Read the building at entity id `bid` from the controller's vision.
///
/// Panics if `bid` refers to a `BuilderBot` (not a building). Mirrors the
/// Python `make_building(ct, bid)` factory which raises `ValueError`.
/// Controller calls `.unwrap()`: by convention bots check `is_in_vision`
/// and friends before calling these — any `GameError` is a logic bug.
pub fn make_building(ct: &Controller<'_>, bid: i32) -> Building {
    let team = ct.get_team(Some(bid)).unwrap();
    let direction = || ct.get_direction(Some(bid)).unwrap();
    match ct.get_entity_type(Some(bid)).unwrap() {
        EntityType::Conveyor => Building::Conveyor {
            team,
            direction: direction(),
        },
        EntityType::ArmouredConveyor => Building::ArmouredConveyor {
            team,
            direction: direction(),
        },
        EntityType::Splitter => Building::Splitter {
            team,
            direction: direction(),
        },
        EntityType::Gunner => Building::Gunner {
            team,
            direction: direction(),
        },
        EntityType::Sentinel => Building::Sentinel {
            team,
            direction: direction(),
        },
        EntityType::Breach => Building::Breach {
            team,
            direction: direction(),
        },
        EntityType::Bridge => Building::Bridge {
            team,
            target: ct.get_bridge_target(bid).unwrap(),
        },
        EntityType::Core => Building::Core { team },
        EntityType::Harvester => Building::Harvester { team },
        EntityType::Foundry => Building::Foundry { team },
        EntityType::Barrier => Building::Barrier { team },
        EntityType::Road => Building::Road { team },
        EntityType::Launcher => Building::Launcher { team },
        EntityType::Marker => {
            // Per the spec, `get_marker_value` is only valid for friendly
            // markers — calling it on an enemy marker is a `GameError`.
            // v54.7.9 calls it unconditionally and relies on `main.py`'s
            // last-resort `except` to recover; v55 gates on team so the
            // turn isn't lost. Enemy markers carry an opaque 0 here; bot
            // code that cares about the value already checks team.
            let my_team = ct.get_team(None).unwrap();
            let value = if team == my_team {
                ct.get_marker_value(bid).unwrap()
            } else {
                0
            };
            Building::Marker { team, value }
        }
        EntityType::BuilderBot => panic!("BUILDER_BOT is not a building"),
    }
}
