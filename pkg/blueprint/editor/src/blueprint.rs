use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Entity {
    Conveyor = 4,
    Splitter = 5,
    ArmouredConveyor = 6,
    Bridge = 7,
    Harvester = 8,
    Foundry = 9,
    Gunner = 10,
    Sentinel = 11,
    Launcher = 12,
    Breach = 13,
    Barrier = 14,
    Road = 15,
}

impl Entity {
    pub const fn name(self) -> &'static str {
        match self {
            Self::Conveyor => "CONVEYOR",
            Self::Splitter => "SPLITTER",
            Self::ArmouredConveyor => "ARMOURED_CONVEYOR",
            Self::Bridge => "BRIDGE",
            Self::Harvester => "HARVESTER",
            Self::Foundry => "FOUNDRY",
            Self::Gunner => "GUNNER",
            Self::Sentinel => "SENTINEL",
            Self::Launcher => "LAUNCHER",
            Self::Breach => "BREACH",
            Self::Barrier => "BARRIER",
            Self::Road => "ROAD",
        }
    }

    pub fn from_name(s: &str) -> Option<Self> {
        Some(match s {
            "CONVEYOR" => Self::Conveyor,
            "SPLITTER" => Self::Splitter,
            "ARMOURED_CONVEYOR" => Self::ArmouredConveyor,
            "BRIDGE" => Self::Bridge,
            "HARVESTER" => Self::Harvester,
            "FOUNDRY" => Self::Foundry,
            "GUNNER" => Self::Gunner,
            "SENTINEL" => Self::Sentinel,
            "LAUNCHER" => Self::Launcher,
            "BREACH" => Self::Breach,
            "BARRIER" => Self::Barrier,
            "ROAD" => Self::Road,
            _ => return None,
        })
    }

    pub const fn is_directional(self) -> bool {
        matches!(
            self,
            Self::Conveyor
                | Self::Splitter
                | Self::ArmouredConveyor
                | Self::Gunner
                | Self::Sentinel
                | Self::Breach
        )
    }

    pub const fn is_cardinal_only(self) -> bool {
        matches!(self, Self::Conveyor | Self::Splitter | Self::ArmouredConveyor)
    }
}

impl fmt::Display for Entity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.name())
    }
}

pub const ALL_ENTITIES: [Entity; 12] = [
    Entity::Conveyor,
    Entity::ArmouredConveyor,
    Entity::Splitter,
    Entity::Bridge,
    Entity::Harvester,
    Entity::Foundry,
    Entity::Gunner,
    Entity::Sentinel,
    Entity::Breach,
    Entity::Launcher,
    Entity::Barrier,
    Entity::Road,
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Direction {
    North = 1,
    NorthEast = 2,
    East = 3,
    SouthEast = 4,
    South = 5,
    SouthWest = 6,
    West = 7,
    NorthWest = 8,
}

impl Direction {
    pub const fn name(self) -> &'static str {
        match self {
            Self::North => "NORTH",
            Self::NorthEast => "NORTHEAST",
            Self::East => "EAST",
            Self::SouthEast => "SOUTHEAST",
            Self::South => "SOUTH",
            Self::SouthWest => "SOUTHWEST",
            Self::West => "WEST",
            Self::NorthWest => "NORTHWEST",
        }
    }

    pub fn from_name(s: &str) -> Option<Self> {
        Some(match s {
            "NORTH" => Self::North,
            "NORTHEAST" => Self::NorthEast,
            "EAST" => Self::East,
            "SOUTHEAST" => Self::SouthEast,
            "SOUTH" => Self::South,
            "SOUTHWEST" => Self::SouthWest,
            "WEST" => Self::West,
            "NORTHWEST" => Self::NorthWest,
            _ => return None,
        })
    }

    pub const fn delta(self) -> (i32, i32) {
        match self {
            Self::North => (0, -1),
            Self::NorthEast => (1, -1),
            Self::East => (1, 0),
            Self::SouthEast => (1, 1),
            Self::South => (0, 1),
            Self::SouthWest => (-1, 1),
            Self::West => (-1, 0),
            Self::NorthWest => (-1, -1),
        }
    }

    pub const fn from_delta(dx: i32, dy: i32) -> Option<Self> {
        Some(match (dx, dy) {
            (0, -1) => Self::North,
            (1, -1) => Self::NorthEast,
            (1, 0) => Self::East,
            (1, 1) => Self::SouthEast,
            (0, 1) => Self::South,
            (-1, 1) => Self::SouthWest,
            (-1, 0) => Self::West,
            (-1, -1) => Self::NorthWest,
            _ => return None,
        })
    }
}

pub const CARDINALS: [Direction; 4] = [
    Direction::North,
    Direction::East,
    Direction::South,
    Direction::West,
];

pub const ALL_DIRECTIONS: [Direction; 8] = [
    Direction::North,
    Direction::NorthEast,
    Direction::East,
    Direction::SouthEast,
    Direction::South,
    Direction::SouthWest,
    Direction::West,
    Direction::NorthWest,
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BlueprintEntry {
    pub pos: (i32, i32),
    pub kind: Entity,
    pub direction: Option<Direction>,
    pub bridge_target: Option<(i32, i32)>,
    pub phase: i32,
}

