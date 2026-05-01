use std::collections::HashSet;

use cambc::{Controller, ControllerApi, Direction, EntityType, Environment, GameConstants, Position};

use crate::builder::Builder;
use crate::building::{Building, make_building};
use crate::util::constants::{FLOW_HISTORY_LEN, INF, MAX_WIDTH, ROAD_COST};
use crate::util::directions::DIR8;
use crate::util::symmetry::Symmetry;

/// Structural output tiles of `bld` placed at `pos`. One entry for a
/// conveyor / armoured conveyor / bridge; three for a splitter; empty for
/// non-routing buildings (which participate via separate sets).
fn _edge_targets(pos: Position, bld: Building) -> Vec<Position> {
    match bld {
        Building::Conveyor { direction: d, .. }
        | Building::ArmouredConveyor { direction: d, .. } => {
            vec![pos.add(d)]
        }
        Building::Bridge { target: t, .. } => vec![t],
        Building::Splitter { direction: d, .. } => {
            vec![
                pos.add(d),
                pos.add(rotate_right(rotate_right(d))),
                pos.add(rotate_left(rotate_left(d))),
            ]
        }
        _ => Vec::new(),
    }
}

const fn rotate_right(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::Northeast,
        Direction::Northeast => Direction::East,
        Direction::East => Direction::Southeast,
        Direction::Southeast => Direction::South,
        Direction::South => Direction::Southwest,
        Direction::Southwest => Direction::West,
        Direction::West => Direction::Northwest,
        Direction::Northwest => Direction::North,
        Direction::Centre => Direction::Centre,
    }
}

const fn rotate_left(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::Northwest,
        Direction::Northeast => Direction::North,
        Direction::East => Direction::Northeast,
        Direction::Southeast => Direction::East,
        Direction::South => Direction::Southeast,
        Direction::Southwest => Direction::South,
        Direction::West => Direction::Southwest,
        Direction::Northwest => Direction::West,
        Direction::Centre => Direction::Centre,
    }
}

pub fn _remove_topology(builder: &mut Builder, pos: Position, i: usize) {
    let old_bld = builder.buildings[i];
    if let Some(b) = old_bld
        && b.team() == builder.state.my_team
    {
        for t in _edge_targets(pos, b) {
            if !builder.in_bounds(t) {
                continue;
            }
            let ti = builder.idx(t);
            if builder.in_edges[ti].contains(&pos) {
                builder.in_edges[ti].retain(|&p| p != pos);
                builder._on_in_edge_removed(t, pos);
                builder._check_multi_input(t);
                builder._check_dangling(t, &format!("edge_removed src={:?}", pos));
            }
        }
        builder.out_edges[i] = Vec::new();
        builder._on_out_edges_changed(pos);
    }
    match old_bld {
        Some(Building::Foundry { team }) if team == builder.state.my_team => {
            builder.my_foundries.remove(&pos);
            builder._bump_foundry(pos, -1);
        }
        Some(Building::Harvester { team }) if team == builder.state.my_team => {
            builder.my_harvesters.remove(&pos);
            let env = builder.env[i];
            if env == Some(Environment::OreAxionite) {
                builder._bump_ax_harv(pos, -1);
            } else if env == Some(Environment::OreTitanium) {
                builder._bump_ti_harv(pos, -1);
            }
        }
        Some(Building::Harvester { .. }) => {
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

pub fn _add_topology(builder: &mut Builder, pos: Position, bld: Building) {
    let i = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
    if builder.reach_parent[i] == -1 {
        builder.reach_parent[i] = i as i32;
        builder.reach_frontier.push(i as i32);
    }
    if bld.team() == builder.state.my_team {
        let targets = _edge_targets(pos, bld);
        if !targets.is_empty() {
            let mut outs: Vec<Position> = Vec::new();
            for t in targets {
                if builder.in_bounds(t) {
                    let ti = builder.idx(t);
                    builder.in_edges[ti].push(pos);
                    outs.push(t);
                    builder._check_multi_input(t);
                }
            }
            let was_ti_in = builder.ti_upstream.contains(&pos);
            let was_ax_in = builder.ax_upstream.contains(&pos);
            let pi = (pos.y as usize) * MAX_WIDTH + (pos.x as usize);
            builder.out_edges[pi] = outs.clone();
            builder._on_out_edges_changed(pos);
            for t in &outs {
                let ti = builder.idx(*t);
                if was_ti_in && builder.ti_upstream.contains(&pos) {
                    builder._ti_in_count[ti] += 1;
                    builder._reeval_ti_upstream(*t);
                }
                if was_ax_in && builder.ax_upstream.contains(&pos) {
                    builder._ax_in_count[ti] += 1;
                    builder._reeval_ax_upstream(*t);
                }
                builder._check_dangling(*t, &format!("edge_added src={:?}", pos));
            }
            return;
        }
    }
    match bld {
        Building::Foundry { team } if team == builder.state.my_team => {
            builder.my_foundries.insert(pos);
            builder._bump_foundry(pos, 1);
        }
        Building::Harvester { team } if team == builder.state.my_team => {
            builder.my_harvesters.insert(pos);
            let idx = builder.idx(pos);
            match builder.env[idx] {
                Some(Environment::OreAxionite) => builder._bump_ax_harv(pos, 1),
                Some(Environment::OreTitanium) => builder._bump_ti_harv(pos, 1),
                _ => {}
            }
        }
        Building::Harvester { .. } => {
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
///
/// Called from `update_vision` (start-of-turn observation) and from
/// `apply_local_destroy` (mid-turn `ct.destroy` invariant fix-up).
fn _apply_post_transition(
    builder: &mut Builder,
    pos: Position,
    i: usize,
    env: Option<Environment>,
    trigger: &str,
) {
    let bld = builder.buildings[i];
    _update_cost(builder, i, env, bld);
    builder.update_pnb(i);
    builder._check_dangling(pos, trigger);
    let feeders: Vec<Position> = builder.in_edges[i].clone();
    for feeder in &feeders {
        let fb = builder.buildings[(feeder.y as usize) * MAX_WIDTH + (feeder.x as usize)];
        if matches!(fb, Some(Building::Splitter { .. })) {
            let siblings: Vec<Position> =
                builder.out_edges[(feeder.y as usize) * MAX_WIDTH + (feeder.x as usize)].clone();
            for sib in siblings {
                if sib != pos {
                    builder._check_dangling(sib, "splitter_sibling");
                }
            }
        }
    }
}

/// Mid-turn invariant fix-up after `ct.destroy(pos)`. The bot's
/// belief (cost_grid, in_edges/out_edges, hp, harvester adjacency,
/// upstream sets, dangling) is otherwise frozen at start-of-turn —
/// a subsequent `try_move_with_road` or bugnav read on the destroyed
/// tile would see stale data. This mirrors the destroy path in
/// `update_vision`: `_remove_topology` first, then clear the slot,
/// then run the shared post-transition work.
///
/// Safe to call after issuing `ct.destroy(pos)` regardless of what
/// was there (friendly conveyor / barrier / road / armoured / etc.).
pub fn apply_local_destroy(builder: &mut Builder, pos: Position) {
    let i = builder.idx(pos);
    _remove_topology(builder, pos, i);
    builder.buildings[i] = None;
    builder.hp[i] = 0;
    builder.max_hp[i] = 0;
    let env = builder.env[i];
    _apply_post_transition(builder, pos, i, env, "local_destroy");
}

pub fn _update_cost(
    builder: &mut Builder,
    i: usize,
    terrain: Option<Environment>,
    bld: Option<Building>,
) {
    let mut routing_extra: i32 = 0;
    let cost: i32;
    let buildable: bool;
    if terrain == Some(Environment::Wall) {
        cost = INF;
        buildable = false;
    } else if let Some(b) = bld {
        match b {
            Building::Road { team } if team == builder.state.my_team => {
                cost = 1;
                buildable = true;
            }
            Building::Road { .. } => {
                cost = 1;
                buildable = true;
                routing_extra = 4;
            }
            Building::Marker { .. } => {
                cost = ROAD_COST;
                buildable = true;
            }
            Building::Conveyor { .. }
            | Building::Splitter { .. }
            | Building::ArmouredConveyor { .. }
            | Building::Bridge { .. } => {
                cost = 1;
                buildable = false;
            }
            Building::Core { team } if team == builder.state.my_team => {
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
    bld: Building,
) {
    let my_team = builder.state.my_team;
    match bld {
        Building::Launcher { team } if team != my_team => {
            for d in DIR8 {
                let n = pos.add(d);
                if builder.in_bounds(n) {
                    builder.adjacent_to_enemy_launcher.insert(n);
                }
            }
        }
        Building::Gunner { team, direction: d } if team != my_team => {
            let mut ray = pos;
            for _ in 0..3 {
                ray = ray.add(d);
                if pos.distance_squared(ray) > GameConstants::GUNNER_VISION_RADIUS_SQ {
                    break;
                }
                if builder.in_bounds(ray) {
                    builder.enemy_turret_ray_tiles.insert(ray);
                }
            }
        }
        Building::Sentinel { team, direction: d } if team != my_team => {
            for tile in ct
                .get_attackable_tiles_from(pos, d, EntityType::Sentinel)
                .unwrap()
            {
                builder.enemy_turret_ray_tiles.insert(tile);
            }
        }
        Building::Gunner { team, direction: d } if team == my_team => {
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
                builder.friendly_turret_ray_tiles.insert(ray);
                if builder.get_building(ray).is_some() {
                    break;
                }
            }
        }
        Building::Sentinel { team, direction: d } if team == my_team => {
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
                builder.friendly_turret_ray_tiles.insert(ray);
                for hd in DIR8 {
                    let h = ray.add(hd);
                    if builder.in_bounds(h) {
                        builder.friendly_turret_ray_tiles.insert(h);
                    }
                }
                if builder.get_building(ray).is_some() {
                    break;
                }
            }
        }
        _ => {}
    }
}

pub fn update_vision(builder: &mut Builder, ct: &mut Controller<'_>) {
    let mut new_observations: Vec<(Position, Environment, bool)> = Vec::new();
    let nearby = builder.state.nearby_tiles.clone();
    for pos in &nearby {
        let pos = *pos;
        let i = builder.idx(pos);
        let env = ct.get_tile_env(pos).unwrap();
        let bid = ct.get_tile_building_id(pos).unwrap();
        let env_changed = builder.env[i] != Some(env);
        let bld_changed = builder.building_ids[i] != bid;
        if builder.env[i].is_none() {
            builder.reflect_queue.push_back(i);
            let is_core =
                bid.is_some_and(|b| ct.get_entity_type(Some(b)).unwrap() == EntityType::Core);
            new_observations.push((pos, env, is_core));
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
                        if !(0..builder.state.width).contains(&nx)
                            || !(0..builder.state.height).contains(&ny)
                        {
                            continue;
                        }
                        let ni = (ny as usize) * MAX_WIDTH + (nx as usize);
                        if builder.reach_parent[ni] != -1 {
                            builder.reach_frontier.push(ni as i32);
                        }
                    }
                }
            }
        }
        builder.env[i] = Some(env);
        builder.building_ids[i] = bid;

        if bld_changed || env_changed {
            if bid.is_none() {
                apply_local_destroy(builder, pos);
            } else {
                _remove_topology(builder, pos, i);
                let bld = make_building(ct, bid.unwrap());
                builder.buildings[i] = Some(bld);
                builder.hp[i] = ct.get_hp(bid).unwrap();
                builder.max_hp[i] = ct.get_max_hp(bid).unwrap();
                _add_topology(builder, pos, bld);
                _apply_post_transition(builder, pos, i, Some(env), "building_changed");
            }
            if let Some(bld) = builder.buildings[i] {
                _update_turret_rays(builder, ct, pos, bld);
            }
        } else if bid.is_some() {
            builder.hp[i] = ct.get_hp(bid).unwrap();
            builder.max_hp[i] = ct.get_max_hp(bid).unwrap();
        }

        if bid.is_some() {
            let bld = builder.buildings[i];
            builder.nearby_buildings.push(pos);
            if let Some(b) = bld
                && builder.hp[i] < builder.max_hp[i]
                && b.team() == builder.state.my_team
            {
                builder.healable_buildings.push(pos);
            }

            if matches!(
                bld,
                Some(
                    Building::Conveyor { .. }
                        | Building::ArmouredConveyor { .. }
                        | Building::Bridge { .. }
                        | Building::Splitter { .. }
                )
            ) {
                let bid_v = bid.unwrap();
                let r = ct.get_stored_resource(Some(bid_v)).unwrap();
                let rid = ct.get_stored_resource_id(Some(bid_v)).unwrap();
                builder.flow_history[i].push_back((r, rid));
                while builder.flow_history[i].len() > FLOW_HISTORY_LEN {
                    builder.flow_history[i].pop_front();
                }
            }
        }
    }

    if builder.symmetry.is_none() {
        _narrow_symmetry(builder, &new_observations);
    }
}

fn _narrow_symmetry(builder: &mut Builder, new_observations: &[(Position, Environment, bool)]) {
    let mut invalid: HashSet<Symmetry> = HashSet::new();
    let candidates: Vec<Symmetry> = builder.state.symmetry_candidates.iter().copied().collect();
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
            let mirror_is_core = matches!(builder.buildings[mi], Some(Building::Core { .. }));
            if mirror_env != env || mirror_is_core != is_core {
                invalid.insert(sym);
                break;
            }
        }
    }
    for sym in invalid {
        builder.state.symmetry_candidates.remove(&sym);
    }
}
