//! The canonical Rust controller surface — the API a bot (Python or
//! native Rust) sees as `c` in `Player::run(c)`.
//!
//! `Controller` is the trait pyrust mirrors into Python codegen.
//! `UnitView<'a>` is the canonical impl over a borrowed `Game`. The
//! PyO3 `Controller` class in the `libre` binary wraps a
//! `Rc<RefCell<Game>>` and delegates each method to a fresh
//! `UnitView` constructed from a `&mut Game` borrow. Native Rust bots
//! receive `&mut UnitView` directly via the `Player` trait, no Python.
//!
//! Every method that mutates game state takes `&mut self`. Errors that
//! bots can recover from are `GameError`; engine invariants violated
//! (impossible-without-corruption) are `panic!` as in Python.

use crate::common::game_constants::{
    ACTION_RADIUS_SQ, ARMOURED_CONVEYOR_BASE_COST, AXIONITE_CONVERSION_TITANIUM_RATE,
    BARRIER_BASE_COST, BREACH_ATTACK_RADIUS_SQ, BREACH_BASE_COST, BRIDGE_BASE_COST,
    BRIDGE_TARGET_RADIUS_SQ, BUILDER_BOT_ATTACK_COST, BUILDER_BOT_ATTACK_DAMAGE,
    BUILDER_BOT_BASE_COST, BUILDER_BOT_HEAL_COST, BUILDER_BOT_SELF_DESTRUCT_DAMAGE,
    CONVEYOR_BASE_COST, CORE_SPAWNING_RADIUS_SQ, FOUNDRY_BASE_COST, GUNNER_BASE_COST,
    GUNNER_ROTATE_COOLDOWN, GUNNER_ROTATE_COST, GUNNER_VISION_RADIUS_SQ, HARVESTER_BASE_COST,
    LAUNCHER_BASE_COST, LAUNCHER_VISION_RADIUS_SQ, MAX_TEAM_UNITS, ROAD_BASE_COST,
    SENTINEL_BASE_COST, SENTINEL_VISION_RADIUS_SQ, SPLITTER_BASE_COST,
};
use crate::common::{Direction, EntityType, Environment, Pos, ResourceType, Team};
use crate::game::Game;
use crate::game_map::{Entity, Turret};
use crate::replay_diff::GameDiff;

/// Recoverable bot-facing error. Mirrors the Python `cambc.GameError`
/// — anything raised by a `c.foo(...)` call that a bot may catch.
#[derive(Debug, Clone)]
pub struct GameError(pub String);

impl std::fmt::Display for GameError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for GameError {}

impl GameError {
    pub fn new(msg: impl Into<String>) -> Self {
        Self(msg.into())
    }
}

pub type Result<T> = std::result::Result<T, GameError>;

/// The `c` object from a bot's perspective.
///
/// Method names match the Python `cambc.Controller` 1:1 except where
/// Rust syntax forces a rename:
/// - Python `c.move(d)`  → Rust `c.move_(d)`  (`move` is a keyword)
/// - Python `c.fire(t)`  → Rust `c.fire(t)`   (no rename)
/// - Python `c.build(t, p, extra)` → Rust `c.build(t, p, extra)` with
///   `extra: BuildExtra` (an enum, not the Python `Direction|Position|None`)
pub trait Controller {
    fn get_team(&self, id: Option<i32>) -> Result<Team>;
    fn get_position(&self, id: Option<i32>) -> Result<Pos>;
    fn get_id(&self) -> Result<i32>;
    fn get_action_cooldown(&self) -> Result<i32>;
    fn get_move_cooldown(&self) -> Result<i32>;
    fn get_hp(&self, id: Option<i32>) -> Result<i32>;
    fn get_max_hp(&self, id: Option<i32>) -> Result<i32>;
    fn get_entity_type(&self, id: Option<i32>) -> Result<EntityType>;
    fn get_direction(&self, id: Option<i32>) -> Result<Direction>;
    fn get_vision_radius_sq(&self, id: Option<i32>) -> Result<i32>;

    fn get_ammo_amount(&self) -> Result<i32>;
    fn get_ammo_type(&self) -> Result<Option<ResourceType>>;
    fn get_gunner_target(&self) -> Result<Option<Pos>>;
    fn get_attackable_tiles(&self) -> Result<Vec<Pos>>;
    fn get_attackable_tiles_from(
        &self,
        position: Pos,
        direction: Direction,
        turret_type: EntityType,
    ) -> Result<Vec<Pos>>;

    fn get_bridge_target(&self, id: i32) -> Result<Pos>;
    fn get_stored_resource(&self, id: Option<i32>) -> Result<Option<ResourceType>>;
    fn get_stored_resource_id(&self, id: Option<i32>) -> Result<Option<i32>>;

    fn get_tile_env(&self, pos: Pos) -> Result<Environment>;
    fn get_tile_building_id(&self, pos: Pos) -> Result<Option<i32>>;
    fn get_tile_builder_bot_id(&self, pos: Pos) -> Result<Option<i32>>;
    fn is_tile_empty(&self, pos: Pos) -> Result<bool>;
    fn is_tile_passable(&self, pos: Pos) -> Result<bool>;
    fn is_in_vision(&self, pos: Pos) -> Result<bool>;

    fn get_nearby_tiles(&self, dist_sq: Option<i32>) -> Result<Vec<Pos>>;
    fn get_nearby_entities(&self, dist_sq: Option<i32>) -> Result<Vec<i32>>;
    fn get_nearby_buildings(&self, dist_sq: Option<i32>) -> Result<Vec<i32>>;
    fn get_nearby_units(&self, dist_sq: Option<i32>) -> Result<Vec<i32>>;

    fn get_map_width(&self) -> Result<i32>;
    fn get_map_height(&self) -> Result<i32>;
    fn get_current_round(&self) -> Result<i32>;
    fn get_global_resources(&self) -> Result<(i32, i32)>;
    fn get_scale_percent(&self) -> Result<f64>;
    fn get_unit_count(&self) -> Result<i32>;
    fn get_cpu_time_elapsed(&self) -> Result<u64>;

    fn get_conveyor_cost(&self) -> Result<(i32, i32)>;
    fn get_splitter_cost(&self) -> Result<(i32, i32)>;
    fn get_bridge_cost(&self) -> Result<(i32, i32)>;
    fn get_armoured_conveyor_cost(&self) -> Result<(i32, i32)>;
    fn get_harvester_cost(&self) -> Result<(i32, i32)>;
    fn get_road_cost(&self) -> Result<(i32, i32)>;
    fn get_barrier_cost(&self) -> Result<(i32, i32)>;
    fn get_gunner_cost(&self) -> Result<(i32, i32)>;
    fn get_sentinel_cost(&self) -> Result<(i32, i32)>;
    fn get_breach_cost(&self) -> Result<(i32, i32)>;
    fn get_launcher_cost(&self) -> Result<(i32, i32)>;
    fn get_foundry_cost(&self) -> Result<(i32, i32)>;
    fn get_builder_bot_cost(&self) -> Result<(i32, i32)>;

    fn move_(&mut self, direction: Direction) -> Result<()>;
    fn can_move(&self, direction: Direction) -> Result<bool>;

    fn can_build_conveyor(&self, position: Pos, direction: Direction) -> Result<bool>;
    fn can_build_splitter(&self, position: Pos, direction: Direction) -> Result<bool>;
    fn can_build_bridge(&self, position: Pos, target: Pos) -> Result<bool>;
    fn can_build_armoured_conveyor(&self, position: Pos, direction: Direction) -> Result<bool>;
    fn can_build_harvester(&self, position: Pos) -> Result<bool>;
    fn can_build_road(&self, position: Pos) -> Result<bool>;
    fn can_build_barrier(&self, position: Pos) -> Result<bool>;
    fn can_build_gunner(&self, position: Pos, direction: Direction) -> Result<bool>;
    fn can_build_sentinel(&self, position: Pos, direction: Direction) -> Result<bool>;
    fn can_build_breach(&self, position: Pos, direction: Direction) -> Result<bool>;
    fn can_build_launcher(&self, position: Pos) -> Result<bool>;
    fn can_build_foundry(&self, position: Pos) -> Result<bool>;

    fn build_conveyor(&mut self, position: Pos, direction: Direction) -> Result<i32>;
    fn build_splitter(&mut self, position: Pos, direction: Direction) -> Result<i32>;
    fn build_bridge(&mut self, position: Pos, target: Pos) -> Result<i32>;
    fn build_armoured_conveyor(&mut self, position: Pos, direction: Direction) -> Result<i32>;
    fn build_harvester(&mut self, position: Pos) -> Result<i32>;
    fn build_road(&mut self, position: Pos) -> Result<i32>;
    fn build_barrier(&mut self, position: Pos) -> Result<i32>;
    fn build_gunner(&mut self, position: Pos, direction: Direction) -> Result<i32>;
    fn build_sentinel(&mut self, position: Pos, direction: Direction) -> Result<i32>;
    fn build_breach(&mut self, position: Pos, direction: Direction) -> Result<i32>;
    fn build_launcher(&mut self, position: Pos) -> Result<i32>;
    fn build_foundry(&mut self, position: Pos) -> Result<i32>;

    fn can_build(&self, entity_type: EntityType, position: Pos, extra: BuildExtra) -> Result<bool>;
    fn build(&mut self, entity_type: EntityType, position: Pos, extra: BuildExtra) -> Result<i32>;

    fn can_destroy(&self, building_pos: Pos) -> Result<bool>;
    fn destroy(&mut self, building_pos: Pos) -> Result<()>;
    fn heal(&mut self, position: Pos) -> Result<()>;
    fn can_heal(&self, position: Pos) -> Result<bool>;
    fn self_destruct(&mut self) -> Result<()>;
    fn resign(&mut self, message: Option<String>) -> Result<()>;

    fn can_place_marker(&self, position: Pos) -> Result<bool>;
    fn place_marker(&mut self, position: Pos, value: u32) -> Result<()>;
    fn get_marker_value(&self, id: i32) -> Result<u32>;

    fn can_fire(&self, target: Pos) -> Result<bool>;
    fn can_fire_from(
        &self,
        position: Pos,
        direction: Direction,
        turret_type: EntityType,
        target: Pos,
    ) -> Result<bool>;
    fn fire(&mut self, target: Pos) -> Result<()>;
    fn can_rotate(&self, direction: Direction) -> Result<bool>;
    fn rotate(&mut self, direction: Direction) -> Result<()>;
    fn can_launch(&self, bot_pos: Pos, target: Pos) -> Result<bool>;
    fn launch(&mut self, bot_pos: Pos, target: Pos) -> Result<()>;

    fn convert(&mut self, amount: i32) -> Result<()>;
    fn spawn_builder(&mut self, position: Pos) -> Result<i32>;
    fn can_spawn(&self, position: Pos) -> Result<bool>;

    fn draw_indicator_line(&mut self, pos_a: Pos, pos_b: Pos, r: i32, g: i32, b: i32)
    -> Result<()>;
    fn draw_indicator_dot(&mut self, pos: Pos, r: i32, g: i32, b: i32) -> Result<()>;
}

/// Polymorphic third argument to `c.build` / `c.can_build`.
///
/// Mirrors the Python `Direction | Position | None` of the generic
/// dispatch — Rust prefers a tagged enum over `dyn Any`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BuildExtra {
    None,
    Direction(Direction),
    Position(Pos),
}

/// A unit's view onto a `Game`. Holds a mutable borrow plus the
/// per-turn `has_placed_marker` flag used by `can_place_marker` /
/// `place_marker`. Per-turn lifecycle: construct one at the start of
/// the unit's turn (resets `has_placed_marker`), pass to the bot, drop
/// at end of turn.
pub struct UnitView<'a> {
    pub game: &'a mut Game,
    pub unit: i32,
    pub has_placed_marker: bool,
}

impl<'a> UnitView<'a> {
    pub fn new(game: &'a mut Game, unit: i32) -> Self {
        Self {
            game,
            unit,
            has_placed_marker: false,
        }
    }

    fn assert_in_vision(&self, pos: Pos) -> Result<()> {
        if self.is_in_vision_inner(pos) {
            Ok(())
        } else {
            Err(GameError::new("Position out of vision range"))
        }
    }

    fn is_in_vision_inner(&self, pos: Pos) -> bool {
        let Some(entity) = self.game.entities.get(&self.unit) else {
            return false;
        };
        let Some(unit) = entity.as_unit() else {
            return false;
        };
        unit.position.distance_squared(pos) <= unit.vision_radius_sq()
    }

    fn assert_entity_in_vision(&self, target_id: i32) -> Result<()> {
        let entity = self
            .game
            .entity(target_id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let centre = entity.position;
        // The core occupies a 3x3 area; it counts as in-vision if any of its
        // 9 tiles is within range.
        if matches!(entity, Entity::Core(_)) {
            use Direction::*;
            let in_vision = [
                North, Northeast, East, Southeast, South, Southwest, West, Northwest, Centre,
            ]
            .iter()
            .any(|d| self.is_in_vision_inner(centre + *d));
            if in_vision {
                Ok(())
            } else {
                Err(GameError::new("Entity out of vision range"))
            }
        } else {
            self.assert_in_vision(centre)
        }
    }

    fn can_build_checks(&self, position: Pos, base_cost: (i32, i32)) -> bool {
        let bot = match self.game.entity(self.unit) {
            Some(Entity::BuilderBot(bot)) => bot,
            _ => return false,
        };
        if !bot.can_act() {
            return false;
        }
        if bot.position.distance_squared(position) > ACTION_RADIUS_SQ {
            return false;
        }
        if !self.game.game_map.in_bounds(position) {
            return false;
        }
        let tile = self.game.game_map.tile(position);
        if tile.environment == Environment::Wall {
            return false;
        }
        if let Some(existing_id) = tile.building {
            if !matches!(self.game.entity(existing_id), Some(Entity::Marker(_))) {
                return false;
            }
        }
        let cost = self.game.scaled_cost(bot.team, base_cost);
        self.game.players[bot.team.index()].can_afford(cost)
    }

    fn team_has_unit_capacity(&self) -> Result<bool> {
        let team = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown unit"))?
            .team;
        Ok(self.game.unit_count(team) < MAX_TEAM_UNITS)
    }

    fn compute_attackable_tiles_pattern(
        &self,
        origin: Pos,
        dir: Direction,
        turret_type: EntityType,
    ) -> Vec<Pos> {
        let mut out = Vec::new();
        if !self.game.game_map.in_bounds(origin) {
            return out;
        }
        match turret_type {
            EntityType::Gunner => {
                let mut pos = origin + dir;
                while self.game.game_map.in_bounds(pos)
                    && origin.distance_squared(pos) <= GUNNER_VISION_RADIUS_SQ
                {
                    out.push(pos);
                    pos = pos + dir;
                }
            }
            EntityType::Sentinel => {
                let r = (SENTINEL_VISION_RADIUS_SQ as f64).sqrt().ceil() as i32;
                let (dx, dy) = dir.delta();
                for cy in -r..=r {
                    for cx in -r..=r {
                        let p = Pos {
                            x: origin.x + cx,
                            y: origin.y + cy,
                        };
                        let dsq = origin.distance_squared(p);
                        if dsq == 0 || dsq > SENTINEL_VISION_RADIUS_SQ {
                            continue;
                        }
                        let mut k = 1;
                        let mut hit = false;
                        while k * k * (dx * dx + dy * dy) <= SENTINEL_VISION_RADIUS_SQ {
                            let lx = cx - k * dx;
                            let ly = cy - k * dy;
                            if lx.abs() <= 1 && ly.abs() <= 1 {
                                hit = true;
                                break;
                            }
                            k += 1;
                        }
                        if hit && self.game.game_map.in_bounds(p) {
                            out.push(p);
                        }
                    }
                }
            }
            EntityType::Breach => {
                let r = (BREACH_ATTACK_RADIUS_SQ as f64).sqrt().ceil() as i32;
                let (dx, dy) = dir.delta();
                for cy in -r..=r {
                    for cx in -r..=r {
                        let dsq = cx * cx + cy * cy;
                        if dsq == 0 || dsq > BREACH_ATTACK_RADIUS_SQ {
                            continue;
                        }
                        let dot = cx * dx + cy * dy;
                        if dot < 0 {
                            continue;
                        }
                        let p = Pos {
                            x: origin.x + cx,
                            y: origin.y + cy,
                        };
                        if self.game.game_map.in_bounds(p) {
                            out.push(p);
                        }
                    }
                }
            }
            EntityType::Launcher => {
                let r = (LAUNCHER_VISION_RADIUS_SQ as f64).sqrt().ceil() as i32;
                for cy in -r..=r {
                    for cx in -r..=r {
                        let dsq = cx * cx + cy * cy;
                        if dsq == 0 || dsq > LAUNCHER_VISION_RADIUS_SQ {
                            continue;
                        }
                        let p = Pos {
                            x: origin.x + cx,
                            y: origin.y + cy,
                        };
                        if self.game.game_map.in_bounds(p) {
                            out.push(p);
                        }
                    }
                }
            }
            _ => {}
        }
        out
    }
}

impl Controller for UnitView<'_> {
    fn get_team(&self, id: Option<i32>) -> Result<Team> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        Ok(self
            .game
            .entity(id)
            .ok_or_else(|| GameError::new("Unknown id"))?
            .team)
    }

    fn get_position(&self, id: Option<i32>) -> Result<Pos> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        Ok(self
            .game
            .entity(id)
            .ok_or_else(|| GameError::new("Unknown id"))?
            .position)
    }

    fn get_id(&self) -> Result<i32> {
        Ok(self.unit)
    }

    fn get_action_cooldown(&self) -> Result<i32> {
        let entity = self
            .game
            .entities
            .get(&self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let unit = entity
            .as_unit()
            .ok_or_else(|| GameError::new("Unit is not a unit"))?;
        Ok(unit.action_cooldown)
    }

    fn get_move_cooldown(&self) -> Result<i32> {
        let entity = self
            .game
            .entities
            .get(&self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let unit = entity
            .as_unit()
            .ok_or_else(|| GameError::new("Unit is not a unit"))?;
        Ok(unit.move_cooldown)
    }

    fn get_ammo_amount(&self) -> Result<i32> {
        let entity = self
            .game
            .entities
            .get(&self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let turret = entity
            .as_turret()
            .ok_or_else(|| GameError::new("Unit is not a turret"))?;
        Ok(turret.ammo_amount)
    }

    fn get_ammo_type(&self) -> Result<Option<ResourceType>> {
        let entity = self
            .game
            .entities
            .get(&self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let turret = entity
            .as_turret()
            .ok_or_else(|| GameError::new("Unit is not a turret"))?;
        Ok(turret.ammo_type)
    }

    fn get_vision_radius_sq(&self, id: Option<i32>) -> Result<i32> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        let entity = self
            .game
            .entity(id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let unit = entity
            .as_unit()
            .ok_or_else(|| GameError::new("Unit is not a unit"))?;
        Ok(unit.vision_radius_sq())
    }

    fn get_hp(&self, id: Option<i32>) -> Result<i32> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        Ok(self
            .game
            .entity(id)
            .ok_or_else(|| GameError::new("Unknown id"))?
            .hp)
    }

    fn get_max_hp(&self, id: Option<i32>) -> Result<i32> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        Ok(self
            .game
            .entity(id)
            .ok_or_else(|| GameError::new("Unknown id"))?
            .max_hp)
    }

    fn get_entity_type(&self, id: Option<i32>) -> Result<EntityType> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        let entity = self
            .game
            .entity(id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        Ok(match entity {
            Entity::BuilderBot(_) => EntityType::BuilderBot,
            Entity::Conveyor(_) => EntityType::Conveyor,
            Entity::Splitter(_) => EntityType::Splitter,
            Entity::ArmouredConveyor(_) => EntityType::ArmouredConveyor,
            Entity::Bridge(_) => EntityType::Bridge,
            Entity::Harvester(_) => EntityType::Harvester,
            Entity::Foundry(_) => EntityType::Foundry,
            Entity::Road(_) => EntityType::Road,
            Entity::Barrier(_) => EntityType::Barrier,
            Entity::Marker(_) => EntityType::Marker,
            Entity::Core(_) => EntityType::Core,
            Entity::Gunner(_) => EntityType::Gunner,
            Entity::Sentinel(_) => EntityType::Sentinel,
            Entity::Breach(_) => EntityType::Breach,
            Entity::Launcher(_) => EntityType::Launcher,
        })
    }

    fn get_direction(&self, id: Option<i32>) -> Result<Direction> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        let entity = self
            .game
            .entities
            .get(&id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        match entity {
            Entity::Conveyor(c) => Ok(c.direction),
            Entity::Splitter(s) => Ok(s.direction),
            Entity::ArmouredConveyor(c) => Ok(c.direction),
            Entity::Gunner(t) => Ok(t.direction),
            Entity::Sentinel(t) => Ok(t.direction),
            Entity::Breach(t) => Ok(t.direction),
            _ => Err(GameError::new("Entity has no direction")),
        }
    }

    fn get_bridge_target(&self, id: i32) -> Result<Pos> {
        self.assert_entity_in_vision(id)?;
        let entity = self
            .game
            .entities
            .get(&id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        match entity {
            Entity::Bridge(b) => Ok(b.target),
            _ => Err(GameError::new("Entity is not a bridge")),
        }
    }

    fn get_stored_resource(&self, id: Option<i32>) -> Result<Option<ResourceType>> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        let entity = self
            .game
            .entities
            .get(&id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        match entity {
            Entity::Conveyor(c) => Ok(c.stored),
            Entity::Splitter(s) => Ok(s.stored),
            Entity::ArmouredConveyor(c) => Ok(c.stored),
            Entity::Bridge(b) => Ok(b.stored),
            Entity::Foundry(f) => Ok(f.stored),
            _ => Err(GameError::new("Entity has no stored resource")),
        }
    }

    fn get_stored_resource_id(&self, id: Option<i32>) -> Result<Option<i32>> {
        let id = id.unwrap_or(self.unit);
        self.assert_entity_in_vision(id)?;
        let entity = self
            .game
            .entities
            .get(&id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        match entity {
            Entity::Conveyor(c) => Ok(c.stored_resource_id),
            Entity::Splitter(s) => Ok(s.stored_resource_id),
            Entity::ArmouredConveyor(c) => Ok(c.stored_resource_id),
            Entity::Bridge(b) => Ok(b.stored_resource_id),
            Entity::Foundry(f) => Ok(f.stored_resource_id),
            _ => Err(GameError::new("Entity has no stored resource")),
        }
    }

    fn get_tile_env(&self, pos: Pos) -> Result<Environment> {
        self.assert_in_vision(pos)?;
        if !self.game.game_map.in_bounds(pos) {
            return Err(GameError::new("Position out of bounds"));
        }
        Ok(self.game.game_map.tile(pos).environment)
    }

    fn get_tile_building_id(&self, pos: Pos) -> Result<Option<i32>> {
        self.assert_in_vision(pos)?;
        if !self.game.game_map.in_bounds(pos) {
            return Err(GameError::new("Position out of bounds"));
        }
        Ok(self.game.game_map.tile(pos).building)
    }

    fn get_tile_builder_bot_id(&self, pos: Pos) -> Result<Option<i32>> {
        self.assert_in_vision(pos)?;
        if !self.game.game_map.in_bounds(pos) {
            return Err(GameError::new("Position out of bounds"));
        }
        Ok(self.game.game_map.tile(pos).builder_bot)
    }

    fn is_tile_empty(&self, pos: Pos) -> Result<bool> {
        self.assert_in_vision(pos)?;
        if !self.game.game_map.in_bounds(pos) {
            return Err(GameError::new("Position out of bounds"));
        }
        Ok(self.game.game_map.tile(pos).is_empty())
    }

    fn is_tile_passable(&self, pos: Pos) -> Result<bool> {
        self.assert_in_vision(pos)?;
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.is_tile_bot_passable(pos, team))
    }

    fn is_in_vision(&self, pos: Pos) -> Result<bool> {
        let entity = self
            .game
            .entities
            .get(&self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let unit = entity
            .as_unit()
            .ok_or_else(|| GameError::new("Unit is not a unit"))?;
        Ok(unit.position.distance_squared(pos) <= unit.vision_radius_sq())
    }

    fn get_map_width(&self) -> Result<i32> {
        Ok(self.game.game_map.width)
    }

    fn get_map_height(&self) -> Result<i32> {
        Ok(self.game.game_map.height)
    }

    fn get_current_round(&self) -> Result<i32> {
        Ok(self.game.turn)
    }

    fn get_cpu_time_elapsed(&self) -> Result<u64> {
        // Native bots don't run under the per-thread CPU watchdog;
        // always report 0. The PyO3 wrapper overrides this in its own
        // adapter to read the actual deadline state.
        Ok(0)
    }

    fn get_global_resources(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        let player = &self.game.players[team.index()];
        Ok((player.titanium, player.axionite))
    }

    fn get_scale_percent(&self) -> Result<f64> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.players[team.index()].scale_milli as f64 / 10.0)
    }

    fn get_unit_count(&self) -> Result<i32> {
        let team = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown unit"))?
            .team;
        Ok(self.game.unit_count(team))
    }

    fn get_conveyor_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, CONVEYOR_BASE_COST))
    }

    fn get_splitter_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, SPLITTER_BASE_COST))
    }

    fn get_bridge_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, BRIDGE_BASE_COST))
    }

    fn get_armoured_conveyor_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, ARMOURED_CONVEYOR_BASE_COST))
    }

    fn get_harvester_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, HARVESTER_BASE_COST))
    }

    fn get_road_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, ROAD_BASE_COST))
    }

    fn get_barrier_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, BARRIER_BASE_COST))
    }

    fn get_gunner_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, GUNNER_BASE_COST))
    }

    fn get_sentinel_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, SENTINEL_BASE_COST))
    }

    fn get_breach_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, BREACH_BASE_COST))
    }

    fn get_launcher_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, LAUNCHER_BASE_COST))
    }

    fn get_foundry_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, FOUNDRY_BASE_COST))
    }

    fn get_builder_bot_cost(&self) -> Result<(i32, i32)> {
        let team = self.game.entity(self.unit).expect("unknown unit").team;
        Ok(self.game.scaled_cost(team, BUILDER_BOT_BASE_COST))
    }

    fn move_(&mut self, direction: Direction) -> Result<()> {
        if !self.can_move(direction)? {
            return Err(GameError::new("Cannot move"));
        }
        let bot = match self.game.entity(self.unit) {
            Some(Entity::BuilderBot(bot)) => bot,
            _ => return Err(GameError::new("Unit is not a builder bot")),
        };
        let to_pos = bot.position + direction;
        let bot_id = bot.id;
        self.game.move_builder_bot(bot_id, to_pos);
        Ok(())
    }

    fn can_move(&self, direction: Direction) -> Result<bool> {
        let bot = match self.game.entity(self.unit) {
            Some(Entity::BuilderBot(bot)) => bot,
            _ => return Ok(false),
        };
        if !bot.can_move() {
            return Ok(false);
        }
        let to_pos = bot.position + direction;
        Ok(self.game.is_tile_bot_passable(to_pos, bot.team))
    }

    fn can_build_conveyor(&self, position: Pos, direction: Direction) -> Result<bool> {
        if !direction.is_cardinal() {
            return Ok(false);
        }
        Ok(self.can_build_checks(position, CONVEYOR_BASE_COST))
    }

    fn can_build_splitter(&self, position: Pos, direction: Direction) -> Result<bool> {
        if !direction.is_cardinal() {
            return Ok(false);
        }
        Ok(self.can_build_checks(position, SPLITTER_BASE_COST))
    }

    fn can_build_bridge(&self, position: Pos, target: Pos) -> Result<bool> {
        if !self.can_build_checks(position, BRIDGE_BASE_COST) {
            return Ok(false);
        }
        if !self.game.game_map.in_bounds(target) {
            return Ok(false);
        }
        let dist_sq = position.distance_squared(target);
        Ok(dist_sq > 0 && dist_sq <= BRIDGE_TARGET_RADIUS_SQ)
    }

    fn can_build_armoured_conveyor(&self, position: Pos, direction: Direction) -> Result<bool> {
        if !direction.is_cardinal() {
            return Ok(false);
        }
        Ok(self.can_build_checks(position, ARMOURED_CONVEYOR_BASE_COST))
    }

    fn can_build_harvester(&self, position: Pos) -> Result<bool> {
        if !self.can_build_checks(position, HARVESTER_BASE_COST) {
            return Ok(false);
        }
        if self.game.game_map.tile(position).builder_bot.is_some() {
            return Ok(false);
        }
        Ok(matches!(
            self.game.game_map.tile(position).environment,
            Environment::OreTitanium | Environment::OreAxionite
        ))
    }

    fn can_build_road(&self, position: Pos) -> Result<bool> {
        Ok(self.can_build_checks(position, ROAD_BASE_COST))
    }

    fn can_build_barrier(&self, position: Pos) -> Result<bool> {
        if !self.can_build_checks(position, BARRIER_BASE_COST) {
            return Ok(false);
        }
        Ok(self.game.game_map.tile(position).builder_bot.is_none())
    }

    fn can_build_gunner(&self, position: Pos, direction: Direction) -> Result<bool> {
        if !direction.is_directional() {
            return Ok(false);
        }
        if !self.can_build_checks(position, GUNNER_BASE_COST) {
            return Ok(false);
        }
        if !self.team_has_unit_capacity()? {
            return Ok(false);
        }
        Ok(self.game.game_map.tile(position).builder_bot.is_none())
    }

    fn can_build_sentinel(&self, position: Pos, direction: Direction) -> Result<bool> {
        if !direction.is_directional() {
            return Ok(false);
        }
        if !self.can_build_checks(position, SENTINEL_BASE_COST) {
            return Ok(false);
        }
        if !self.team_has_unit_capacity()? {
            return Ok(false);
        }
        Ok(self.game.game_map.tile(position).builder_bot.is_none())
    }

    fn can_build_breach(&self, position: Pos, direction: Direction) -> Result<bool> {
        if !direction.is_directional() {
            return Ok(false);
        }
        if !self.can_build_checks(position, BREACH_BASE_COST) {
            return Ok(false);
        }
        if !self.team_has_unit_capacity()? {
            return Ok(false);
        }
        Ok(self.game.game_map.tile(position).builder_bot.is_none())
    }

    fn can_build_launcher(&self, position: Pos) -> Result<bool> {
        if !self.can_build_checks(position, LAUNCHER_BASE_COST) {
            return Ok(false);
        }
        if !self.team_has_unit_capacity()? {
            return Ok(false);
        }
        Ok(self.game.game_map.tile(position).builder_bot.is_none())
    }

    fn can_build_foundry(&self, position: Pos) -> Result<bool> {
        if !self.can_build_checks(position, FOUNDRY_BASE_COST) {
            return Ok(false);
        }
        Ok(self.game.game_map.tile(position).builder_bot.is_none())
    }

    fn build_conveyor(&mut self, position: Pos, direction: Direction) -> Result<i32> {
        if !self.can_build_conveyor(position, direction)? {
            return Err(GameError::new("Cannot build conveyor"));
        }
        Ok(self.game.build_conveyor(self.unit, position, direction))
    }

    fn build_splitter(&mut self, position: Pos, direction: Direction) -> Result<i32> {
        if !self.can_build_splitter(position, direction)? {
            return Err(GameError::new("Cannot build splitter"));
        }
        Ok(self.game.build_splitter(self.unit, position, direction))
    }

    fn build_bridge(&mut self, position: Pos, target: Pos) -> Result<i32> {
        if !self.can_build_bridge(position, target)? {
            return Err(GameError::new("Cannot build bridge"));
        }
        Ok(self.game.build_bridge(self.unit, position, target))
    }

    fn build_armoured_conveyor(&mut self, position: Pos, direction: Direction) -> Result<i32> {
        if !self.can_build_armoured_conveyor(position, direction)? {
            return Err(GameError::new("Cannot build armoured conveyor"));
        }
        Ok(self
            .game
            .build_armoured_conveyor(self.unit, position, direction))
    }

    fn build_harvester(&mut self, position: Pos) -> Result<i32> {
        if !self.can_build_harvester(position)? {
            return Err(GameError::new("Cannot build harvester"));
        }
        Ok(self.game.build_harvester(self.unit, position))
    }

    fn build_road(&mut self, position: Pos) -> Result<i32> {
        if !self.can_build_road(position)? {
            return Err(GameError::new("Cannot build road"));
        }
        Ok(self.game.build_road(self.unit, position))
    }

    fn build_barrier(&mut self, position: Pos) -> Result<i32> {
        if !self.can_build_barrier(position)? {
            return Err(GameError::new("Cannot build barrier"));
        }
        Ok(self.game.build_barrier(self.unit, position))
    }

    fn build_gunner(&mut self, position: Pos, direction: Direction) -> Result<i32> {
        if !self.can_build_gunner(position, direction)? {
            return Err(GameError::new("Cannot build gunner"));
        }
        Ok(self.game.build_gunner(self.unit, position, direction))
    }

    fn build_sentinel(&mut self, position: Pos, direction: Direction) -> Result<i32> {
        if !self.can_build_sentinel(position, direction)? {
            return Err(GameError::new("Cannot build sentinel"));
        }
        Ok(self.game.build_sentinel(self.unit, position, direction))
    }

    fn build_breach(&mut self, position: Pos, direction: Direction) -> Result<i32> {
        if !self.can_build_breach(position, direction)? {
            return Err(GameError::new("Cannot build breach"));
        }
        Ok(self.game.build_breach(self.unit, position, direction))
    }

    fn build_launcher(&mut self, position: Pos) -> Result<i32> {
        if !self.can_build_launcher(position)? {
            return Err(GameError::new("Cannot build launcher"));
        }
        Ok(self.game.build_launcher(self.unit, position))
    }

    fn build_foundry(&mut self, position: Pos) -> Result<i32> {
        if !self.can_build_foundry(position)? {
            return Err(GameError::new("Cannot build foundry"));
        }
        Ok(self.game.build_foundry(self.unit, position))
    }

    fn can_build(&self, entity_type: EntityType, position: Pos, extra: BuildExtra) -> Result<bool> {
        let dir = || match extra {
            BuildExtra::Direction(d) => Ok(d),
            _ => Err(GameError::new("Direction extra is required")),
        };
        let pos = || match extra {
            BuildExtra::Position(p) => Ok(p),
            _ => Err(GameError::new("Position extra is required")),
        };
        match entity_type {
            EntityType::Conveyor => self.can_build_conveyor(position, dir()?),
            EntityType::Splitter => self.can_build_splitter(position, dir()?),
            EntityType::ArmouredConveyor => self.can_build_armoured_conveyor(position, dir()?),
            EntityType::Bridge => self.can_build_bridge(position, pos()?),
            EntityType::Harvester => self.can_build_harvester(position),
            EntityType::Road => self.can_build_road(position),
            EntityType::Barrier => self.can_build_barrier(position),
            EntityType::Gunner => self.can_build_gunner(position, dir()?),
            EntityType::Sentinel => self.can_build_sentinel(position, dir()?),
            EntityType::Breach => self.can_build_breach(position, dir()?),
            EntityType::Launcher => self.can_build_launcher(position),
            EntityType::Foundry => self.can_build_foundry(position),
            _ => Err(GameError::new("entity_type is not buildable")),
        }
    }

    fn build(&mut self, entity_type: EntityType, position: Pos, extra: BuildExtra) -> Result<i32> {
        let dir = || match extra {
            BuildExtra::Direction(d) => Ok(d),
            _ => Err(GameError::new("Direction extra is required")),
        };
        let pos = || match extra {
            BuildExtra::Position(p) => Ok(p),
            _ => Err(GameError::new("Position extra is required")),
        };
        match entity_type {
            EntityType::Conveyor => self.build_conveyor(position, dir()?),
            EntityType::Splitter => self.build_splitter(position, dir()?),
            EntityType::ArmouredConveyor => self.build_armoured_conveyor(position, dir()?),
            EntityType::Bridge => self.build_bridge(position, pos()?),
            EntityType::Harvester => self.build_harvester(position),
            EntityType::Road => self.build_road(position),
            EntityType::Barrier => self.build_barrier(position),
            EntityType::Gunner => self.build_gunner(position, dir()?),
            EntityType::Sentinel => self.build_sentinel(position, dir()?),
            EntityType::Breach => self.build_breach(position, dir()?),
            EntityType::Launcher => self.build_launcher(position),
            EntityType::Foundry => self.build_foundry(position),
            _ => Err(GameError::new("entity_type is not buildable")),
        }
    }

    fn can_destroy(&self, building_pos: Pos) -> Result<bool> {
        let bot = match self.game.entity(self.unit) {
            Some(Entity::BuilderBot(bot)) => bot,
            _ => return Ok(false),
        };
        if bot.position.distance_squared(building_pos) > ACTION_RADIUS_SQ {
            return Ok(false);
        }
        if !self.game.game_map.in_bounds(building_pos) {
            return Ok(false);
        }
        let tile = self.game.game_map.tile(building_pos);
        let Some(building_id) = tile.building else {
            return Ok(false);
        };
        if matches!(self.game.entity(building_id), Some(Entity::Core(_))) {
            return Ok(false);
        }
        let Some(building) = self
            .game
            .entity(building_id)
            .and_then(|entity| entity.as_building())
        else {
            return Ok(false);
        };
        Ok(building.team == bot.team)
    }

    fn destroy(&mut self, building_pos: Pos) -> Result<()> {
        if !self.can_destroy(building_pos)? {
            return Err(GameError::new("Cannot destroy"));
        }
        let building_id = self
            .game
            .game_map
            .tile(building_pos)
            .building
            .expect("can_destroy was true but tile had no building");
        self.game.destroy_entity(building_id);
        Ok(())
    }

    fn heal(&mut self, position: Pos) -> Result<()> {
        if !self.can_heal(position)? {
            return Err(GameError::new("Cannot heal"));
        }
        let bot_id = self.unit;
        let team = self
            .game
            .entity(bot_id)
            .and_then(|e| e.as_unit())
            .expect("healer is not a unit")
            .team;
        // 1 Ti per heal action — flat, not scaled.
        self.game.spend(team, BUILDER_BOT_HEAL_COST);
        self.game.heal_tile(position, team);
        let Some(Entity::BuilderBot(bot)) = self.game.entity_mut(bot_id) else {
            unreachable!()
        };
        bot.action_cooldown += 1;
        let cd = bot.action_cooldown;
        self.game
            .replay_recorder
            .append(GameDiff::SetActionCooldown {
                id: bot_id,
                value: cd,
            });
        Ok(())
    }

    fn can_heal(&self, position: Pos) -> Result<bool> {
        let bot = match self.game.entity(self.unit) {
            Some(Entity::BuilderBot(bot)) => bot,
            _ => return Ok(false),
        };
        if !bot.can_act() {
            return Ok(false);
        }
        if bot.position.distance_squared(position) > ACTION_RADIUS_SQ {
            return Ok(false);
        }
        if !self.game.game_map.in_bounds(position) {
            return Ok(false);
        }
        let team = bot.team;
        // Cost: must afford 1 Ti per heal (flat, not scaled).
        if !self.game.players[team.index()].can_afford(BUILDER_BOT_HEAL_COST) {
            return Ok(false);
        }
        // Tile must contain at least one friendly entity below max HP
        // (otherwise no HP would be gained — `heal` is a no-op which the
        // 1.7.1 spec rejects).
        let tile = self.game.game_map.tile(position);
        let any_below_max = [tile.building, tile.builder_bot]
            .iter()
            .filter_map(|id| *id)
            .filter_map(|id| self.game.entity(id))
            .any(|e| e.team == team && e.hp < e.max_hp);
        Ok(any_below_max)
    }

    fn self_destruct(&mut self) -> Result<()> {
        let (pos, is_builder_bot) = match self.game.entity(self.unit) {
            Some(Entity::BuilderBot(bot)) => (bot.position, true),
            Some(entity) => match entity.as_unit() {
                Some(unit) => (unit.position, false),
                None => return Err(GameError::new("Unit is not a unit")),
            },
            None => return Err(GameError::new("Unknown unit")),
        };
        self.game.destroy_entity(self.unit);
        if is_builder_bot {
            self.game.damage_tile(pos, BUILDER_BOT_SELF_DESTRUCT_DAMAGE);
        }
        Ok(())
    }

    fn resign(&mut self, message: Option<String>) -> Result<()> {
        let team = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown unit"))?
            .team;
        self.game.resign_called = true;
        if let Some(msg) = message {
            let truncated = if msg.len() > 500 {
                msg.chars().take(500).collect::<String>()
            } else {
                msg
            };
            self.game.resign_message = Some(truncated);
        }
        let core_id = self
            .game
            .entities
            .iter()
            .find_map(|(&id, e)| match e {
                Entity::Core(core) if core.team == team => Some(id),
                _ => None,
            })
            .ok_or_else(|| GameError::new("No core found"))?;
        self.game.destroy_entity(core_id);
        Ok(())
    }

    fn can_place_marker(&self, position: Pos) -> Result<bool> {
        if self.has_placed_marker {
            return Ok(false);
        }
        let entity = match self.game.entity(self.unit) {
            Some(e) => e,
            None => return Ok(false),
        };
        let unit = match entity.as_unit() {
            Some(u) => u,
            None => return Ok(false),
        };
        if !self.game.game_map.in_bounds(position) {
            return Ok(false);
        }
        if unit.position.distance_squared(position) > unit.action_radius_sq() {
            return Ok(false);
        }
        let tile = self.game.game_map.tile(position);
        if tile.environment == Environment::Wall {
            return Ok(false);
        }
        // Markers are non-walkable buildings. Per `docs/spec/builder-bot.md`
        // "If a tile already contains a builder bot, only walkable
        // buildings (conveyors and roads) can be built on that tile."
        // Markers aren't walkable, so a tile occupied by a builder bot
        // can't accept a new marker.
        if tile.builder_bot.is_some() {
            return Ok(false);
        }
        match tile.building {
            None => Ok(true),
            Some(id) => match self.game.entity(id) {
                Some(Entity::Marker(marker)) => Ok(marker.team == unit.team),
                _ => Ok(false),
            },
        }
    }

    fn place_marker(&mut self, position: Pos, value: u32) -> Result<()> {
        if !self.can_place_marker(position)? {
            return Err(GameError::new("Cannot place marker"));
        }
        let team = self
            .game
            .entity(self.unit)
            .and_then(|e| e.as_unit())
            .expect("can_place_marker was true but entity is not a unit")
            .team;
        self.game.place_marker(team, position, value);
        self.has_placed_marker = true;
        Ok(())
    }

    fn get_marker_value(&self, id: i32) -> Result<u32> {
        self.assert_entity_in_vision(id)?;
        let entity = self
            .game
            .entity(id)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        match entity {
            Entity::Marker(marker) => Ok(marker.value),
            _ => Err(GameError::new("Entity is not a marker")),
        }
    }

    fn get_gunner_target(&self) -> Result<Option<Pos>> {
        let entity = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        if !matches!(entity, Entity::Gunner(_)) {
            return Err(GameError::new("Unit is not a gunner"));
        }
        Ok(self.game.gunner_target(self.unit))
    }

    fn can_fire(&self, target: Pos) -> Result<bool> {
        let entity = match self.game.entity(self.unit) {
            Some(e) => e,
            None => return Ok(false),
        };
        // Builder bot own-tile attack: target must equal bot position;
        // requires action cooldown 0, 2 Ti, and a non-armoured-conveyor
        // building on the tile (armoured conveyors are immune).
        if let Entity::BuilderBot(bot) = entity {
            if !bot.can_act() {
                return Ok(false);
            }
            if target != bot.position {
                return Ok(false);
            }
            // Action costs (attack, heal, rotate) are flat, not scaled
            // by the team's cost multiplier — that multiplier applies
            // only to BUILD costs. Verified against the cambc 1.7.1
            // binary: attack cost stays 2 Ti regardless of scale.
            if !self.game.players[bot.team.index()].can_afford(BUILDER_BOT_ATTACK_COST) {
                return Ok(false);
            }
            let tile = self.game.game_map.tile(target);
            let Some(building_id) = tile.building else {
                return Ok(false);
            };
            // Armoured conveyors are immune to builder-bot attacks.
            if matches!(
                self.game.entity(building_id),
                Some(Entity::ArmouredConveyor(_))
            ) {
                return Ok(false);
            }
            return Ok(true);
        }
        let turret = match entity.as_turret() {
            Some(t) => t,
            None => return Ok(false),
        };
        if !turret.can_act() || turret.ammo_amount <= 0 {
            return Ok(false);
        }
        match turret {
            Turret::Gunner(_) => Ok(self.game.gunner_can_fire_at(self.unit, target)),
            Turret::Sentinel(_) => Ok(self.game.game_map.in_bounds(target)
                && self.game.sentinel_target_valid(self.unit, target)),
            Turret::Breach(_) => Ok(self.game.game_map.in_bounds(target)
                && self.game.breach_target_valid(self.unit, target)),
            Turret::Launcher(_) => Err(GameError::new(
                "Use can_launch() for launchers, not can_fire()",
            )),
        }
    }

    fn fire(&mut self, target: Pos) -> Result<()> {
        if !self.can_fire(target)? {
            return Err(GameError::new("Cannot fire"));
        }
        let entity = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        // Builder bot own-tile attack path.
        if let Entity::BuilderBot(_) = entity {
            let bot_id = self.unit;
            let team = entity.team;
            // Flat 2 Ti, not scaled. See can_fire().
            self.game.spend(team, BUILDER_BOT_ATTACK_COST);
            // Damage the building on this tile (not the bot itself).
            let building_id = self.game.game_map.tile(target).building;
            if let Some(bid) = building_id {
                self.game.apply_damage(bid, BUILDER_BOT_ATTACK_DAMAGE);
            }
            // Emit BuilderAttack BEFORE the cooldown update — the
            // 1.7.1 binary records the attack action then the cooldown
            // bump, in that order.
            self.game
                .replay_recorder
                .append(GameDiff::BuilderAttack { id: bot_id });
            if let Some(Entity::BuilderBot(bot)) = self.game.entity_mut(bot_id) {
                bot.action_cooldown += 1;
                let cd = bot.action_cooldown;
                self.game
                    .replay_recorder
                    .append(GameDiff::SetActionCooldown {
                        id: bot_id,
                        value: cd,
                    });
            }
            return Ok(());
        }
        let turret = entity
            .as_turret()
            .ok_or_else(|| GameError::new("Unit is not a turret"))?;
        if matches!(turret, Turret::Launcher(_)) {
            return Err(GameError::new("Use launch() for launchers, not fire()"));
        }
        let axionite = turret.ammo_type == Some(ResourceType::RefinedAxionite);
        let kind = match turret {
            Turret::Gunner(_) => 0u8,
            Turret::Sentinel(_) => 1,
            Turret::Breach(_) => 2,
            Turret::Launcher(_) => unreachable!(),
        };
        match kind {
            0 => self.game.fire_gunner(self.unit, target, axionite),
            1 => self.game.fire_sentinel(self.unit, target, axionite),
            2 => self.game.fire_breach(self.unit, target),
            _ => unreachable!(),
        }
        Ok(())
    }

    fn can_launch(&self, bot_pos: Pos, target: Pos) -> Result<bool> {
        let entity = match self.game.entity(self.unit) {
            Some(e) => e,
            None => return Ok(false),
        };
        let turret = match entity.as_turret() {
            Some(t) => t,
            None => return Ok(false),
        };
        if !matches!(turret, Turret::Launcher(_)) {
            return Ok(false);
        }
        if !turret.can_act() {
            return Ok(false);
        }
        if !self.game.game_map.in_bounds(bot_pos) {
            return Ok(false);
        }
        let launcher_pos = turret.position;
        if launcher_pos.distance_squared(bot_pos) > ACTION_RADIUS_SQ {
            return Ok(false);
        }
        if self.game.game_map.tile(bot_pos).builder_bot.is_none() {
            return Ok(false);
        }
        if !self.game.launcher_target_valid(self.unit, target) {
            return Ok(false);
        }
        let bot_id = self.game.game_map.tile(bot_pos).builder_bot.unwrap();
        let bot_team = self.game.entity(bot_id).expect("unknown bot").team;
        Ok(self.game.is_tile_bot_passable(target, bot_team))
    }

    fn launch(&mut self, bot_pos: Pos, target: Pos) -> Result<()> {
        let entity = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let turret = entity
            .as_turret()
            .ok_or_else(|| GameError::new("Unit is not a turret"))?;
        if !matches!(turret, Turret::Launcher(_)) {
            return Err(GameError::new("Unit is not a launcher"));
        }
        if !self.can_launch(bot_pos, target)? {
            return Err(GameError::new("Cannot launch"));
        }
        let bot_id = self
            .game
            .game_map
            .tile(bot_pos)
            .builder_bot
            .expect("can_launch was true but no builder bot at bot_pos");
        self.game.fire_launcher(self.unit, bot_id, target);
        Ok(())
    }

    fn can_rotate(&self, direction: Direction) -> Result<bool> {
        if !direction.is_directional() {
            return Ok(false);
        }
        let entity = match self.game.entity(self.unit) {
            Some(e) => e,
            None => return Ok(false),
        };
        let Entity::Gunner(gunner) = entity else {
            return Ok(false);
        };
        if !gunner.can_act() {
            return Ok(false);
        }
        if gunner.direction == direction {
            return Ok(false);
        }
        // Flat 10 Ti rotate cost; action costs aren't scaled.
        Ok(self.game.players[gunner.team.index()].can_afford(GUNNER_ROTATE_COST))
    }

    fn rotate(&mut self, direction: Direction) -> Result<()> {
        if !self.can_rotate(direction)? {
            return Err(GameError::new("Cannot rotate"));
        }
        let team = self
            .game
            .entity(self.unit)
            .expect("rotate: unknown unit")
            .team;
        self.game.spend(team, GUNNER_ROTATE_COST);
        let id = self.unit;
        let updated = if let Some(Entity::Gunner(g)) = self.game.entities.get_mut(&id) {
            g.direction = direction;
            g.action_cooldown = GUNNER_ROTATE_COOLDOWN;
            g.clone()
        } else {
            return Err(GameError::new("rotate: unit is not a gunner"));
        };
        // Re-emit PlaceEntity so the visualiser sees the new direction.
        self.game.replay_recorder.append(GameDiff::PlaceEntity {
            id,
            entity: Entity::Gunner(updated),
        });
        self.game
            .replay_recorder
            .append(GameDiff::SetActionCooldown {
                id,
                value: GUNNER_ROTATE_COOLDOWN,
            });
        Ok(())
    }

    fn can_fire_from(
        &self,
        position: Pos,
        direction: Direction,
        turret_type: EntityType,
        target: Pos,
    ) -> Result<bool> {
        if !self.game.game_map.in_bounds(position) || !self.game.game_map.in_bounds(target) {
            return Ok(false);
        }
        match turret_type {
            EntityType::Gunner => Ok(self
                .game
                .gunner_can_fire_from_at(position, direction, target)),
            EntityType::Sentinel => Ok(self
                .game
                .sentinel_target_valid_from(position, direction, target)),
            EntityType::Breach => Ok(self
                .game
                .breach_target_valid_from(position, direction, target)),
            EntityType::Launcher => {
                // Launcher only checks raw throw range here; pickup adjacency
                // and bot-passable target are NOT checked. Per docs.
                let dist_sq = position.distance_squared(target);
                Ok(dist_sq > 0 && dist_sq <= LAUNCHER_VISION_RADIUS_SQ)
            }
            _ => Err(GameError::new(
                "turret_type must be one of GUNNER, SENTINEL, BREACH, LAUNCHER",
            )),
        }
    }

    fn get_attackable_tiles(&self) -> Result<Vec<Pos>> {
        let entity = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let turret = entity
            .as_turret()
            .ok_or_else(|| GameError::new("Unit is not a turret"))?;
        let (origin, dir, ty) = match turret {
            Turret::Gunner(g) => (g.position, g.direction, EntityType::Gunner),
            Turret::Sentinel(s) => (s.position, s.direction, EntityType::Sentinel),
            Turret::Breach(b) => (b.position, b.direction, EntityType::Breach),
            Turret::Launcher(l) => (l.position, Direction::Centre, EntityType::Launcher),
        };
        Ok(self.compute_attackable_tiles_pattern(origin, dir, ty))
    }

    fn get_attackable_tiles_from(
        &self,
        position: Pos,
        direction: Direction,
        turret_type: EntityType,
    ) -> Result<Vec<Pos>> {
        Ok(self.compute_attackable_tiles_pattern(position, direction, turret_type))
    }

    fn convert(&mut self, amount: i32) -> Result<()> {
        if amount < 0 {
            return Err(GameError::new("convert amount must be non-negative"));
        }
        let team = self
            .game
            .entity(self.unit)
            .ok_or_else(|| GameError::new("Unknown unit"))?
            .team;
        if !matches!(self.game.entity(self.unit), Some(Entity::Core(_))) {
            return Err(GameError::new("Only cores can convert"));
        }
        let player = &mut self.game.players[team.index()];
        if player.axionite < amount {
            return Err(GameError::new("Not enough axionite to convert"));
        }
        player.axionite -= amount;
        player.axionite_collected -= amount;
        let rate = AXIONITE_CONVERSION_TITANIUM_RATE;
        player.titanium += amount * rate;
        player.titanium_collected += amount * rate;
        Ok(())
    }

    fn spawn_builder(&mut self, position: Pos) -> Result<i32> {
        if !self.can_spawn(position)? {
            return Err(GameError::new("Cannot spawn"));
        }
        Ok(self.game.spawn_builder(self.unit, position))
    }

    fn can_spawn(&self, position: Pos) -> Result<bool> {
        let core = match self.game.entity(self.unit) {
            Some(Entity::Core(c)) => c,
            _ => return Ok(false),
        };
        if !core.can_act() {
            return Ok(false);
        }
        if core.position.distance_squared(position) > CORE_SPAWNING_RADIUS_SQ {
            return Ok(false);
        }
        if !self.game.is_tile_bot_passable(position, core.team) {
            return Ok(false);
        }
        if self.game.unit_count(core.team) >= MAX_TEAM_UNITS {
            return Ok(false);
        }
        let cost = self.game.scaled_cost(core.team, BUILDER_BOT_BASE_COST);
        Ok(self.game.players[core.team.index()].can_afford(cost))
    }

    fn get_nearby_tiles(&self, dist_sq: Option<i32>) -> Result<Vec<Pos>> {
        let entity = self
            .game
            .entities
            .get(&self.unit)
            .ok_or_else(|| GameError::new("Unknown id"))?;
        let unit = entity
            .as_unit()
            .ok_or_else(|| GameError::new("Unit is not a unit"))?;
        let pos = unit.position;
        let vision = unit.vision_radius_sq();
        if let Some(d) = dist_sq {
            if d > vision {
                return Err(GameError::new("dist_sq exceeds vision radius"));
            }
        }
        let radius_sq = dist_sq.unwrap_or(vision);
        let r = (radius_sq as f64).sqrt().ceil() as i32;
        let mut result = Vec::new();
        for dy in -r..=r {
            for dx in -r..=r {
                if dx * dx + dy * dy > radius_sq {
                    continue;
                }
                let p = Pos {
                    x: pos.x + dx,
                    y: pos.y + dy,
                };
                if self.game.game_map.in_bounds(p) {
                    result.push(p);
                }
            }
        }
        Ok(result)
    }

    fn get_nearby_entities(&self, dist_sq: Option<i32>) -> Result<Vec<i32>> {
        let tiles = self.get_nearby_tiles(dist_sq)?;
        let mut seen = rustc_hash::FxHashSet::default();
        let mut result = Vec::new();
        for p in tiles {
            let tile = self.game.game_map.tile(p);
            for id in [tile.building, tile.builder_bot].into_iter().flatten() {
                if seen.insert(id) {
                    result.push(id);
                }
            }
        }
        Ok(result)
    }

    fn get_nearby_buildings(&self, dist_sq: Option<i32>) -> Result<Vec<i32>> {
        let all = self.get_nearby_entities(dist_sq)?;
        Ok(all
            .into_iter()
            .filter(|id| {
                self.game
                    .entity(*id)
                    .and_then(|e| e.as_building())
                    .is_some()
            })
            .collect())
    }

    fn get_nearby_units(&self, dist_sq: Option<i32>) -> Result<Vec<i32>> {
        let all = self.get_nearby_entities(dist_sq)?;
        Ok(all
            .into_iter()
            .filter(|id| self.game.entity(*id).and_then(|e| e.as_unit()).is_some())
            .collect())
    }

    fn draw_indicator_line(
        &mut self,
        pos_a: Pos,
        pos_b: Pos,
        r: i32,
        g: i32,
        b: i32,
    ) -> Result<()> {
        self.game.replay_recorder.append(GameDiff::IndicatorLine {
            id: self.unit,
            pos_a,
            pos_b,
            r,
            g,
            b,
        });
        Ok(())
    }

    fn draw_indicator_dot(&mut self, pos: Pos, r: i32, g: i32, b: i32) -> Result<()> {
        self.game.replay_recorder.append(GameDiff::IndicatorDot {
            id: self.unit,
            pos,
            r,
            g,
            b,
        });
        Ok(())
    }
}
