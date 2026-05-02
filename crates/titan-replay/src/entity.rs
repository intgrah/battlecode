use crate::proto;
use crate::state::{Entity, EntityKind};
use titan_core::constants as c;

#[must_use]
pub const fn label(kind: &EntityKind) -> &'static str {
    match kind {
        EntityKind::BuilderBot { .. } => "Builder",
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => "Core",
        EntityKind::Conveyor { .. } => "Conveyor",
        EntityKind::ArmouredConveyor { .. } => "Arm. Conv",
        EntityKind::Splitter { .. } => "Splitter",
        EntityKind::Bridge { .. } => "Bridge",
        EntityKind::Harvester { .. } => "Harvester",
        EntityKind::Foundry { .. } => "Foundry",
        EntityKind::Road => "Road",
        EntityKind::Barrier => "Barrier",
        EntityKind::Marker { .. } => "Marker",
        EntityKind::Gunner { .. } => "Gunner",
        EntityKind::Sentinel { .. } => "Sentinel",
        EntityKind::Breach { .. } => "Breach",
        EntityKind::Launcher { .. } => "Launcher",
    }
}

/// Scale contribution in millis (1 milli = 0.1%).
#[must_use]
pub const fn scale_millis(kind: &EntityKind) -> u32 {
    match kind {
        EntityKind::Road => 5,
        EntityKind::Conveyor { .. }
        | EntityKind::ArmouredConveyor { .. }
        | EntityKind::Splitter { .. }
        | EntityKind::Barrier => 10,
        EntityKind::Harvester { .. } => 50,
        EntityKind::Bridge { .. }
        | EntityKind::Gunner { .. }
        | EntityKind::Breach { .. }
        | EntityKind::Launcher { .. } => 100,
        EntityKind::BuilderBot { .. } | EntityKind::Sentinel { .. } => 200,
        EntityKind::Foundry { .. } => 500,
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } | EntityKind::Marker { .. } => 0,
    }
}

#[must_use]
pub const fn z_order(kind: &EntityKind) -> i32 {
    match kind {
        EntityKind::Road => 0,
        EntityKind::Marker { .. } => 1,
        EntityKind::Barrier => 2,
        EntityKind::CoreEdge { .. } => 3,
        EntityKind::Conveyor { .. }
        | EntityKind::ArmouredConveyor { .. }
        | EntityKind::Splitter { .. }
        | EntityKind::Bridge { .. } => 4,
        EntityKind::Harvester { .. } | EntityKind::Foundry { .. } => 5,
        EntityKind::Gunner { .. }
        | EntityKind::Sentinel { .. }
        | EntityKind::Breach { .. }
        | EntityKind::Launcher { .. } => 6,
        EntityKind::Core { .. } => 7,
        EntityKind::BuilderBot { .. } => 8,
    }
}

#[must_use]
pub const fn sort_key(kind: &EntityKind) -> u8 {
    // Display order in the stats / cost panels:
    // builder, road, barrier, conveyor, armoured conveyor, bridge,
    // splitter, harvester, foundry, gunner, sentinel, breach, launcher.
    // Core / CoreEdge come first (always present); marker last.
    match kind {
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => 0,
        EntityKind::BuilderBot { .. } => 1,
        EntityKind::Road => 2,
        EntityKind::Barrier => 3,
        EntityKind::Conveyor { .. } => 4,
        EntityKind::ArmouredConveyor { .. } => 5,
        EntityKind::Bridge { .. } => 6,
        EntityKind::Splitter { .. } => 7,
        EntityKind::Harvester { .. } => 8,
        EntityKind::Foundry { .. } => 9,
        EntityKind::Gunner { .. } => 10,
        EntityKind::Sentinel { .. } => 11,
        EntityKind::Breach { .. } => 12,
        EntityKind::Launcher { .. } => 13,
        EntityKind::Marker { .. } => 14,
    }
}

#[must_use]
pub const fn is_resource_holder(kind: &EntityKind) -> bool {
    matches!(
        kind,
        EntityKind::Conveyor { .. }
            | EntityKind::ArmouredConveyor { .. }
            | EntityKind::Splitter { .. }
            | EntityKind::Bridge { .. }
            | EntityKind::Foundry { .. }
            | EntityKind::Harvester { .. }
            | EntityKind::Core { .. }
            | EntityKind::Gunner { .. }
            | EntityKind::Sentinel { .. }
            | EntityKind::Breach { .. }
            | EntityKind::Launcher { .. }
    )
}

#[must_use]
pub const fn stored_resource(kind: &EntityKind) -> Option<proto::ResourceType> {
    match kind {
        EntityKind::Conveyor { stored, .. }
        | EntityKind::ArmouredConveyor { stored, .. }
        | EntityKind::Splitter { stored, .. }
        | EntityKind::Bridge { stored, .. }
        | EntityKind::Foundry { stored } => Some(*stored),
        EntityKind::Harvester { resource_type, .. } => Some(*resource_type),
        _ => None,
    }
}

#[must_use]
pub const fn resource_sprite(kind: &EntityKind) -> Option<&'static str> {
    let res = match kind {
        EntityKind::Conveyor { stored, .. }
        | EntityKind::ArmouredConveyor { stored, .. }
        | EntityKind::Splitter { stored, .. }
        | EntityKind::Bridge { stored, .. }
        | EntityKind::Foundry { stored } => *stored,
        _ => return None,
    };
    match res {
        proto::ResourceType::ResourceTitanium => Some("titanium"),
        proto::ResourceType::ResourceRawAxionite => Some("axionite_raw"),
        proto::ResourceType::ResourceRefinedAxionite => Some("axionite_processed"),
        proto::ResourceType::ResourceNone => None,
    }
}

#[must_use]
pub const fn dir_suffix(dir: proto::Direction) -> &'static str {
    match dir {
        proto::Direction::DirNorth | proto::Direction::DirCentre => "n",
        proto::Direction::DirNortheast => "ne",
        proto::Direction::DirEast => "e",
        proto::Direction::DirSoutheast => "se",
        proto::Direction::DirSouth => "s",
        proto::Direction::DirSouthwest => "sw",
        proto::Direction::DirWest => "w",
        proto::Direction::DirNorthwest => "nw",
    }
}

#[must_use]
pub const fn dir_name(dx: i32, dy: i32) -> &'static str {
    match (dx.signum(), dy.signum()) {
        (0, -1) => "N",
        (1, -1) => "NE",
        (1, 0) => "E",
        (1, 1) => "SE",
        (0, 1) => "S",
        (-1, 1) => "SW",
        (-1, 0) => "W",
        (-1, -1) => "NW",
        _ => "?",
    }
}

#[must_use]
pub const fn dir_delta(dir: proto::Direction) -> (i32, i32) {
    match dir {
        proto::Direction::DirNorth => (0, -1),
        proto::Direction::DirSouth => (0, 1),
        proto::Direction::DirEast => (1, 0),
        proto::Direction::DirWest => (-1, 0),
        proto::Direction::DirNortheast => (1, -1),
        proto::Direction::DirSoutheast => (1, 1),
        proto::Direction::DirSouthwest => (-1, 1),
        proto::Direction::DirNorthwest => (-1, -1),
        proto::Direction::DirCentre => (0, 0),
    }
}

#[must_use]
pub fn sprite_name(e: &Entity) -> String {
    let team = match e.team {
        proto::Team::A => "gold",
        proto::Team::B => "silver",
    };
    match &e.kind {
        EntityKind::BuilderBot { .. } => format!("builderbot_front_{team}"),
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => format!("base_{team}"),
        EntityKind::Conveyor { dir, .. } => format!("conveyor_{team}_{}", dir_suffix(*dir)),
        EntityKind::ArmouredConveyor { dir, .. } => {
            format!("armoured_conveyor_{team}_{}", dir_suffix(*dir))
        }
        EntityKind::Splitter { dir, .. } => format!("splitter_{}_{team}", dir_suffix(*dir)),
        EntityKind::Bridge { .. } => format!("bridge_stand_{team}"),
        EntityKind::Harvester { .. } => format!("harvester_{team}"),
        EntityKind::Foundry { .. } => format!("foundry_{team}"),
        EntityKind::Road => format!("road_{team}"),
        EntityKind::Barrier => format!("barrier_{team}"),
        EntityKind::Marker { .. } => format!("marker_{team}"),
        EntityKind::Gunner { dir, .. } => format!("gunner_{}_{team}", dir_suffix(*dir)),
        EntityKind::Sentinel { dir, .. } => format!("sentinel_{}_{team}", dir_suffix(*dir)),
        EntityKind::Breach { dir, .. } => format!("breach_{}_{team}", dir_suffix(*dir)),
        EntityKind::Launcher { .. } => format!("launcher_{team}"),
    }
}

pub const BUILDABLE_COSTS: &[(&str, (i32, i32))] = &[
    ("Builder", c::BUILDER_BOT_BASE_COST),
    ("Road", c::ROAD_BASE_COST),
    ("Barrier", c::BARRIER_BASE_COST),
    ("Conveyor", c::CONVEYOR_BASE_COST),
    ("Arm. Conv", c::ARMOURED_CONVEYOR_BASE_COST),
    ("Bridge", c::BRIDGE_BASE_COST),
    ("Splitter", c::SPLITTER_BASE_COST),
    ("Harvester", c::HARVESTER_BASE_COST),
    ("Foundry", c::FOUNDRY_BASE_COST),
    ("Gunner", c::GUNNER_BASE_COST),
    ("Sentinel", c::SENTINEL_BASE_COST),
    ("Breach", c::BREACH_BASE_COST),
    ("Launcher", c::LAUNCHER_BASE_COST),
];
