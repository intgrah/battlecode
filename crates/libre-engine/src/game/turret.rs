use super::{Game, Pos, Turret, GUNNER_VISION_RADIUS_SQ, Environment, RngExt, SeedableRng, Direction, Entity, GUNNER_DAMAGE, GameDiff, GUNNER_AMMO_COST, GUNNER_FIRE_COOLDOWN, SENTINEL_VISION_RADIUS_SQ, SENTINEL_DAMAGE, SENTINEL_AMMO_COST, SENTINEL_FIRE_COOLDOWN, BREACH_ATTACK_RADIUS_SQ, BREACH_DAMAGE, BREACH_SPLASH_DAMAGE, BREACH_AMMO_COST, BREACH_FIRE_COOLDOWN, LAUNCHER_VISION_RADIUS_SQ, LAUNCHER_FIRE_COOLDOWN};
use crate::common::game_constants::{GUNNER_AXIONITE_DAMAGE, SENTINEL_STUN_DURATION};

impl Game {
    /// Closest **targetable** tile on the gunner's forward ray within
    /// vision range. Walls block but are not targetable; markers are
    /// targetable but do not block farther targets; builder bots and
    /// non-marker buildings are both targetable and blocking. Per
    /// `docs/spec/turrets.md` (Gunner) and `docs/api/controller.md`.
    #[must_use] 
    pub fn gunner_target(&self, turret_id: i32) -> Option<Pos> {
        let entity = self.entity(turret_id).expect("unknown turret");
        let Turret::Gunner(turret) = entity.as_turret().expect("not a turret") else {
            panic!("gunner_target called on non-gunner");
        };
        let origin = turret.position;
        let dir = turret.direction;
        let vision_sq = GUNNER_VISION_RADIUS_SQ;
        let mut pos = origin + dir;
        loop {
            if !self.game_map.in_bounds(pos) || origin.distance_squared(pos) > vision_sq {
                return None;
            }
            let tile = self.game_map.tile(pos);
            // Wall: blocks the ray, not targetable, no further legal target.
            if tile.environment == Environment::Wall {
                return None;
            }
            // Builder bot: first hit wins.
            if tile.builder_bot.is_some() {
                return Some(pos);
            }
            // Marker or non-marker building: first hit wins. (Markers are
            // pierceable for `can_fire`, but `gunner_target` only reports
            // the closest tile occupied by any targetable thing.)
            if tile.building.is_some() {
                return Some(pos);
            }
            pos = pos + dir;
        }
    }

    /// Whether `target` is a legal gunner-fire target from `turret_id`'s
    /// current position and facing.
    #[must_use] 
    pub fn gunner_can_fire_at(&self, turret_id: i32, target: Pos) -> bool {
        let entity = self.entity(turret_id).expect("unknown turret");
        let Turret::Gunner(turret) = entity.as_turret().expect("not a turret") else {
            return false;
        };
        self.gunner_can_fire_from_at(turret.position, turret.direction, target)
    }

    /// Same as [`Self::gunner_can_fire_at`] but for a hypothetical gunner
    /// at any position/direction (used by `Controller::can_fire_from`).
    #[must_use] 
    pub fn gunner_can_fire_from_at(&self, origin: Pos, dir: Direction, target: Pos) -> bool {
        if !dir.is_directional() {
            return false;
        }
        if !self.game_map.in_bounds(target) || !self.game_map.in_bounds(origin) {
            return false;
        }
        if origin.distance_squared(target) > GUNNER_VISION_RADIUS_SQ {
            return false;
        }
        // Target must lie on the forward ray from origin in `dir`.
        let (dx, dy) = dir.delta();
        let rx = target.x - origin.x;
        let ry = target.y - origin.y;
        if rx == 0 && ry == 0 {
            return false;
        }
        if dx == 0 {
            if rx != 0 || ry.signum() != dy.signum() {
                return false;
            }
        } else if dy == 0 {
            if ry != 0 || rx.signum() != dx.signum() {
                return false;
            }
        } else {
            // Diagonal: must be on the |x|=|y| ray in the right quadrant.
            if rx.signum() != dx.signum() || ry.signum() != dy.signum() || rx.abs() != ry.abs() {
                return false;
            }
        }
        // Walk from origin+dir up to (but excluding) target. If we hit a
        // wall or a non-marker non-empty tile before target, the shot is
        // blocked. Markers are pierceable.
        let mut pos = origin + dir;
        while pos != target {
            if !self.game_map.in_bounds(pos) {
                return false;
            }
            let tile = self.game_map.tile(pos);
            if tile.environment == Environment::Wall {
                return false;
            }
            if tile.builder_bot.is_some() {
                return false;
            }
            if let Some(building_id) = tile.building {
                let is_marker = matches!(self.entity(building_id), Some(Entity::Marker(_)));
                if !is_marker {
                    return false;
                }
            }
            pos = pos + dir;
        }
        // Target must itself be a legal target: not a wall, and occupied
        // (builder bot or building, including markers).
        let tile = self.game_map.tile(target);
        if tile.environment == Environment::Wall {
            return false;
        }
        tile.builder_bot.is_some() || tile.building.is_some()
    }

    /// Gunner: hits `target` (resolved by caller via `can_fire`).
    pub fn fire_gunner(&mut self, turret_id: i32, target: Pos, axionite: bool) {
        let damage = if axionite {
            GUNNER_AXIONITE_DAMAGE
        } else {
            GUNNER_DAMAGE
        };
        let from = self.entity(turret_id).expect("unknown turret").position;
        self.damage_tile(target, damage);
        self.replay_recorder
            .append(GameDiff::FireTurret { from, to: target });
        self.finish_firing_turret(turret_id, GUNNER_AMMO_COST, GUNNER_FIRE_COOLDOWN);
    }

    /// Check whether `target` is in the Sentinel's attack range: the intersection
    /// of the Chebyshev-1 line shape and the vision radius.
    #[must_use] 
    pub fn sentinel_target_valid(&self, turret_id: i32, target: Pos) -> bool {
        let entity = self.entity(turret_id).expect("unknown turret");
        let Turret::Sentinel(turret) = entity.as_turret().expect("not a turret") else {
            panic!("sentinel_target_valid called on non-sentinel");
        };
        self.sentinel_target_valid_from(turret.position, turret.direction, target)
    }

    /// Same shape check from a hypothetical position/direction.
    #[must_use] 
    pub const fn sentinel_target_valid_from(&self, origin: Pos, dir: Direction, target: Pos) -> bool {
        let dist_sq = origin.distance_squared(target);
        if dist_sq == 0 || dist_sq > SENTINEL_VISION_RADIUS_SQ {
            return false;
        }
        let (dx, dy) = dir.delta();
        let rx = target.x - origin.x;
        let ry = target.y - origin.y;
        let mut k = 1;
        while k * k * (dx * dx + dy * dy) <= SENTINEL_VISION_RADIUS_SQ {
            let lx = rx - k * dx;
            let ly = ry - k * dy;
            if lx.abs() <= 1 && ly.abs() <= 1 {
                return true;
            }
            k += 1;
        }
        false
    }

    /// Sentinel: hits the target tile. With refined-axionite ammo, stuns
    /// any unit on the direct target tile for `SENTINEL_STUN_DURATION` (5)
    /// extra action AND move cooldown. Per `docs/spec/turrets.md`.
    pub fn fire_sentinel(&mut self, turret_id: i32, target: Pos, axionite: bool) {
        let from = self.entity(turret_id).expect("unknown turret").position;
        self.replay_recorder
            .append(GameDiff::FireTurret { from, to: target });
        self.damage_tile(target, SENTINEL_DAMAGE);
        if axionite && self.game_map.in_bounds(target) {
            let tile = self.game_map.tile(target);
            let ids: Vec<i32> = [tile.building, tile.builder_bot]
                .iter()
                .filter_map(|id| *id)
                .collect();
            for id in ids {
                let entity = self
                    .entities
                    .get_mut(&id)
                    .unwrap_or_else(|| panic!("tile entity id missing from entities: {id}"));
                if let Some(mut unit) = entity.as_unit_mut() {
                    unit.action_cooldown += SENTINEL_STUN_DURATION;
                    unit.move_cooldown += SENTINEL_STUN_DURATION;
                    self.replay_recorder.append(GameDiff::SetActionCooldown {
                        id,
                        value: unit.action_cooldown,
                    });
                    self.replay_recorder.append(GameDiff::SetMoveCooldown {
                        id,
                        value: unit.move_cooldown,
                    });
                }
            }
        }
        self.finish_firing_turret(turret_id, SENTINEL_AMMO_COST, SENTINEL_FIRE_COOLDOWN);
    }

    /// Check whether `target` is in the Breach's 180° cone within attack
    /// radius (radius² ≤ `BREACH_ATTACK_RADIUS_SQ`, forward half-plane).
    #[must_use] 
    pub fn breach_target_valid(&self, turret_id: i32, target: Pos) -> bool {
        let entity = self.entity(turret_id).expect("unknown turret");
        let Turret::Breach(turret) = entity.as_turret().expect("not a turret") else {
            panic!("breach_target_valid called on non-breach");
        };
        self.breach_target_valid_from(turret.position, turret.direction, target)
    }

    /// Same cone check from a hypothetical position/direction.
    #[must_use] 
    pub const fn breach_target_valid_from(&self, origin: Pos, dir: Direction, target: Pos) -> bool {
        let dist_sq = origin.distance_squared(target);
        if dist_sq == 0 || dist_sq > BREACH_ATTACK_RADIUS_SQ {
            return false;
        }
        let (dx, dy) = dir.delta();
        let rx = target.x - origin.x;
        let ry = target.y - origin.y;
        let dot = rx * dx + ry * dy;
        dot >= 0
    }

    /// Breach: hits the target tile with high damage and deals splash damage
    /// to the 8 surrounding tiles (friendly fire enabled, except the breach itself).
    pub fn fire_breach(&mut self, turret_id: i32, target: Pos) {
        let origin = self.entity(turret_id).expect("unknown turret").position;
        self.replay_recorder.append(GameDiff::FireTurret {
            from: origin,
            to: target,
        });
        self.damage_tile(target, BREACH_DAMAGE);
        for dir in [
            Direction::North,
            Direction::Northeast,
            Direction::East,
            Direction::Southeast,
            Direction::South,
            Direction::Southwest,
            Direction::West,
            Direction::Northwest,
        ] {
            let splash_pos = target + dir;
            if splash_pos == origin {
                continue;
            }
            self.damage_tile(splash_pos, BREACH_SPLASH_DAMAGE);
        }
        self.finish_firing_turret(turret_id, BREACH_AMMO_COST, BREACH_FIRE_COOLDOWN);
    }

    /// Check whether `target` is within the Launcher's action range.
    #[must_use] 
    pub fn launcher_target_valid(&self, turret_id: i32, target: Pos) -> bool {
        let entity = self.entity(turret_id).expect("unknown turret");
        let origin = entity.position;
        let dist_sq = origin.distance_squared(target);
        dist_sq > 0 && dist_sq <= LAUNCHER_VISION_RADIUS_SQ
    }

    /// Launcher: picks up an adjacent builder bot and throws it to the target tile.
    pub fn fire_launcher(&mut self, turret_id: i32, bot_id: i32, target: Pos) {
        // Move the bot from its current position to the target.
        let from_pos = match self.entity(bot_id) {
            Some(Entity::BuilderBot(bot)) => bot.position,
            _ => panic!("fire_launcher: bot_id {bot_id} is not a builder bot"),
        };
        self.game_map.tile_mut(from_pos).builder_bot = None;
        self.game_map.tile_mut(target).builder_bot = Some(bot_id);
        let Some(Entity::BuilderBot(bot)) = self.entity_mut(bot_id) else {
            unreachable!()
        };
        bot.position = target;
        self.replay_recorder.append(GameDiff::MoveBuilderBot {
            id: bot_id,
            to: target,
        });
        self.finish_firing_turret(turret_id, 0, LAUNCHER_FIRE_COOLDOWN);
    }

    fn finish_firing_turret(&mut self, turret_id: i32, ammo_cost: i32, cooldown: i32) {
        let entity = self.entity_mut(turret_id).expect("unknown turret id");
        let mut turret = entity.as_turret_mut().expect("not a turret");
        turret.ammo_amount -= ammo_cost;
        assert!(
            turret.ammo_amount >= 0,
            "turret {turret_id} does not have enough ammo"
        );
        if turret.ammo_amount == 0 {
            turret.ammo_type = None;
        }
        turret.action_cooldown += cooldown;
        let new_cd = turret.action_cooldown;
        self.replay_recorder.append(GameDiff::SetActionCooldown {
            id: turret_id,
            value: new_cd,
        });
    }
}
