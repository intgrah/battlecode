//! Translation of `bots/intgrah/v54.7.9/gunner/__init__.py`.
//!
//! Phase 5 PosInt note: Gunner uses UnitState (not Builder), so the _p accessor
//! variants (is_passable_p, kind_at_p, etc.) are not available. The inner loops
//! in fire_target / score_ray walk a short ray (max 3 steps) via Position::add
//! and call ct API methods on Position — no hot-loop scenario worth converting.
//! TODO Phase 5 holdout: convert if UnitState gains _p accessors.

use cambc::{Controller, ControllerApi, Direction, EntityType, GameConstants, Position};

use crate::unit::{Unit, UnitState};
use crate::util::directions::DIR8;

/// Valid priority targets for rotation: other enemy turrets we should
/// actually use our shot on.
#[must_use]
const fn is_valid_rotation_target(et: EntityType) -> bool {
    matches!(
        et,
        EntityType::Sentinel | EntityType::Gunner | EntityType::Launcher | EntityType::Breach,
    )
}

pub struct Gunner {
    state: UnitState,
    idle_turns: i32,
}

impl Gunner {
    const SELF_DESTRUCT_THRESHOLD: i32 = 10;

    #[must_use]
    pub fn new() -> Self {
        Self {
            state: UnitState::new(),
            idle_turns: 0,
        }
    }

    /// Walk the forward ray. Return the first blocker iff firing
    /// actually damages the enemy: enemy non-harvester building OR
    /// enemy bot. A friendly absorber (any of our buildings except a
    /// marker, or our bot) returns None — the engine shoots the first
    /// blocker and a friendly one would eat the projectile.
    fn fire_target(&self, ct: &mut Controller<'_>, direction: Direction) -> Option<Position> {
        let my_pos = self.state.my_pos;
        let my_team = self.state.my_team;
        let mut cur = my_pos;
        for _ in 0..3 {
            cur = cur.add(direction);
            if cur.distance_squared(my_pos) > GameConstants::GUNNER_VISION_RADIUS_SQ {
                return None;
            }
            if !self.in_bounds(cur) {
                return None;
            }
            if !pyrust::unwrap!(ct.is_in_vision(cur)) {
                return None;
            }
            if let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(cur)) {
                let etype = pyrust::unwrap!(ct.get_entity_type(Some(bid)));
                if etype == EntityType::Marker {
                    continue;
                }
                if pyrust::unwrap!(ct.get_team(Some(bid))) == my_team {
                    return None;
                }
                if etype == EntityType::Harvester {
                    return None;
                }
                return Some(cur);
            }
            if let Some(&uid) = self.state.all_bots.get(&cur) {
                if pyrust::unwrap!(ct.get_team(Some(uid))) == my_team {
                    return None;
                }
                return Some(cur);
            }
        }
        None
    }

    /// Walk the forward ray from `my_pos` in `direction` (3 steps,
    /// capped by `GUNNER_VISION_RADIUS_SQ`). Return (score, `blocker_pos)`:
    ///
    ///   3 — enemy turret in `VALID_ROTATION_TARGETS` (highest value)
    ///   2 — enemy builder bot
    ///   1 — enemy core (always-on chip damage; below builders so a
    ///       free builder wins the rotation tiebreak)
    ///   0 — empty ray, friendly absorber, enemy harvester, enemy
    ///       non-target transport (conveyor / road etc.), vision gap
    ///
    /// Markers are transparent. A friendly bot or non-marker friendly
    /// building scores 0 (would eat our shot). Enemy harvesters score
    /// 0 (15 shots to kill, may feed a chain we're parasitising).
    fn score_ray(&self, ct: &mut Controller<'_>, direction: Direction) -> (i32, Option<Position>) {
        let my_pos = self.state.my_pos;
        let my_team = self.state.my_team;
        let mut cur = my_pos;
        for _ in 0..3 {
            cur = cur.add(direction);
            if cur.distance_squared(my_pos) > GameConstants::GUNNER_VISION_RADIUS_SQ {
                return (0, None);
            }
            if !self.in_bounds(cur) {
                return (0, None);
            }
            if !pyrust::unwrap!(ct.is_in_vision(cur)) {
                return (0, None);
            }
            if let Some(bid) = pyrust::unwrap!(ct.get_tile_building_id(cur)) {
                let etype = pyrust::unwrap!(ct.get_entity_type(Some(bid)));
                if etype == EntityType::Marker {
                    continue;
                }
                if pyrust::unwrap!(ct.get_team(Some(bid))) == my_team {
                    return (0, Some(cur)); // friendly building absorbs
                }
                if etype == EntityType::Harvester {
                    return (0, Some(cur)); // enemy harvester: skip
                }
                if etype == EntityType::Core {
                    return (1, Some(cur)); // enemy core
                }
                if !is_valid_rotation_target(etype) {
                    return (0, Some(cur)); // conveyor / road / etc.
                }
                return (3, Some(cur)); // enemy turret
            }
            if let Some(&uid) = self.state.all_bots.get(&cur) {
                if pyrust::unwrap!(ct.get_team(Some(uid))) == my_team {
                    return (0, Some(cur)); // friendly bot absorbs
                }
                return (2, Some(cur)); // enemy bot
            }
        }
        (0, None)
    }

    /// Find a direction whose forward ray hits something worth shooting.
    /// Enumerates all 8 directions, scores each via the same logic the
    /// fire decision uses, and picks the highest-scoring direction
    /// (tiebreak by closest blocker).
    fn try_rotate_to_enemy(&mut self, ct: &mut Controller<'_>) -> bool {
        let mut best_score: i32 = 0;
        let mut best_dist_sq: i32 = 999;
        let mut best_dir: Option<Direction> = None;
        for d in DIR8 {
            let (score, bpos) = self.score_ray(ct, d);
            let Some(bpos) = bpos else { continue };
            if score == 0 {
                continue;
            }
            let dist_sq = self.state.my_pos.distance_squared(bpos);
            if (score, -dist_sq) > (best_score, -best_dist_sq) {
                best_score = score;
                best_dist_sq = dist_sq;
                best_dir = Some(d);
            }
        }
        if let Some(d) = best_dir
            && pyrust::unwrap!(ct.can_rotate(d))
        {
            pyrust::unwrap!(ct.rotate(d));
            return true;
        }
        false
    }

    fn try_self_destruct(&mut self, ct: &mut Controller<'_>) {
        let my_team = self.state.my_team;
        let mut has_ally = false;
        for uid in pyrust::unwrap!(ct.get_nearby_units(None)) {
            if pyrust::unwrap!(ct.get_team(Some(uid))) == my_team {
                has_ally = true;
            } else {
                return;
            }
        }
        if has_ally {
            pyrust::unwrap!(ct.self_destruct());
        }
    }
}

impl Default for Gunner {
    fn default() -> Self {
        Self::new()
    }
}

impl Unit for Gunner {
    fn unit_state(&self) -> &UnitState {
        &self.state
    }

    fn unit_state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        // super().run(ct) — populate cached per-turn state.
        self.state.cache_per_turn_state(ct);
        self.state.check_symmetry_marker(ct);

        let facing = pyrust::unwrap!(ct.get_direction(None));
        let fire_target = self.fire_target(ct, facing);
        if let Some(target) = fire_target
            && pyrust::unwrap!(ct.can_fire(target))
        {
            pyrust::unwrap!(ct.fire(target));
            self.idle_turns = 0;
            return;
        }

        if self.try_rotate_to_enemy(ct) {
            self.idle_turns = 0;
        } else {
            self.idle_turns += 1;
        }

        if self.idle_turns > Self::SELF_DESTRUCT_THRESHOLD {
            self.try_self_destruct(ct);
        }
    }
}
