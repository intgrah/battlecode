use std::fmt;
use std::ops::Add;
use std::str::FromStr;

pub mod game_constants {
    pub const MAX_TURNS: i32 = 2000;
    pub const STACK_SIZE: i32 = 10;
    pub const STARTING_TITANIUM: i32 = 500;
    pub const STARTING_AXIONITE: i32 = 0;
    pub const MAX_TEAM_UNITS: i32 = 50;
    pub const PASSIVE_TITANIUM_AMOUNT: i32 = 10;
    pub const PASSIVE_TITANIUM_INTERVAL: i32 = 4;
    pub const AXIONITE_CONVERSION_TITANIUM_RATE: i32 = 4;

    pub const ACTION_RADIUS_SQ: i32 = 2;
    pub const CORE_SPAWNING_RADIUS_SQ: i32 = 2;
    pub const CORE_ACTION_RADIUS_SQ: i32 = 8;

    pub const CORE_VISION_RADIUS_SQ: i32 = 36;
    pub const BUILDER_BOT_VISION_RADIUS_SQ: i32 = 20;
    pub const GUNNER_VISION_RADIUS_SQ: i32 = 13;
    pub const SENTINEL_VISION_RADIUS_SQ: i32 = 32;
    pub const BREACH_VISION_RADIUS_SQ: i32 = 2;
    pub const LAUNCHER_VISION_RADIUS_SQ: i32 = 26;

    pub const CONVEYOR_BASE_COST: (i32, i32) = (3, 0);
    pub const SPLITTER_BASE_COST: (i32, i32) = (6, 0);
    pub const BRIDGE_BASE_COST: (i32, i32) = (20, 0);
    pub const ARMOURED_CONVEYOR_BASE_COST: (i32, i32) = (5, 5);
    pub const HARVESTER_BASE_COST: (i32, i32) = (20, 0);
    pub const ROAD_BASE_COST: (i32, i32) = (1, 0);
    pub const BARRIER_BASE_COST: (i32, i32) = (3, 0);
    pub const GUNNER_BASE_COST: (i32, i32) = (10, 0);
    pub const SENTINEL_BASE_COST: (i32, i32) = (30, 0);
    pub const BREACH_BASE_COST: (i32, i32) = (15, 10);
    pub const LAUNCHER_BASE_COST: (i32, i32) = (20, 0);
    pub const FOUNDRY_BASE_COST: (i32, i32) = (40, 0);
    pub const BUILDER_BOT_BASE_COST: (i32, i32) = (30, 0);
    pub const GUNNER_ROTATE_COST: (i32, i32) = (10, 0);
    pub const GUNNER_ROTATE_COOLDOWN: i32 = 1;

    pub const CONVEYOR_MAX_HP: i32 = 20;
    pub const SPLITTER_MAX_HP: i32 = 20;
    pub const BRIDGE_MAX_HP: i32 = 20;
    pub const ARMOURED_CONVEYOR_MAX_HP: i32 = 50;
    pub const HARVESTER_MAX_HP: i32 = 30;
    pub const ROAD_MAX_HP: i32 = 4;
    pub const BARRIER_MAX_HP: i32 = 30;
    pub const FOUNDRY_MAX_HP: i32 = 50;
    pub const MARKER_MAX_HP: i32 = 1;

    pub const BUILDER_BOT_MAX_HP: i32 = 40;
    pub const CORE_MAX_HP: i32 = 500;
    pub const GUNNER_MAX_HP: i32 = 40;
    pub const SENTINEL_MAX_HP: i32 = 30;
    pub const BREACH_MAX_HP: i32 = 60;
    pub const LAUNCHER_MAX_HP: i32 = 30;

    pub const BUILDER_BOT_SELF_DESTRUCT_DAMAGE: i32 = 0;
    pub const BUILDER_BOT_ATTACK_DAMAGE: i32 = 2;
    pub const BUILDER_BOT_ATTACK_COST: (i32, i32) = (2, 0);
    pub const BUILDER_BOT_HEAL_COST: (i32, i32) = (1, 0);
    pub const HEAL_AMOUNT: i32 = 4;

    pub const BRIDGE_TARGET_RADIUS_SQ: i32 = 9;

    // Turret firing constants
    pub const GUNNER_DAMAGE: i32 = 10;
    pub const GUNNER_AXIONITE_DAMAGE: i32 = 25;
    pub const GUNNER_FIRE_COOLDOWN: i32 = 1;
    pub const GUNNER_AMMO_COST: i32 = 2;

    pub const SENTINEL_DAMAGE: i32 = 18;
    pub const SENTINEL_FIRE_COOLDOWN: i32 = 3;
    pub const SENTINEL_AMMO_COST: i32 = 10;
    pub const SENTINEL_STUN_DURATION: i32 = 5;

    pub const BREACH_DAMAGE: i32 = 40;
    pub const BREACH_SPLASH_DAMAGE: i32 = 20;
    pub const BREACH_FIRE_COOLDOWN: i32 = 1;
    pub const BREACH_AMMO_COST: i32 = 5;
    pub const BREACH_ATTACK_RADIUS_SQ: i32 = 24;

    pub const LAUNCHER_FIRE_COOLDOWN: i32 = 1;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Pos {
    pub x: i32,
    pub y: i32,
}

impl Add<Direction> for Pos {
    type Output = Self;

    fn add(self, d: Direction) -> Self {
        let (dx, dy) = d.delta();
        Self {
            x: self.x + dx,
            y: self.y + dy,
        }
    }
}

impl Pos {
    #[must_use]
    pub const fn distance_squared(self, other: Self) -> i32 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        dx * dx + dy * dy
    }

    /// Inherent shorthand for `<Pos as Add<Direction>>::add`. Lets bots
    /// write `pos.add(d)` without importing `std::ops::Add`, matching the
    /// Python `Position.add(d)` shape.
    #[must_use]
    pub fn add(self, d: Direction) -> Self {
        <Self as std::ops::Add<Direction>>::add(self, d)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Team {
    A,
    B,
}

impl Team {
    #[must_use]
    pub const fn index(self) -> usize {
        match self {
            Self::A => 0,
            Self::B => 1,
        }
    }
}

impl fmt::Display for Team {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::A => write!(f, "a"),
            Self::B => write!(f, "b"),
        }
    }
}

impl FromStr for Team {
    type Err = ();

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "a" => Ok(Self::A),
            "b" => Ok(Self::B),
            _ => Err(()),
        }
    }
}

/// Mirror of Python `EntityType`. Used by the controller's generic
/// `can_build` / `build` dispatch and for `get_attackable_tiles_from`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum EntityType {
    BuilderBot,
    Core,
    Gunner,
    Sentinel,
    Breach,
    Launcher,
    Conveyor,
    Splitter,
    ArmouredConveyor,
    Bridge,
    Harvester,
    Foundry,
    Road,
    Barrier,
    Marker,
}

impl FromStr for EntityType {
    type Err = ();

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "builder_bot" => Ok(Self::BuilderBot),
            "core" => Ok(Self::Core),
            "gunner" => Ok(Self::Gunner),
            "sentinel" => Ok(Self::Sentinel),
            "breach" => Ok(Self::Breach),
            "launcher" => Ok(Self::Launcher),
            "conveyor" => Ok(Self::Conveyor),
            "splitter" => Ok(Self::Splitter),
            "armoured_conveyor" => Ok(Self::ArmouredConveyor),
            "bridge" => Ok(Self::Bridge),
            "harvester" => Ok(Self::Harvester),
            "foundry" => Ok(Self::Foundry),
            "road" => Ok(Self::Road),
            "barrier" => Ok(Self::Barrier),
            "marker" => Ok(Self::Marker),
            _ => Err(()),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ResourceType {
    Titanium,
    RawAxionite,
    RefinedAxionite,
}

impl fmt::Display for ResourceType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Titanium => write!(f, "titanium"),
            Self::RawAxionite => write!(f, "raw_axionite"),
            Self::RefinedAxionite => write!(f, "refined_axionite"),
        }
    }
}

impl FromStr for ResourceType {
    type Err = ();

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "titanium" => Ok(Self::Titanium),
            "raw_axionite" => Ok(Self::RawAxionite),
            "refined_axionite" => Ok(Self::RefinedAxionite),
            _ => Err(()),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Environment {
    Empty,
    Wall,
    OreTitanium,
    OreAxionite,
}

impl fmt::Display for Environment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Empty => write!(f, "empty"),
            Self::Wall => write!(f, "wall"),
            Self::OreTitanium => write!(f, "ore_titanium"),
            Self::OreAxionite => write!(f, "ore_axionite"),
        }
    }
}

impl FromStr for Environment {
    type Err = ();

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "empty" => Ok(Self::Empty),
            "wall" => Ok(Self::Wall),
            "ore_titanium" => Ok(Self::OreTitanium),
            "ore_axionite" => Ok(Self::OreAxionite),
            _ => Err(()),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Direction {
    North,
    Northeast,
    East,
    Southeast,
    South,
    Southwest,
    West,
    Northwest,
    Centre,
}

impl fmt::Display for Direction {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::North => write!(f, "north"),
            Self::Northeast => write!(f, "northeast"),
            Self::East => write!(f, "east"),
            Self::Southeast => write!(f, "southeast"),
            Self::South => write!(f, "south"),
            Self::Southwest => write!(f, "southwest"),
            Self::West => write!(f, "west"),
            Self::Northwest => write!(f, "northwest"),
            Self::Centre => write!(f, "centre"),
        }
    }
}

impl FromStr for Direction {
    type Err = ();

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "north" => Ok(Self::North),
            "northeast" => Ok(Self::Northeast),
            "east" => Ok(Self::East),
            "southeast" => Ok(Self::Southeast),
            "south" => Ok(Self::South),
            "southwest" => Ok(Self::Southwest),
            "west" => Ok(Self::West),
            "northwest" => Ok(Self::Northwest),
            "centre" => Ok(Self::Centre),
            _ => Err(()),
        }
    }
}

impl Direction {
    #[must_use]
    pub const fn is_cardinal(self) -> bool {
        matches!(self, Self::North | Self::East | Self::South | Self::West)
    }

    #[must_use]
    pub fn is_directional(self) -> bool {
        self != Self::Centre
    }

    #[must_use]
    pub const fn delta(self) -> (i32, i32) {
        match self {
            Self::North => (0, -1),
            Self::Northeast => (1, -1),
            Self::East => (1, 0),
            Self::Southeast => (1, 1),
            Self::South => (0, 1),
            Self::Southwest => (-1, 1),
            Self::West => (-1, 0),
            Self::Northwest => (-1, -1),
            Self::Centre => (0, 0),
        }
    }

    #[must_use]
    pub const fn opposite(self) -> Self {
        match self {
            Self::North => Self::South,
            Self::Northeast => Self::Southwest,
            Self::East => Self::West,
            Self::Southeast => Self::Northwest,
            Self::South => Self::North,
            Self::Southwest => Self::Northeast,
            Self::West => Self::East,
            Self::Northwest => Self::Southeast,
            Self::Centre => Self::Centre,
        }
    }
}
