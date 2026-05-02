use crate::common::game_constants::{
    ACTION_RADIUS_SQ, ARMOURED_CONVEYOR_MAX_HP, BARRIER_MAX_HP, BREACH_MAX_HP,
    BREACH_VISION_RADIUS_SQ, BRIDGE_MAX_HP, BUILDER_BOT_VISION_RADIUS_SQ, CONVEYOR_MAX_HP,
    CORE_ACTION_RADIUS_SQ, CORE_VISION_RADIUS_SQ, FOUNDRY_MAX_HP, GUNNER_MAX_HP,
    GUNNER_VISION_RADIUS_SQ, HARVESTER_MAX_HP, LAUNCHER_MAX_HP, LAUNCHER_VISION_RADIUS_SQ,
    MARKER_MAX_HP, ROAD_MAX_HP, SENTINEL_MAX_HP, SENTINEL_VISION_RADIUS_SQ, SPLITTER_MAX_HP,
    STACK_SIZE,
};
use crate::common::{Direction, Environment, Pos, ResourceType, Team};
use paste::paste;
use rustc_hash::FxHashMap;
use std::ops::{Deref, DerefMut};

macro_rules! impl_derefs {
    ($ty:ty, $target:ident) => {
        paste! {
            impl Deref for $ty {
                type Target = [< $target:camel Base>];

                fn deref(&self) -> &Self::Target {
                    &self.$target
                }
            }

            impl DerefMut for $ty {
                fn deref_mut(&mut self) -> &mut Self::Target {
                    &mut self.$target
                }
            }
        }
    };
}

#[derive(Clone, Debug)]
pub struct EntityBase {
    pub id: i32,
    pub team: Team,
    pub position: Pos,
    pub hp: i32,
    pub max_hp: i32,
}

#[derive(Clone, Debug)]
pub enum Entity {
    BuilderBot(BuilderBot),
    Conveyor(Conveyor),
    Splitter(Splitter),
    ArmouredConveyor(ArmouredConveyor),
    Bridge(Bridge),
    Harvester(Harvester),
    Foundry(Foundry),
    Road(Road),
    Barrier(Barrier),
    Marker(Marker),
    Core(Core),
    Gunner(Gunner),
    Sentinel(Sentinel),
    Breach(Breach),
    Launcher(Launcher),
}

impl Deref for Entity {
    type Target = EntityBase;

    fn deref(&self) -> &Self::Target {
        match self {
            Self::BuilderBot(bot) => bot,
            Self::Conveyor(c) => c,
            Self::Splitter(c) => c,
            Self::ArmouredConveyor(c) => c,
            Self::Bridge(b) => b,
            Self::Harvester(h) => h,
            Self::Foundry(f) => f,
            Self::Road(r) => r,
            Self::Barrier(b) => b,
            Self::Marker(m) => m,
            Self::Core(c) => c,
            Self::Gunner(t) => t,
            Self::Sentinel(t) => t,
            Self::Breach(t) => t,
            Self::Launcher(t) => t,
        }
    }
}

impl DerefMut for Entity {
    fn deref_mut(&mut self) -> &mut Self::Target {
        match self {
            Self::BuilderBot(bot) => bot,
            Self::Conveyor(c) => c,
            Self::Splitter(c) => c,
            Self::ArmouredConveyor(c) => c,
            Self::Bridge(b) => b,
            Self::Harvester(h) => h,
            Self::Foundry(f) => f,
            Self::Road(r) => r,
            Self::Barrier(b) => b,
            Self::Marker(m) => m,
            Self::Core(c) => c,
            Self::Gunner(t) => t,
            Self::Sentinel(t) => t,
            Self::Breach(t) => t,
            Self::Launcher(t) => t,
        }
    }
}

impl Entity {
    #[must_use]
    pub const fn as_unit(&self) -> Option<Unit<'_>> {
        match self {
            Self::BuilderBot(bot) => Some(Unit::BuilderBot(bot)),
            Self::Core(core) => Some(Unit::Core(core)),
            Self::Gunner(t) => Some(Unit::Gunner(t)),
            Self::Sentinel(t) => Some(Unit::Sentinel(t)),
            Self::Breach(t) => Some(Unit::Breach(t)),
            Self::Launcher(t) => Some(Unit::Launcher(t)),
            _ => None,
        }
    }

    pub const fn as_unit_mut(&mut self) -> Option<UnitMut<'_>> {
        match self {
            Self::BuilderBot(bot) => Some(UnitMut::BuilderBot(bot)),
            Self::Core(core) => Some(UnitMut::Core(core)),
            Self::Gunner(t) => Some(UnitMut::Gunner(t)),
            Self::Sentinel(t) => Some(UnitMut::Sentinel(t)),
            Self::Breach(t) => Some(UnitMut::Breach(t)),
            Self::Launcher(t) => Some(UnitMut::Launcher(t)),
            _ => None,
        }
    }

    #[must_use]
    pub const fn as_turret(&self) -> Option<Turret<'_>> {
        match self {
            Self::Gunner(t) => Some(Turret::Gunner(t)),
            Self::Sentinel(t) => Some(Turret::Sentinel(t)),
            Self::Breach(t) => Some(Turret::Breach(t)),
            Self::Launcher(t) => Some(Turret::Launcher(t)),
            _ => None,
        }
    }

    pub const fn as_turret_mut(&mut self) -> Option<TurretMut<'_>> {
        match self {
            Self::Gunner(t) => Some(TurretMut::Gunner(t)),
            Self::Sentinel(t) => Some(TurretMut::Sentinel(t)),
            Self::Breach(t) => Some(TurretMut::Breach(t)),
            Self::Launcher(t) => Some(TurretMut::Launcher(t)),
            _ => None,
        }
    }

    #[must_use]
    pub const fn as_building(&self) -> Option<Building<'_>> {
        match self {
            Self::BuilderBot(_) => None,
            Self::Conveyor(c) => Some(Building::Conveyor(c)),
            Self::Splitter(c) => Some(Building::Splitter(c)),
            Self::ArmouredConveyor(c) => Some(Building::ArmouredConveyor(c)),
            Self::Bridge(b) => Some(Building::Bridge(b)),
            Self::Harvester(h) => Some(Building::Harvester(h)),
            Self::Foundry(f) => Some(Building::Foundry(f)),
            Self::Road(r) => Some(Building::Road(r)),
            Self::Barrier(b) => Some(Building::Barrier(b)),
            Self::Marker(m) => Some(Building::Marker(m)),
            Self::Core(c) => Some(Building::Core(c)),
            Self::Gunner(t) => Some(Building::Gunner(t)),
            Self::Sentinel(t) => Some(Building::Sentinel(t)),
            Self::Breach(t) => Some(Building::Breach(t)),
            Self::Launcher(t) => Some(Building::Launcher(t)),
        }
    }

    pub const fn as_building_mut(&mut self) -> Option<BuildingMut<'_>> {
        match self {
            Self::BuilderBot(_) => None,
            Self::Conveyor(c) => Some(BuildingMut::Conveyor(c)),
            Self::Splitter(c) => Some(BuildingMut::Splitter(c)),
            Self::ArmouredConveyor(c) => Some(BuildingMut::ArmouredConveyor(c)),
            Self::Bridge(b) => Some(BuildingMut::Bridge(b)),
            Self::Harvester(h) => Some(BuildingMut::Harvester(h)),
            Self::Foundry(f) => Some(BuildingMut::Foundry(f)),
            Self::Road(r) => Some(BuildingMut::Road(r)),
            Self::Barrier(b) => Some(BuildingMut::Barrier(b)),
            Self::Marker(m) => Some(BuildingMut::Marker(m)),
            Self::Core(c) => Some(BuildingMut::Core(c)),
            Self::Gunner(t) => Some(BuildingMut::Gunner(t)),
            Self::Sentinel(t) => Some(BuildingMut::Sentinel(t)),
            Self::Breach(t) => Some(BuildingMut::Breach(t)),
            Self::Launcher(t) => Some(BuildingMut::Launcher(t)),
        }
    }

    #[must_use]
    pub const fn scale_contribution(&self) -> i32 {
        // Values are in milli-percent: +10 = +1%. Per docs/spec/reference.md
        // and docs/spec/resources.md cost-scaling table.
        match self {
            Self::Road(_) => 5, // +0.5%
            Self::Conveyor(_)
            | Self::Splitter(_)
            | Self::ArmouredConveyor(_)
            | Self::Barrier(_) => 10, // +1%
            Self::Harvester(_) => 50, // +5%
            Self::Bridge(_) | Self::Gunner(_) | Self::Breach(_) | Self::Launcher(_) => 100, // +10%
            Self::Sentinel(_) => 200, // +20%
            Self::Foundry(_) => 500, // +50%
            // BuilderBot scale (+20%) is applied at spawn/remove sites,
            // not via scale_contribution (it isn't a building).
            _ => 0,
        }
    }

    #[must_use]
    pub fn resource_to_feed(&self) -> Option<ResourceType> {
        match self {
            Self::Conveyor(c) => c.stored,
            Self::Splitter(s) => s.stored,
            Self::ArmouredConveyor(c) => c.stored,
            Self::Bridge(b) => b.stored,
            Self::Harvester(h) => {
                if h.cooldown == 0 {
                    Some(h.resource_type)
                } else {
                    None
                }
            }
            Self::Foundry(f) => {
                if f.stored == Some(ResourceType::RefinedAxionite) {
                    Some(ResourceType::RefinedAxionite)
                } else {
                    None
                }
            }
            _ => None,
        }
    }

    #[must_use]
    pub fn output_targets(&self) -> Vec<Pos> {
        match self {
            Self::Conveyor(c) => vec![c.position + c.direction],
            Self::ArmouredConveyor(c) => vec![c.position + c.direction],
            Self::Bridge(b) => vec![b.target],
            Self::Splitter(s) => {
                let excluded = s.direction.opposite();
                let dirs = [
                    Direction::North,
                    Direction::East,
                    Direction::South,
                    Direction::West,
                ];
                dirs.iter()
                    .filter(|d| **d != excluded)
                    .map(|d| s.position + *d)
                    .collect()
            }
            Self::Harvester(h) => {
                let dirs = [
                    Direction::North,
                    Direction::East,
                    Direction::South,
                    Direction::West,
                ];
                dirs.iter().map(|d| h.position + *d).collect()
            }
            Self::Foundry(f) => {
                let dirs = [
                    Direction::North,
                    Direction::East,
                    Direction::South,
                    Direction::West,
                ];
                dirs.iter().map(|d| f.position + *d).collect()
            }
            _ => Vec::new(),
        }
    }

    pub fn consume_feed(&mut self) {
        match self {
            Self::Conveyor(c) => {
                c.stored = None;
                c.stored_resource_id = None;
            }
            Self::Splitter(s) => {
                s.stored = None;
                s.stored_resource_id = None;
            }
            Self::ArmouredConveyor(c) => {
                c.stored = None;
                c.stored_resource_id = None;
            }
            Self::Bridge(b) => {
                b.stored = None;
                b.stored_resource_id = None;
            }
            Self::Harvester(h) => h.cooldown = 4,
            Self::Foundry(f) => {
                f.stored = None;
                f.stored_resource_id = None;
            }
            _ => panic!("consume_feed called on non-feeder entity"),
        }
    }

    #[must_use]
    pub fn can_accept_from(
        &self,
        resource: ResourceType,
        source_pos: Pos,
        source_is_bridge: bool,
    ) -> bool {
        match self {
            Self::Conveyor(c) => {
                // Rejects input from its output direction.
                (source_is_bridge || source_pos != c.position + c.direction) && c.stored.is_none()
            }
            Self::Splitter(s) => {
                // Splitter only accepts input from its entry side (direction.opposite()).
                let input_pos = s.position + s.direction.opposite();
                if !source_is_bridge && source_pos != input_pos {
                    return false;
                }
                s.stored.is_none()
            }
            Self::ArmouredConveyor(c) => {
                // Rejects input from its output direction.
                (source_is_bridge || source_pos != c.position + c.direction) && c.stored.is_none()
            }
            Self::Bridge(b) => b.stored.is_none(),
            Self::Foundry(f) => {
                matches!(
                    (resource, f.stored),
                    (
                        ResourceType::Titanium,
                        Some(ResourceType::RawAxionite) | None
                    ) | (
                        ResourceType::RawAxionite,
                        Some(ResourceType::Titanium) | None
                    )
                )
            }
            Self::Core(_) => true,
            Self::Gunner(t) => {
                t.ammo_amount == 0 && (source_is_bridge || source_pos != t.position + t.direction)
            }
            Self::Sentinel(t) => {
                t.ammo_amount == 0 && (source_is_bridge || source_pos != t.position + t.direction)
            }
            Self::Breach(t) => {
                // Breach accepts any resource type; titanium and raw axionite
                // are silently destroyed in receive_resource. Only refined
                // axionite actually loads as ammo. See docs/spec/turrets.md
                // (Breach section).
                let _ = resource;
                t.ammo_amount == 0 && (source_is_bridge || source_pos != t.position + t.direction)
            }

            Self::Launcher(_) => false,
            _ => false,
        }
    }

    /// Apply an incoming resource stack to this entity.
    ///
    /// `in_id` is the id of the incoming stack (preserved on storage
    /// transfers). `fresh_id_fn` produces a fresh id for newly-combined
    /// stacks (currently only refined axionite produced by a foundry).
    pub fn receive_resource(
        &mut self,
        resource: ResourceType,
        in_id: i32,
        fresh_id_fn: &mut dyn FnMut() -> i32,
    ) {
        match self {
            Self::Conveyor(c) => {
                c.stored = Some(resource);
                c.stored_resource_id = Some(in_id);
            }
            Self::Splitter(s) => {
                s.stored = Some(resource);
                s.stored_resource_id = Some(in_id);
            }
            Self::ArmouredConveyor(c) => {
                c.stored = Some(resource);
                c.stored_resource_id = Some(in_id);
            }
            Self::Bridge(b) => {
                b.stored = Some(resource);
                b.stored_resource_id = Some(in_id);
            }
            Self::Core(core) => core.received.push(resource),
            // Gunner / Sentinel: titanium and refined axionite load as ammo.
            // Raw axionite delivered to a turret is destroyed (per
            // docs/spec/turrets.md "Raw axionite fed into a turret is
            // destroyed").
            Self::Gunner(t) => t.turret.load_ammo_for_standard_turret(resource),
            Self::Sentinel(t) => t.turret.load_ammo_for_standard_turret(resource),
            // Breach: only refined axionite loads as ammo. Titanium and raw
            // axionite are destroyed (this prevents conveyor backups feeding
            // a breach with non-axionite resources).
            Self::Breach(t) => t.turret.load_ammo_for_breach(resource),
            Self::Foundry(f) => match (resource, f.stored) {
                (r @ (ResourceType::Titanium | ResourceType::RawAxionite), None) => {
                    f.stored = Some(r);
                    f.stored_resource_id = Some(in_id);
                }
                (ResourceType::Titanium, Some(ResourceType::RawAxionite))
                | (ResourceType::RawAxionite, Some(ResourceType::Titanium)) => {
                    // Combined output is a fresh stack with a fresh id.
                    f.stored = Some(ResourceType::RefinedAxionite);
                    f.stored_resource_id = Some(fresh_id_fn());
                }
                _ => panic!(
                    "foundry received unexpected resource {:?} with stored {:?}",
                    resource, f.stored
                ),
            },
            _ => panic!("receive_resource called on non-receiver entity"),
        }
    }

    /// The id of the stack this entity would feed in distribution this
    /// turn, paired with its resource type. Returns `None` if the entity
    /// is empty / not ready to feed (analogous to `resource_to_feed`).
    ///
    /// For harvesters, returns `None` even when `cooldown == 0`, because
    /// a producer doesn't know its output id until it actually produces;
    /// the distribute loop assigns a fresh id at that moment.
    #[must_use]
    pub fn feed_id(&self) -> Option<i32> {
        match self {
            Self::Conveyor(c) => c.stored_resource_id,
            Self::Splitter(s) => s.stored_resource_id,
            Self::ArmouredConveyor(c) => c.stored_resource_id,
            Self::Bridge(b) => b.stored_resource_id,
            Self::Foundry(f) if f.stored == Some(ResourceType::RefinedAxionite) => {
                f.stored_resource_id
            }
            _ => None,
        }
    }
}

macro_rules! define_category {
    ($name:ident : $parent:ident [$base_type:ty] ($($variant:ident),* $(,)?) {$($field:ident : $type:ty),* $(,)?}) => {
        paste! {
            #[derive(Clone, Debug)]
            pub struct [< $name Base >] {
                pub [< $parent:lower >]: [< $parent Base >],
                $(
                    pub $field: $type,
                 )*
            }
            impl_derefs!([< $name Base >], [< $parent:lower >]);

            #[derive(Clone, Copy, Debug)]
            pub enum $name<'a> {
                $($variant(&'a $variant)),*
            }
            impl<'a> Deref for $name<'a> {
                type Target = [< $base_type Base >];
                fn deref(&self) -> &Self::Target {
                    match self {
                        $(
                            Self::$variant(v) => &v.[< $base_type:lower >],
                        )*
                    }
                }
            }

            #[derive(Debug)]
            pub enum [< $name Mut >]<'a> {
                $($variant(&'a mut $variant)),*
            }
            impl<'a> Deref for [< $name Mut >]<'a> {
                type Target = [< $base_type Base >];
                fn deref(&self) -> &Self::Target {
                    match self {
                        $(
                            Self::$variant(v) => &v.[< $base_type:lower >],
                        )*
                    }
                }
            }
            impl<'a> DerefMut for [< $name Mut >]<'a> {
                fn deref_mut(&mut self) -> &mut Self::Target {
                    match self {
                        $(
                            Self::$variant(v) => &mut v.[< $base_type:lower >],
                        )*
                    }
                }
            }
        }
    };
}

define_category! {
    Unit : Entity [Unit] (
        BuilderBot,
        Core,
        Gunner,
        Sentinel,
        Breach,
        Launcher,
    ) {
        action_cooldown: i32,
        move_cooldown: i32,
    }
}

impl UnitBase {
    #[must_use]
    pub const fn can_act(&self) -> bool {
        self.action_cooldown <= 0
    }

    #[must_use]
    pub const fn can_move(&self) -> bool {
        self.move_cooldown <= 0
    }

    pub const fn end_turn(&mut self) {
        if self.action_cooldown > 0 {
            self.action_cooldown -= 1;
        }
        if self.move_cooldown > 0 {
            self.move_cooldown -= 1;
        }
    }
}

impl Unit<'_> {
    #[must_use]
    pub const fn vision_radius_sq(&self) -> i32 {
        match self {
            Unit::BuilderBot(_) => BUILDER_BOT_VISION_RADIUS_SQ,
            Unit::Core(_) => CORE_VISION_RADIUS_SQ,
            Unit::Gunner(_) => GUNNER_VISION_RADIUS_SQ,
            Unit::Sentinel(_) => SENTINEL_VISION_RADIUS_SQ,
            Unit::Breach(_) => BREACH_VISION_RADIUS_SQ,
            Unit::Launcher(_) => LAUNCHER_VISION_RADIUS_SQ,
        }
    }

    #[must_use]
    pub const fn action_radius_sq(&self) -> i32 {
        match self {
            Unit::Core(_) => CORE_ACTION_RADIUS_SQ,
            Unit::Launcher(_) => LAUNCHER_VISION_RADIUS_SQ,
            _ => ACTION_RADIUS_SQ,
        }
    }
}

define_category! {
    Turret : Unit [Turret] (
        Gunner,
        Sentinel,
        Breach,
        Launcher,
    ) {
        ammo_type: Option<ResourceType>,
        ammo_amount: i32,
    }
}

impl TurretBase {
    /// Gunner / Sentinel ammo loading.
    ///
    /// Titanium → load Ti ammo. Refined axionite → load axionite ammo
    /// (enables Gunner +25 dmg / Sentinel stun). Raw axionite is silently
    /// destroyed without loading.
    pub fn load_ammo_for_standard_turret(&mut self, resource: ResourceType) {
        assert!(self.ammo_amount == 0);
        match resource {
            ResourceType::Titanium => {
                self.ammo_type = Some(ResourceType::Titanium);
                self.ammo_amount = STACK_SIZE;
            }
            ResourceType::RefinedAxionite => {
                self.ammo_type = Some(ResourceType::RefinedAxionite);
                self.ammo_amount = STACK_SIZE;
            }
            ResourceType::RawAxionite => {} // destroyed
        }
    }

    /// Breach ammo loading. Only refined axionite loads as ammo; titanium
    /// and raw axionite are destroyed on receipt.
    pub fn load_ammo_for_breach(&mut self, resource: ResourceType) {
        assert!(self.ammo_amount == 0);
        match resource {
            ResourceType::RefinedAxionite => {
                self.ammo_type = Some(ResourceType::RefinedAxionite);
                self.ammo_amount = STACK_SIZE;
            }
            ResourceType::Titanium | ResourceType::RawAxionite => {} // destroyed
        }
    }
}

impl Turret<'_> {
    #[must_use]
    pub const fn vision_radius_sq(&self) -> i32 {
        match self {
            Turret::Gunner(_) => GUNNER_VISION_RADIUS_SQ,
            Turret::Sentinel(_) => SENTINEL_VISION_RADIUS_SQ,
            Turret::Breach(_) => BREACH_VISION_RADIUS_SQ,
            Turret::Launcher(_) => LAUNCHER_VISION_RADIUS_SQ,
        }
    }
}

define_category! {
    Building : Entity [Entity] (
        Conveyor,
        Splitter,
        ArmouredConveyor,
        Bridge,
        Harvester,
        Foundry,
        Road,
        Barrier,
        Marker,
        Core,
        Gunner,
        Sentinel,
        Breach,
        Launcher,
    ) {}
}

#[derive(Clone, Debug)]
pub struct Conveyor {
    pub building: BuildingBase,
    pub direction: Direction,
    pub stored: Option<ResourceType>,
    pub stored_resource_id: Option<i32>,
}
impl_derefs!(Conveyor, building);

#[derive(Clone, Debug)]
pub struct Splitter {
    pub building: BuildingBase,
    pub direction: Direction,
    pub stored: Option<ResourceType>,
    pub stored_resource_id: Option<i32>,
}
impl_derefs!(Splitter, building);

#[derive(Clone, Debug)]
pub struct Bridge {
    pub building: BuildingBase,
    pub target: Pos,
    pub stored: Option<ResourceType>,
    pub stored_resource_id: Option<i32>,
}
impl_derefs!(Bridge, building);

#[derive(Clone, Debug)]
pub struct ArmouredConveyor {
    pub building: BuildingBase,
    pub direction: Direction,
    pub stored: Option<ResourceType>,
    pub stored_resource_id: Option<i32>,
}
impl_derefs!(ArmouredConveyor, building);

#[derive(Clone, Debug)]
pub struct Harvester {
    pub building: BuildingBase,
    pub resource_type: ResourceType,
    pub cooldown: i32,
}
impl_derefs!(Harvester, building);

#[derive(Clone, Debug)]
pub struct Foundry {
    pub building: BuildingBase,
    pub stored: Option<ResourceType>,
    pub stored_resource_id: Option<i32>,
}
impl_derefs!(Foundry, building);

#[derive(Clone, Debug)]
pub struct Road {
    pub building: BuildingBase,
}
impl_derefs!(Road, building);

#[derive(Clone, Debug)]
pub struct Barrier {
    pub building: BuildingBase,
}
impl_derefs!(Barrier, building);

#[derive(Clone, Debug)]
pub struct Marker {
    pub building: BuildingBase,
    pub value: u32,
}
impl_derefs!(Marker, building);

#[derive(Clone, Debug)]
pub struct Core {
    pub unit: UnitBase,
    pub received: Vec<ResourceType>,
}
impl_derefs!(Core, unit);

#[derive(Clone, Debug)]
pub struct Gunner {
    pub turret: TurretBase,
    pub direction: Direction,
}
impl_derefs!(Gunner, turret);

#[derive(Clone, Debug)]
pub struct Sentinel {
    pub turret: TurretBase,
    pub direction: Direction,
}
impl_derefs!(Sentinel, turret);

#[derive(Clone, Debug)]
pub struct Breach {
    pub turret: TurretBase,
    pub direction: Direction,
}
impl_derefs!(Breach, turret);

#[derive(Clone, Debug)]
pub struct Launcher {
    pub turret: TurretBase,
}
impl_derefs!(Launcher, turret);

#[derive(Clone, Debug)]
pub struct BuilderBot {
    pub unit: UnitBase,
}
impl_derefs!(BuilderBot, unit);

#[derive(Clone, Debug)]
pub struct Tile {
    pub position: Pos,
    pub building: Option<i32>,
    pub builder_bot: Option<i32>,
    pub environment: Environment,
}

impl Tile {
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.building.is_none() && self.environment != Environment::Wall
    }

    #[must_use]
    pub fn is_bot_passable(&self, entities: &FxHashMap<i32, Entity>, team: Team) -> bool {
        if self.builder_bot.is_some() {
            return false;
        }
        if let Some(id) = self.building {
            let entity = entities
                .get(&id)
                .unwrap_or_else(|| panic!("tile building id missing entity {id}"));
            matches!(
                entity,
                Entity::Conveyor(_)
                    | Entity::Splitter(_)
                    | Entity::ArmouredConveyor(_)
                    | Entity::Bridge(_)
                    | Entity::Road(_)
            ) || matches!(entity, Entity::Core(_) if entity.team == team)
        } else {
            false
        }
    }
}

#[derive(Clone, Debug)]
pub struct GameMap {
    pub width: i32,
    pub height: i32,
    pub tiles: Vec<Vec<Tile>>,
}

impl GameMap {
    #[must_use]
    pub const fn in_bounds(&self, pos: Pos) -> bool {
        pos.x >= 0 && pos.x < self.width && pos.y >= 0 && pos.y < self.height
    }

    #[must_use]
    pub fn tile(&self, pos: Pos) -> &Tile {
        assert!(self.in_bounds(pos), "position out of bounds: {pos:?}");
        &self.tiles[pos.y as usize][pos.x as usize]
    }

    pub fn tile_mut(&mut self, pos: Pos) -> &mut Tile {
        assert!(self.in_bounds(pos), "position out of bounds: {pos:?}");
        &mut self.tiles[pos.y as usize][pos.x as usize]
    }

    pub fn place_building_tile(&mut self, id: i32, pos: Pos) {
        self.tile_mut(pos).building = Some(id);
    }

    pub fn build_conveyor(
        &mut self,
        id: i32,
        team: Team,
        position: Pos,
        direction: Direction,
    ) -> Conveyor {
        self.place_building_tile(id, position);
        Conveyor {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: CONVEYOR_MAX_HP,
                    max_hp: CONVEYOR_MAX_HP,
                },
            },
            direction,
            stored: None,
            stored_resource_id: None,
        }
    }

    pub fn build_splitter(
        &mut self,
        id: i32,
        team: Team,
        position: Pos,
        direction: Direction,
    ) -> Splitter {
        self.place_building_tile(id, position);
        Splitter {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: SPLITTER_MAX_HP,
                    max_hp: SPLITTER_MAX_HP,
                },
            },
            direction,
            stored: None,
            stored_resource_id: None,
        }
    }

    pub fn build_bridge(&mut self, id: i32, team: Team, position: Pos, target: Pos) -> Bridge {
        self.place_building_tile(id, position);
        Bridge {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: BRIDGE_MAX_HP,
                    max_hp: BRIDGE_MAX_HP,
                },
            },
            target,
            stored: None,
            stored_resource_id: None,
        }
    }

    pub fn build_armoured_conveyor(
        &mut self,
        id: i32,
        team: Team,
        position: Pos,
        direction: Direction,
    ) -> ArmouredConveyor {
        self.place_building_tile(id, position);
        ArmouredConveyor {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: ARMOURED_CONVEYOR_MAX_HP,
                    max_hp: ARMOURED_CONVEYOR_MAX_HP,
                },
            },
            direction,
            stored: None,
            stored_resource_id: None,
        }
    }

    pub fn build_harvester(&mut self, id: i32, team: Team, position: Pos) -> Harvester {
        self.place_building_tile(id, position);
        let resource_type = match self.tile(position).environment {
            Environment::OreTitanium => ResourceType::Titanium,
            Environment::OreAxionite => ResourceType::RawAxionite,
            env => panic!("build_harvester called on non-ore tile {position:?}: {env:?}"),
        };
        Harvester {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: HARVESTER_MAX_HP,
                    max_hp: HARVESTER_MAX_HP,
                },
            },
            resource_type,
            cooldown: 0,
        }
    }

    pub fn build_road(&mut self, id: i32, team: Team, position: Pos) -> Road {
        self.place_building_tile(id, position);
        Road {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: ROAD_MAX_HP,
                    max_hp: ROAD_MAX_HP,
                },
            },
        }
    }

    pub fn build_barrier(&mut self, id: i32, team: Team, position: Pos) -> Barrier {
        self.place_building_tile(id, position);
        Barrier {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: BARRIER_MAX_HP,
                    max_hp: BARRIER_MAX_HP,
                },
            },
        }
    }

    pub fn build_gunner(
        &mut self,
        id: i32,
        team: Team,
        position: Pos,
        direction: Direction,
    ) -> Gunner {
        self.place_building_tile(id, position);
        Gunner {
            turret: TurretBase {
                unit: UnitBase {
                    entity: EntityBase {
                        id,
                        team,
                        position,
                        hp: GUNNER_MAX_HP,
                        max_hp: GUNNER_MAX_HP,
                    },
                    action_cooldown: 0,
                    move_cooldown: 0,
                },
                ammo_type: None,
                ammo_amount: 0,
            },
            direction,
        }
    }

    pub fn build_sentinel(
        &mut self,
        id: i32,
        team: Team,
        position: Pos,
        direction: Direction,
    ) -> Sentinel {
        self.place_building_tile(id, position);
        Sentinel {
            turret: TurretBase {
                unit: UnitBase {
                    entity: EntityBase {
                        id,
                        team,
                        position,
                        hp: SENTINEL_MAX_HP,
                        max_hp: SENTINEL_MAX_HP,
                    },
                    action_cooldown: 0,
                    move_cooldown: 0,
                },
                ammo_type: None,
                ammo_amount: 0,
            },
            direction,
        }
    }

    pub fn build_breach(
        &mut self,
        id: i32,
        team: Team,
        position: Pos,
        direction: Direction,
    ) -> Breach {
        self.place_building_tile(id, position);
        Breach {
            turret: TurretBase {
                unit: UnitBase {
                    entity: EntityBase {
                        id,
                        team,
                        position,
                        hp: BREACH_MAX_HP,
                        max_hp: BREACH_MAX_HP,
                    },
                    action_cooldown: 0,
                    move_cooldown: 0,
                },
                ammo_type: None,
                ammo_amount: 0,
            },
            direction,
        }
    }

    pub fn build_launcher(&mut self, id: i32, team: Team, position: Pos) -> Launcher {
        self.place_building_tile(id, position);
        Launcher {
            turret: TurretBase {
                unit: UnitBase {
                    entity: EntityBase {
                        id,
                        team,
                        position,
                        hp: LAUNCHER_MAX_HP,
                        max_hp: LAUNCHER_MAX_HP,
                    },
                    action_cooldown: 0,
                    move_cooldown: 0,
                },
                ammo_type: None,
                ammo_amount: 0,
            },
        }
    }

    pub fn build_foundry(&mut self, id: i32, team: Team, position: Pos) -> Foundry {
        self.place_building_tile(id, position);
        Foundry {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: FOUNDRY_MAX_HP,
                    max_hp: FOUNDRY_MAX_HP,
                },
            },
            stored: None,
            stored_resource_id: None,
        }
    }

    pub fn build_marker(&mut self, id: i32, team: Team, position: Pos, value: u32) -> Marker {
        self.place_building_tile(id, position);
        Marker {
            building: BuildingBase {
                entity: EntityBase {
                    id,
                    team,
                    position,
                    hp: MARKER_MAX_HP,
                    max_hp: MARKER_MAX_HP,
                },
            },
            value,
        }
    }
}

#[derive(Clone, Debug)]
pub struct PlayerState {
    pub titanium: i32,
    pub axionite: i32,
    pub titanium_collected: i32,
    pub axionite_collected: i32,
    pub scale_milli: i32,
}

impl PlayerState {
    #[must_use]
    pub const fn can_afford(&self, cost: (i32, i32)) -> bool {
        self.titanium >= cost.0 && self.axionite >= cost.1
    }

    pub const fn spend(&mut self, cost: (i32, i32)) {
        self.titanium -= cost.0;
        self.axionite -= cost.1;
    }

    pub const fn add_resource(&mut self, resource: ResourceType) {
        match resource {
            ResourceType::Titanium => {
                self.titanium += STACK_SIZE;
                self.titanium_collected += STACK_SIZE;
            }
            // Raw axionite delivered to the core is destroyed (must be
            // refined first via a foundry to survive). See docs/spec/core.md
            // and docs/spec/resources.md.
            ResourceType::RawAxionite => {}
            ResourceType::RefinedAxionite => {
                self.axionite += STACK_SIZE;
                self.axionite_collected += STACK_SIZE;
            }
        }
    }
}
