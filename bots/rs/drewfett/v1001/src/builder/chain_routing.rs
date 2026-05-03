//! Chain-laying for Ti and Ax harvester outputs.
//!
//! Two public entry points share a single one-step worker `extend_step`:
//!
//! - `extend_chain` — auto-pick target by resource (Ti -> `ti_sink`, Ax ->
//!   `ax_sink`). Used by ECON's chain-extension tasks.
//! - `extend_step` — picks an explicit target. Used by OFFENSE
//!   (`push_extend`) to point at the enemy core.
//!
//! Failures return `Err(TaskRejected)` so callers don't need their own
//! wrapper types.

use crate::config::DEBUG_LOG;
use std::collections::HashSet;

use cambc::{
    BuildExtra, Controller, ControllerApi, Direction, EntityType, Position, ResourceType, Team,
};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::algorithms::econ_astar::AstarStep;
use crate::builder::algorithms::greedy_route::greedy_route;
use crate::builder::helpers::{
    make_move, on_enemy_side, trace_upstream, try_move_with_road, try_place,
};
use crate::builder::tasks::rejected::TaskRejected;
use crate::util::debug::{Scope, debug, line};
use crate::util::directions::{DIR4, DIR8, delta_to_dir, get_direction_object, is_cardinal};
use crate::util::metrics::{chebyshev, reachable_path_end};
use crate::util::posint::idx_of;
use crate::util::visualiser::auto_wrap_position;

/// Cap on upstream BFS size in `resource_at`.
const _UPSTREAM_MAX_NODES_RES: usize = 80;

/// Infer which resource a chain starting at `pos` carries. Returns None
/// if it can't be determined — caller must NOT silently default to Ti,
/// because routing Ax as Ti sends raw Ax to the core where it's destroyed.
#[must_use]
pub fn resource_at(builder: &Builder, pos: Position) -> Option<ResourceType> {
    let ax_adj = pyrust::vec::contains!(builder.ax_harvester_adjacent, &idx_of(pos));
    let ti_adj = pyrust::vec::contains!(builder.ti_harvester_adjacent, &idx_of(pos));
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
        if pyrust::vec::contains!(builder.ti_harvester_adjacent, &idx_of(p)) {
            seen_ti = true;
        }
        if pyrust::vec::contains!(builder.ax_harvester_adjacent, &idx_of(p)) {
            seen_ax = true;
        }
        let pi = idx_of(p) as usize;
        for &(r, _rid) in &builder.flow_history[pi] {
            match r {
                Some(ResourceType::Titanium) => seen_ti = true,
                Some(ResourceType::RawAxionite | ResourceType::RefinedAxionite) => {
                    seen_ax = true;
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
    let hist = &builder.flow_history[idx_of(landing) as usize];
    let mut saw_ti = false;
    let mut has_ax = false;
    for &(r, _rid) in hist {
        match r {
            Some(ResourceType::Titanium) => saw_ti = true,
            Some(ResourceType::RawAxionite | ResourceType::RefinedAxionite) => has_ax = true,
            _ => {}
        }
    }
    if !saw_ti || has_ax {
        return;
    }
    if DEBUG_LOG {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("landing"),
            auto_wrap_position(landing)
        );
        debug("retarget foundry to junction at {landing}", args);
    }
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
    if pyrust::vec::is_empty!(path) {
        return false;
    }

    // Read cached building state instead of `ct.get_tile_building_id` +
    // `ct.get_entity_type` + `ct.get_team` (each a Python-boundary call).
    let start_idx = idx_of(start_pos) as usize;
    let bid = builder.building_ids[start_idx];
    let entity_type: Option<EntityType> = builder.building_kind[start_idx];
    let entity_team: Option<Team> = builder.building_team[start_idx];

    // pyrust translates `.is_some()` literally; Python Optional[T] just
    // tests `is None` directly. The `entity_team != Some(my_team)` check
    // already covers None (None != Some(_) is true), so the explicit
    // is_some() filter is wrong and unnecessary — drop it.
    if entity_type == Some(EntityType::Road)
        && pyrust::is_some!(entity_team)
        && entity_team != Some(builder.state.my_team)
        && pyrust::unwrap!(ct.can_fire(start_pos))
    {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("pos"),
                auto_wrap_position(start_pos)
            );
            debug("chain: fire on enemy road at {pos}", args);
        }
        pyrust::unwrap!(ct.fire(start_pos));
        return true;
    }

    let mut direction: Option<Direction> = None;
    if start_pos.distance_squared(builder.my_core) <= 5
        && path[pyrust::len!(path) - 1] == builder.my_core
    {
        for d in DIR4 {
            if start_pos.add(d).distance_squared(builder.my_core) <= 2 {
                direction = Some(d);
                break;
            }
        }
    } else {
        direction = get_direction_object(start_pos, path[1]);
    }

    if entity_type == Some(EntityType::Conveyor)
        && pyrust::unwrap!(ct.get_direction(bid))
            == pyrust::unwrap_or!(direction, Direction::Centre)
    {
        return true;
    }
    if entity_type == Some(EntityType::Bridge)
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

    let next_idx = idx_of(next_pos) as usize;
    let destination_building = builder.building_ids[next_idx];
    let destination_team = builder.building_team[next_idx];
    let destination_is_marker = builder.building_kind[next_idx] == Some(EntityType::Marker);

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
    if pyrust::vec::is_empty!(existing_path) {
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
    // v56-style: try greedy_route (Bresenham + 2 L-shapes, O(N)) first.
    // Falls back to A* only when all three greedy attempts hit walls
    // unbridgeable. Greedy is ~10x cheaper per call and yields shorter
    // paths in most open-map cases.
    let greedy_path = {
        let _g = Scope::new_timed("conv_greedy");
        greedy_route(builder, start, target, resource)
    };
    let mut path: Vec<Position>;
    if pyrust::is_some!(greedy_path) {
        path = pyrust::unwrap!(greedy_path);
    } else {
        let _g = Scope::new_timed("conv_astar_fallback");
        let astar_budget_us: u64 = 1500;
        let step = if is_ax {
            builder.ax_conv_astar(ct, start, target, resource, astar_budget_us)
        } else {
            builder.ti_conv_astar(ct, start, target, resource, astar_budget_us)
        };
        match step {
            AstarStep::Done(p) => {
                path = p;
            }
            AstarStep::Pending => {
                return Some(TaskRejected::new("A* in progress, will resume next turn"));
            }
            AstarStep::NoPath => {
                return Some(TaskRejected::from_string(format!(
                    "greedy {resource} {start:?}->{target:?}: no Bresenham/L route, A* exhausted"
                )));
            }
        }
    }

    let colour: (i32, i32, i32) = if is_ax { (200, 0, 255) } else { (80, 160, 255) };
    for i in 0..(pyrust::len!(path) - 1) {
        line(ct, path[i], path[i + 1], colour.0, colour.1, colour.2);
    }

    let existing_set: HashSet<Position> =
        pyrust::collect!(pyrust::copied!(pyrust::iter!(existing_path)));
    let mut path_start_index: usize = 0;
    for (i, pos) in pyrust::enumerate!(pyrust::iter!(path)) {
        if pyrust::vec::contains!(existing_set, pos) {
            start = *pos;
            path_start_index = i;
        }
    }
    {
        let mut _new_path: Vec<Position> = pyrust::vec::new!();
        for _pi in path_start_index..pyrust::len!(path) {
            pyrust::vec::push!(_new_path, path[_pi]);
        }
        path = _new_path;
    }

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
/// resource and picks the right sink. Ti -> `ti_sink`, Ax -> `ax_sink`.
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
