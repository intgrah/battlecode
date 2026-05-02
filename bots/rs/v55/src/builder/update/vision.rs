use std::collections::HashSet;

use cambc::{Controller, ControllerApi, EntityType, Environment, GameConstants, Position};

use crate::builder::Builder;
use crate::building::{edge_targets, make_building};
use crate::util::constants::{FLOW_HISTORY_LEN, INF, MAX_WIDTH, ROAD_COST};
use crate::util::directions::DIR8;
use crate::util::symmetry::Symmetry;

pub fn _remove_topology(builder: &mut Builder, pos: Position, i: usize) {
    let old_kind = builder.building_kind[i];
    let old_team = builder.building_team[i];
    let my_team = builder.state.my_team;
    if old_team == Some(my_team) && !pyrust::vec::is_empty!(builder.out_edges[i]) {
        let outs: Vec<Position> = pyrust::clone!(builder.out_edges[i]);
        for t in outs {
            if !builder.in_bounds(t) {
                continue;
            }
            let ti = builder.idx(t);
            if pyrust::vec::contains!(builder.in_edges[ti], &pos) {
                pyrust::vec::retain!(builder.in_edges[ti], |&p| p != pos);
                builder._on_in_edge_removed(t, pos);
                builder._check_multi_input(t);
                builder._check_dangling(t, &format!("edge_removed src={pos:?}"));
            }
        }
        builder.out_edges[i] = pyrust::vec::new!();
        builder._on_out_edges_changed(pos);
    }
    match old_kind {
        Some(EntityType::Foundry) if old_team == Some(my_team) => {
            pyrust::set::remove!(builder.my_foundries, &pos);
            builder._bump_foundry(pos, -1);
        }
        Some(EntityType::Harvester) => {
            if old_team == Some(my_team) {
                pyrust::set::remove!(builder.my_harvesters, &pos);
            }
            let env = builder.env[i];
            if env == Some(Environment::OreAxionite) {
                builder._bump_ax_harv(pos, -1);
            } else if env == Some(Environment::OreTitanium) {
                builder._bump_ti_harv(pos, -1);
            }
        }
        _ => {}
    }
}

pub fn _add_topology(
    builder: &mut Builder,
    ct: &Controller<'_>,
    pos: Position,
    bid: i32,
    kind: EntityType,
    team: cambc::Team,
) {
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    if builder.reach_parent[i] == -1 {
        builder.reach_parent[i] = i as i32;
        pyrust::vec::push!(builder.reach_frontier, i as i32);
    }
    if team == builder.state.my_team {
        let targets = edge_targets(ct, pos, bid, kind);
        if !pyrust::vec::is_empty!(targets) {
            let mut outs: Vec<Position> = pyrust::vec::new!();
            for t in targets {
                if builder.in_bounds(t) {
                    let ti = builder.idx(t);
                    pyrust::vec::push!(builder.in_edges[ti], pos);
                    pyrust::vec::push!(outs, t);
                    builder._check_multi_input(t);
                }
            }
            let was_ti_in = pyrust::vec::contains!(builder.ti_upstream, &pos);
            let was_ax_in = pyrust::vec::contains!(builder.ax_upstream, &pos);
            let pi = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
            builder.out_edges[pi] = pyrust::clone!(outs);
            builder._on_out_edges_changed(pos);
            for t in &outs {
                let ti = builder.idx(*t);
                if was_ti_in && pyrust::vec::contains!(builder.ti_upstream, &pos) {
                    builder._ti_in_count[ti] += 1;
                    builder._reeval_ti_upstream(*t);
                }
                if was_ax_in && pyrust::vec::contains!(builder.ax_upstream, &pos) {
                    builder._ax_in_count[ti] += 1;
                    builder._reeval_ax_upstream(*t);
                }
                builder._check_dangling(*t, &format!("edge_added src={pos:?}"));
            }
            return;
        }
    }
    match kind {
        EntityType::Foundry if team == builder.state.my_team => {
            pyrust::set::add!(builder.my_foundries, pos);
            builder._bump_foundry(pos, 1);
        }
        EntityType::Harvester => {
            if team == builder.state.my_team {
                pyrust::set::add!(builder.my_harvesters, pos);
            }
            let idx = builder.idx(pos);
            match builder.env[idx] {
                Some(Environment::OreAxionite) => builder._bump_ax_harv(pos, 1),
                Some(Environment::OreTitanium) => builder._bump_ti_harv(pos, 1),
                _ => {}
            }
        }
        _ => {}
    }
}

/// Shared post-transition fix-up after a tile's building changes
/// (added, removed, or replaced). Refreshes cost grid, precomputed
/// neighbours, and dangling status for the tile and any splitter
/// feeders whose satisfaction count may have flipped.
fn _apply_post_transition(
    builder: &mut Builder,
    pos: Position,
    i: usize,
    env: Option<Environment>,
    trigger: &str,
) {
    let kind = builder.building_kind[i];
    let team = builder.building_team[i];
    _update_cost(builder, i, env, kind, team);
    builder.update_pnb(i);
    builder._check_dangling(pos, trigger);
    let feeders: Vec<Position> = pyrust::clone!(builder.in_edges[i]);
    for feeder in &feeders {
        let fi = (feeder.y as usize) * MAX_WIDTH + (feeder.x as usize);
        if builder.building_kind[fi] == Some(EntityType::Splitter) {
            let siblings: Vec<Position> = pyrust::clone!(builder.out_edges[fi]);
            for sib in siblings {
                if sib != pos {
                    builder._check_dangling(sib, "splitter_sibling");
                }
            }
        }
    }
}

/// Mid-turn invariant fix-up after `ct.destroy(pos)`.
pub fn apply_local_destroy(builder: &mut Builder, pos: Position) {
    let i = builder.idx(pos);
    _remove_topology(builder, pos, i);
    builder.building_kind[i] = None;
    builder.building_team[i] = None;
    builder.hp[i] = 0;
    builder.max_hp[i] = 0;
    let env = builder.env[i];
    _apply_post_transition(builder, pos, i, env, "local_destroy");
    _refresh_ore_set(builder, pos, env);
}

/// Maintain the incremental `visible_{ti,ax}_ores` sets: a tile is in
/// the matching set iff its env is the corresponding ore type AND it
/// has no harvester on it. Called wherever the env or building on
/// `pos` may have changed (vision update, mid-turn local destroy).
fn _refresh_ore_set(builder: &mut Builder, pos: Position, env: Option<Environment>) {
    let i = builder.idx(pos);
    let has_harvester = builder.building_kind[i] == Some(EntityType::Harvester);
    if env == Some(Environment::OreTitanium) {
        if has_harvester {
            pyrust::set::remove!(builder.visible_ti_ores, &pos);
        } else {
            pyrust::set::add!(builder.visible_ti_ores, pos);
        }
        pyrust::set::remove!(builder.visible_ax_ores, &pos);
    } else if env == Some(Environment::OreAxionite) {
        if has_harvester {
            pyrust::set::remove!(builder.visible_ax_ores, &pos);
        } else {
            pyrust::set::add!(builder.visible_ax_ores, pos);
        }
        pyrust::set::remove!(builder.visible_ti_ores, &pos);
    } else {
        pyrust::set::remove!(builder.visible_ti_ores, &pos);
        pyrust::set::remove!(builder.visible_ax_ores, &pos);
    }
}

pub fn _update_cost(
    builder: &mut Builder,
    i: usize,
    terrain: Option<Environment>,
    kind: Option<EntityType>,
    team: Option<cambc::Team>,
) {
    let mut routing_extra: i32 = 0;
    let cost: i32;
    let buildable: bool;
    if terrain == Some(Environment::Wall) {
        cost = INF;
        buildable = false;
    } else if let Some(k) = kind {
        match k {
            EntityType::Road if team == Some(builder.state.my_team) => {
                cost = 1;
                buildable = true;
            }
            EntityType::Road => {
                cost = 1;
                buildable = true;
                routing_extra = 4;
            }
            EntityType::Marker => {
                cost = ROAD_COST;
                buildable = true;
            }
            EntityType::Conveyor
            | EntityType::Splitter
            | EntityType::ArmouredConveyor
            | EntityType::Bridge => {
                cost = 1;
                buildable = false;
            }
            EntityType::Core if team == Some(builder.state.my_team) => {
                cost = 1;
                buildable = false;
            }
            _ => {
                cost = INF;
                buildable = false;
            }
        }
    } else if terrain == Some(Environment::Empty) {
        cost = ROAD_COST;
        buildable = true;
    } else {
        cost = ROAD_COST;
        buildable = false;
    }
    builder.cost_grid[i] = cost;
    builder.routing_extra[i] = routing_extra as u8;
    if builder.buildable[i] != buildable {
        builder.buildable[i] = buildable;
        builder.ti_routable[i] = buildable && !builder.ti_leakage[i];
        builder.ax_routable[i] = buildable && !builder.ax_leakage[i];
    }
}

fn _update_turret_rays(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    pos: Position,
    bid: i32,
    kind: EntityType,
    team: cambc::Team,
) {
    let my_team = builder.state.my_team;
    let enemy = team != my_team;
    match kind {
        EntityType::Launcher if enemy => {
            for d in DIR8 {
                let n = pos.add(d);
                if builder.in_bounds(n) {
                    pyrust::set::add!(builder.adjacent_to_enemy_launcher, n);
                }
            }
        }
        EntityType::Gunner if enemy => {
            let d = pyrust::unwrap!(ct.get_direction(Some(bid)));
            let mut ray = pos;
            for _ in 0..3 {
                ray = ray.add(d);
                if pos.distance_squared(ray) > GameConstants::GUNNER_VISION_RADIUS_SQ {
                    break;
                }
                if builder.in_bounds(ray) {
                    pyrust::set::add!(builder.enemy_turret_ray_tiles, ray);
                }
            }
        }
        EntityType::Sentinel if enemy => {
            let d = pyrust::unwrap!(ct.get_direction(Some(bid)));
            for tile in pyrust::unwrap!(ct.get_attackable_tiles_from(pos, d, EntityType::Sentinel))
            {
                pyrust::set::add!(builder.enemy_turret_ray_tiles, tile);
            }
        }
        EntityType::Gunner => {
            let d = pyrust::unwrap!(ct.get_direction(Some(bid)));
            let mut ray = pos;
            for _ in 0..3 {
                ray = ray.add(d);
                if pos.distance_squared(ray) > GameConstants::GUNNER_VISION_RADIUS_SQ {
                    break;
                }
                if !builder.in_bounds(ray) {
                    break;
                }
                if builder.get_env(ray) == Some(Environment::Wall) {
                    break;
                }
                pyrust::set::add!(builder.friendly_turret_ray_tiles, ray);
                if pyrust::is_some!(builder.get_building(ray)) {
                    break;
                }
            }
        }
        EntityType::Sentinel => {
            let d = pyrust::unwrap!(ct.get_direction(Some(bid)));
            let mut ray = pos;
            for _ in 0..6 {
                ray = ray.add(d);
                if pos.distance_squared(ray) > 32 {
                    break;
                }
                if !builder.in_bounds(ray) {
                    break;
                }
                if builder.get_env(ray) == Some(Environment::Wall) {
                    break;
                }
                pyrust::set::add!(builder.friendly_turret_ray_tiles, ray);
                for hd in DIR8 {
                    let h = ray.add(hd);
                    if builder.in_bounds(h) {
                        pyrust::set::add!(builder.friendly_turret_ray_tiles, h);
                    }
                }
                if pyrust::is_some!(builder.get_building(ray)) {
                    break;
                }
            }
        }
        _ => {}
    }
}

pub fn update_vision(builder: &mut Builder, ct: &mut Controller<'_>) {
    let mut new_observations: Vec<(Position, Environment, bool)> = pyrust::vec::new!();
    let nearby = pyrust::clone!(builder.state.nearby_tiles);
    for pos in &nearby {
        let pos = *pos;
        let i = builder.idx(pos);
        let env = pyrust::unwrap!(ct.get_tile_env(pos));
        let bid = pyrust::unwrap!(ct.get_tile_building_id(pos));
        let env_changed = builder.env[i] != Some(env);
        let bld_changed = builder.building_ids[i] != bid;
        if pyrust::is_none!(builder.env[i]) {
            pyrust::vec::push_back!(builder.reflect_queue, i);
            let is_core =
                pyrust::is_some_and!(bid, |b| pyrust::unwrap!(ct.get_entity_type(Some(b)))
                    == EntityType::Core);
            pyrust::vec::push!(new_observations, (pos, env, is_core));
            if env != Environment::Wall {
                let py = pos.y;
                let px = pos.x;
                for dy in [-1, 0, 1] {
                    for dx in [-1, 0, 1] {
                        if dx == 0 && dy == 0 {
                            continue;
                        }
                        let nx = px + dx;
                        let ny = py + dy;
                        if !pyrust::vec::contains!((0..builder.state.width), &nx)
                            || !pyrust::vec::contains!((0..builder.state.height), &ny)
                        {
                            continue;
                        }
                        let ni = (ny as usize) * MAX_WIDTH + (nx as usize);
                        if builder.reach_parent[ni] != -1 {
                            pyrust::vec::push!(builder.reach_frontier, ni as i32);
                        }
                    }
                }
            }
        }
        builder.env[i] = Some(env);
        builder.building_ids[i] = bid;

        if bld_changed || env_changed {
            if pyrust::is_none!(bid) {
                apply_local_destroy(builder, pos);
            } else {
                _remove_topology(builder, pos, i);
                let bid_v = pyrust::unwrap!(bid);
                let (kind, team) = make_building(ct, bid_v);
                builder.building_kind[i] = Some(kind);
                builder.building_team[i] = Some(team);
                builder.hp[i] = pyrust::unwrap!(ct.get_hp(bid));
                builder.max_hp[i] = pyrust::unwrap!(ct.get_max_hp(bid));
                _add_topology(builder, ct, pos, bid_v, kind, team);
                _apply_post_transition(builder, pos, i, Some(env), "building_changed");
            }
            if let Some(bid_v) = bid
                && let Some(kind) = builder.building_kind[i]
                && let Some(team) = builder.building_team[i]
            {
                _update_turret_rays(builder, ct, pos, bid_v, kind, team);
            }
        } else if pyrust::is_some!(bid) {
            builder.hp[i] = pyrust::unwrap!(ct.get_hp(bid));
            builder.max_hp[i] = pyrust::unwrap!(ct.get_max_hp(bid));
        }

        _refresh_ore_set(builder, pos, Some(env));

        if pyrust::is_some!(bid) {
            let kind = builder.building_kind[i];
            let team = builder.building_team[i];
            pyrust::vec::push!(builder.nearby_buildings, pos);
            if builder.hp[i] < builder.max_hp[i] && team == Some(builder.state.my_team) {
                pyrust::vec::push!(builder.healable_buildings, pos);
            }

            if matches!(
                kind,
                Some(
                    EntityType::Conveyor
                        | EntityType::ArmouredConveyor
                        | EntityType::Bridge
                        | EntityType::Splitter
                )
            ) {
                let bid_v = pyrust::unwrap!(bid);
                let r = pyrust::unwrap!(ct.get_stored_resource(Some(bid_v)));
                let rid = pyrust::unwrap!(ct.get_stored_resource_id(Some(bid_v)));
                pyrust::vec::push_back!(builder.flow_history[i], (r, rid));
                while pyrust::len!(builder.flow_history[i]) > FLOW_HISTORY_LEN {
                    pyrust::vec::pop_front!(builder.flow_history[i]);
                }
            }
        }
    }

    if pyrust::is_none!(builder.symmetry) {
        _narrow_symmetry(builder, &new_observations);
    }
}

fn _narrow_symmetry(builder: &mut Builder, new_observations: &[(Position, Environment, bool)]) {
    let mut invalid: HashSet<Symmetry> = pyrust::set::new!();
    let candidates: Vec<Symmetry> = pyrust::collect!(pyrust::copied!(pyrust::iter!(
        builder.state.symmetry_candidates
    )));
    let w = builder.state.width;
    let h = builder.state.height;
    for sym in candidates {
        for &(pos, env, is_core) in new_observations {
            let m = sym.action(pos, w, h);
            let mi = (m.y as usize) * MAX_WIDTH + (m.x as usize);
            let mirror_env = builder.env[mi];
            let Some(mirror_env) = mirror_env else {
                continue;
            };
            let mirror_is_core = builder.building_kind[mi] == Some(EntityType::Core);
            if mirror_env != env || mirror_is_core != is_core {
                pyrust::set::add!(invalid, sym);
                break;
            }
        }
    }
    for sym in invalid {
        pyrust::set::remove!(builder.state.symmetry_candidates, &sym);
    }
}
