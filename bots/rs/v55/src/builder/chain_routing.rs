//! Chain-laying for Ti and Ax harvester outputs.
//!
//! Two public entry points share a single one-step worker `extend_step`:
//!
//! - `extend_chain` — auto-pick target by resource (Ti -> ti_sink, Ax ->
//!   ax_sink). Used by ECON's chain-extension tasks.
//! - `extend_step` — picks an explicit target. Used by OFFENSE
//!   (`push_extend`) to point at the enemy core.
//!
//! Failures return `Err(TaskRejected)` so callers don't need their own
//! wrapper types.

use std::collections::HashSet;

use cambc::{BuildExtra, Controller, ControllerApi, Direction, EntityType, Position, ResourceType};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::helpers::{
    make_move, on_enemy_side, trace_upstream, try_move_with_road, try_place,
};
use crate::builder::tasks::rejected::TaskRejected;
use crate::util::constants::MAX_WIDTH;
use crate::util::debug::{Scope, debug, line};
use crate::util::directions::{DIR4, DIR8, delta_to_dir, get_direction_object, is_cardinal};
use crate::util::metrics::{chebyshev, reachable_path_end};
use crate::util::visualiser::auto_wrap_position;

/// Cap on upstream BFS size in `resource_at`.
const _UPSTREAM_MAX_NODES_RES: usize = 80;

/// Infer which resource a chain starting at `pos` carries. Returns None
/// if it can't be determined — caller must NOT silently default to Ti,
/// because routing Ax as Ti sends raw Ax to the core where it's destroyed.
pub fn resource_at(builder: &Builder, pos: Position) -> Option<ResourceType> {
    let ax_adj = pyrust::vec::contains!(builder.ax_harvester_adjacent, &pos);
    let ti_adj = pyrust::vec::contains!(builder.ti_harvester_adjacent, &pos);
    if ax_adj && !ti_adj {
        return Some(ResourceType::RawAxionite);
    }
    if ti_adj && !ax_adj {
        return Some(ResourceType::Titanium);
    }

    let mut seen_ti = false;
    let mut seen_ax = false;
    let mut visited: HashSet<Position> = pyrust::set::new!();
    pyrust::set::add!(visited, pos);
    let mut stack: Vec<Position> = vec![pos];
    while let Some(p) = pyrust::vec::pop!(stack) {
        if pyrust::len!(visited) > _UPSTREAM_MAX_NODES_RES {
            break;
        }
        if pyrust::vec::contains!(builder.ti_harvester_adjacent, &p) {
            seen_ti = true;
        }
        if pyrust::vec::contains!(builder.ax_harvester_adjacent, &p) {
            seen_ax = true;
        }
        let pi = (p.y as usize) * MAX_WIDTH + (p.x as usize);
        for &(r, _rid) in &builder.flow_history[pi] {
            match r {
                Some(ResourceType::Titanium) => seen_ti = true,
                Some(ResourceType::RawAxionite) | Some(ResourceType::RefinedAxionite) => {
                    seen_ax = true
                }
                _ => {}
            }
        }
        if seen_ti && seen_ax {
            return None;
        }
        for &u in &builder.in_edges[pi] {
            if pyrust::vec::contains!(visited, &u) {
                continue;
            }
            pyrust::set::add!(visited, u);
            pyrust::vec::push!(stack, u);
        }
    }

    if seen_ax && !seen_ti {
        return Some(ResourceType::RawAxionite);
    }
    if seen_ti && !seen_ax {
        return Some(ResourceType::Titanium);
    }
    None
}

/// If an Ax chain segment we just placed lands on a pre-existing friendly
/// Ti conveyor with pure-Ti flow history, retarget `foundry_target` to that
/// tile — it's the natural junction.
fn _retarget_foundry_to_junction(builder: &mut Builder, landing: Position) {
    if builder.foundry_target == Some(landing) {
        return;
    }
    let kind = builder.kind_at(landing);
    let team = builder.team_at(landing);
    if !matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
    ) {
        return;
    }
    if team != Some(builder.state.my_team) {
        return;
    }
    let hist = &builder.flow_history[(landing.y as usize) * MAX_WIDTH + (landing.x as usize)];
    let mut saw_ti = false;
    let mut has_ax = false;
    for &(r, _rid) in hist {
        match r {
            Some(ResourceType::Titanium) => saw_ti = true,
            Some(ResourceType::RawAxionite) | Some(ResourceType::RefinedAxionite) => has_ax = true,
            _ => {}
        }
    }
    if !saw_ti || has_ax {
        return;
    }
    let mut args = Map::new();
    pyrust::dict::insert!(args, pyrust::to_string!("landing"), auto_wrap_position(landing));
    debug("retarget foundry to junction at {landing}", args);
    builder.foundry_target = Some(landing);
}

/// Step off `build_pos` if needed, then place a sentinel facing
/// `target_pos`.
fn _clear_with_turret(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    build_pos: Position,
    target_pos: Position,
) -> bool {
    if build_pos == builder.state.my_pos {
        for d in DIR8 {
            if pyrust::unwrap!(ct.can_move(d)) {
                pyrust::unwrap!(ct.move_(d));
                break;
            }
        }
    }
    if build_pos == pyrust::unwrap!(ct.get_position(None)) {
        for d in DIR8 {
            let pos = pyrust::unwrap!(ct.get_position(None)).add(d);
            if try_move_with_road(builder, ct, pos) {
                break;
            }
        }
    }
    let dx = target_pos.x - build_pos.x;
    let dy = target_pos.y - build_pos.y;
    let Some(direction) = delta_to_dir(dx, dy) else {
        return false;
    };
    try_place(
        builder,
        ct,
        EntityType::Sentinel,
        build_pos,
        BuildExtra::Direction(direction),
        true,
    )
}

/// Place one conveyor / bridge at `start_pos` that advances along `path`.
/// Returns True iff an action was taken.
fn _lay_segment(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    start_pos: Position,
    path: &[Position],
) -> bool {
    if path.is_empty() {
        return false;
    }

    let bid = pyrust::unwrap!(ct.get_tile_building_id(start_pos));
    let entity_type = pyrust::map!(bid, |b| pyrust::unwrap!(ct.get_entity_type(Some(b))));

    if let Some(EntityType::Road) = entity_type
        && let Some(b) = bid
        && pyrust::unwrap!(ct.get_team(Some(b))) != builder.state.my_team
        && pyrust::unwrap!(ct.can_fire(start_pos))
    {
        let mut args = Map::new();
        pyrust::dict::insert!(args, pyrust::to_string!("pos"), auto_wrap_position(start_pos));
        debug("chain: fire on enemy road at {pos}", args);
        pyrust::unwrap!(ct.fire(start_pos));
        return true;
    }

    let mut direction: Option<Direction> = None;
    if start_pos.distance_squared(builder.my_core) <= 5 && path[pyrust::len!(path) - 1] == builder.my_core {
        for d in DIR4 {
            if start_pos.add(d).distance_squared(builder.my_core) <= 2 {
                direction = Some(d);
                break;
            }
        }
    } else {
        direction = get_direction_object(start_pos, path[1]);
    }

    if let Some(EntityType::Conveyor) = entity_type
        && pyrust::unwrap!(ct.get_direction(bid)) == pyrust::unwrap_or!(direction, Direction::Centre)
    {
        return true;
    }
    if let Some(EntityType::Bridge) = entity_type
        && let Some(b) = bid
    {
        let bridge_output = pyrust::unwrap!(ct.get_bridge_target(b));
        if !pyrust::unwrap!(ct.is_in_vision(bridge_output)) || builder.is_buildable(bridge_output) {
            return true;
        }
    }

    let next_pos = path[1];
    if !pyrust::unwrap!(ct.is_in_vision(next_pos)) {
        let target = reachable_path_end(path, start_pos, 3);
        return try_place(
            builder,
            ct,
            EntityType::Bridge,
            start_pos,
            BuildExtra::Position(target),
            true,
        );
    }

    let destination_building = pyrust::unwrap!(ct.get_tile_building_id(next_pos));
    let destination_team = pyrust::map!(destination_building, |b| pyrust::unwrap!(ct.get_team(Some(b))));
    let destination_is_marker = pyrust::unwrap_or!(pyrust::map!(destination_building, |b| ct.get_entity_type(Some(b)).unwrap() == EntityType::Marker), false);

    if let Some(d) = direction
        && is_cardinal(d)
        && (pyrust::is_none!(destination_building)
            || destination_team == Some(builder.state.my_team)
            || destination_is_marker)
    {
        let ok = try_place(
            builder,
            ct,
            EntityType::Conveyor,
            start_pos,
            BuildExtra::Direction(d),
            true,
        );
        if ok {
            line(ct, start_pos, next_pos, 255, 255, 0);
            _retarget_foundry_to_junction(builder, next_pos);
        }
        return ok;
    }

    let pending_bridge = reachable_path_end(path, start_pos, 3);
    if builder.is_enemy_building(pending_bridge) {
        _clear_with_turret(builder, ct, start_pos, pending_bridge);
        return false;
    }
    if try_place(
        builder,
        ct,
        EntityType::Bridge,
        start_pos,
        BuildExtra::Position(pending_bridge),
        true,
    ) {
        _retarget_foundry_to_junction(builder, pending_bridge);
        return true;
    }
    false
}

/// Lay one segment toward `target` and/or take one step toward it.
pub fn extend_step(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    mut start: Position,
    target: Position,
    resource: ResourceType,
) -> Option<TaskRejected> {
    if start == target {
        return Some(TaskRejected::from_string(format!(
            "start == target ({start:?})"
        )));
    }
    if chebyshev(start, target) <= 1 && target == builder.my_core {
        return Some(TaskRejected::from_string(format!(
            "{start:?} is already adjacent to core; nothing to lay"
        )));
    }

    let current_pos = builder.state.my_pos;
    let existing_path = trace_upstream(builder, start);
    if existing_path.is_empty() {
        return Some(TaskRejected::from_string(format!(
            "no upstream chain reaches {start:?}"
        )));
    }

    if !builder.is_passable(start) {
        if pyrust::len!(existing_path) > 1 {
            start = existing_path[pyrust::len!(existing_path) - 2];
        } else {
            return Some(TaskRejected::from_string(format!(
                "{start:?} is unpassable and no upstream fallback"
            )));
        }
    }

    let is_ax = matches!(
        resource,
        ResourceType::RawAxionite | ResourceType::RefinedAxionite
    );
    let path = {
        let _g = Scope::new_timed("conv_astar");
        if is_ax {
            builder.ax_conv_astar(ct, start, target, resource)
        } else {
            builder.ti_conv_astar(ct, start, target, resource)
        }
    };
    let Some(mut path) = path else {
        let fail = if is_ax {
            builder.ax_conv_search.last_fail_reason.clone()
        } else {
            builder.conv_search.last_fail_reason.clone()
        };
        return Some(TaskRejected::from_string(format!(
            "A* {resource} {start:?}->{target:?}: {fail}"
        )));
    };

    let colour: (i32, i32, i32) = if is_ax { (200, 0, 255) } else { (80, 160, 255) };
    for i in 0..(pyrust::len!(path) - 1) {
        line(ct, path[i], path[i + 1], colour.0, colour.1, colour.2);
    }

    let existing_set: HashSet<Position> = pyrust::collect!(pyrust::copied!(pyrust::iter!(existing_path)));
    let mut path_start_index: usize = 0;
    for (i, pos) in pyrust::enumerate!(pyrust::iter!(path)) {
        if pyrust::vec::contains!(existing_set, pos) {
            start = *pos;
            path_start_index = i;
        }
    }
    path = path.split_off(path_start_index);

    let mut did_something = false;
    if chebyshev(current_pos, start) <= 1 {
        if pyrust::len!(path) < 2 {
            return Some(TaskRejected::from_string(format!(
                "in range of {start:?} but A* path is empty"
            )));
        }
        if _lay_segment(builder, ct, start, &path) {
            did_something = true;
        }
    }
    if make_move(builder, ct, start) {
        did_something = true;
    }
    if !did_something {
        return Some(TaskRejected::from_string(format!(
            "could neither lay at {start:?} nor move toward {target:?}"
        )));
    }
    None
}

/// Auto-target wrapper around `extend_step`: classifies the chain's
/// resource and picks the right sink. Ti -> ti_sink, Ax -> ax_sink.
pub fn extend_chain(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    start: Position,
) -> Option<TaskRejected> {
    if on_enemy_side(builder, start) {
        return Some(TaskRejected::from_string(format!(
            "{start:?} is enemy-side; deferring to OFFENSE"
        )));
    }
    let resource = resource_at(builder, start);
    let Some(resource) = resource else {
        return Some(TaskRejected::from_string(format!(
            "cannot classify resource at {start:?}"
        )));
    };
    if resource == ResourceType::RawAxionite {
        let target = builder.ax_sink;
        let Some(target) = target else {
            return Some(TaskRejected::from_string(format!(
                "chain at {start:?} is Ax but ax_sink is None"
            )));
        };
        return extend_step(builder, ct, start, target, resource);
    }
    let target = pyrust::unwrap_or!(builder.ti_sink, builder.my_core);
    extend_step(builder, ct, start, target, resource)
}
