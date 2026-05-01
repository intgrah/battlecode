//! Translation of `bots/intgrah/v54.7.9/builder/helpers.py`.

use std::collections::HashSet;

use cambc::{
    BuildExtra, Controller, ControllerApi, Direction, EntityType, Environment, Position,
    ResourceType,
};
use serde_json::Map;

use crate::builder::Builder;
use crate::util::constants::{MAX_WIDTH, base_cost};
use crate::util::debug::{Scope, debug as log};
use crate::util::directions::{DIR4, DIR8, delta_to_dir};
use crate::util::metrics::{chebyshev, claims_by_proximity, manhattan};
use crate::util::visualiser::auto_wrap_position;

/// Return True iff this call actually issued a move. 'Already at target'
/// and 'no plan' both return False — neither advances the builder, so the
/// caller shouldn't treat the turn as productive.
pub fn make_move(builder: &mut Builder, ct: &mut Controller<'_>, target: Position) -> bool {
    if builder.state.my_pos == target {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
        log("make_move: already on target {target}", args);
        return false;
    }
    let next_move = builder.bugnav_step(target);
    let Some(next_move) = next_move else {
        if move_random(builder, ct) {
            let mut args = Map::new();
            args.insert(
                pyrust::to_string!("start"),
                auto_wrap_position(builder.state.my_pos),
            );
            args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
            log(
                "make_move: bugnav stuck, took random step {start}->{target}",
                args,
            );
            return true;
        }
        let mut args = Map::new();
        args.insert(
            pyrust::to_string!("start"),
            auto_wrap_position(builder.state.my_pos),
        );
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
        log(
            "make_move: FAILED {start}->{target} (bugnav: no plan, random step also blocked)",
            args,
        );
        return false;
    };
    let mut args = Map::new();
    args.insert(
        pyrust::to_string!("start"),
        auto_wrap_position(builder.state.my_pos),
    );
    args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
    args.insert(pyrust::to_string!("next"), auto_wrap_position(next_move));
    log("make_move: bugnav {start}->{target} step {next}", args);
    try_move_with_road(builder, ct, next_move)
}

/// Like `make_move`, but if `target` itself is impassable, routes to the
/// closest passable cardinal of `target` instead.
pub fn make_move_or_adjacent(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    target: Position,
) -> bool {
    if builder.is_passable(target) {
        return make_move(builder, ct, target);
    }
    let mut best: Option<Position> = None;
    let mut best_d: i32 = 1 << 30;
    for d in DIR4 {
        let c = target.add(d);
        if !builder.in_bounds(c) || !builder.is_passable(c) {
            continue;
        }
        let cd = chebyshev(builder.state.my_pos, c);
        if cd < best_d {
            best_d = cd;
            best = Some(c);
        }
    }
    let Some(best) = best else {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
        log(
            "make_move_or_adjacent: {target} impassable AND no passable cardinal",
            args,
        );
        return false;
    };
    if builder.state.my_pos == best {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
        args.insert(pyrust::to_string!("pos"), auto_wrap_position(builder.state.my_pos));
        log(
            "make_move_or_adjacent: already adjacent to {target} (at {pos})",
            args,
        );
        return false;
    }
    let mut args = Map::new();
    args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
    args.insert(pyrust::to_string!("adj"), auto_wrap_position(best));
    log(
        "make_move_or_adjacent: {target} impassable, routing to cardinal {adj}",
        args,
    );
    make_move(builder, ct, best)
}

pub fn try_move_dir(ct: &mut Controller<'_>, d: Direction) -> bool {
    if pyrust::unwrap!(ct.can_move(d)) {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("dir"), serde_json::Value::String(format!("{d}")));
        log("try_move_dir: moving {dir}", args);
        pyrust::unwrap!(ct.move_(d));
        return true;
    }
    false
}

pub fn try_move_to(builder: &mut Builder, ct: &mut Controller<'_>, target_pos: Position) -> bool {
    let dx = target_pos.x - builder.state.my_pos.x;
    let dy = target_pos.y - builder.state.my_pos.y;
    let Some(d) = delta_to_dir(dx, dy) else {
        return false;
    };
    if pyrust::unwrap!(ct.can_move(d)) {
        let mut args = Map::new();
        args.insert(
            pyrust::to_string!("start"),
            auto_wrap_position(builder.state.my_pos),
        );
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
        args.insert(pyrust::to_string!("dir"), serde_json::Value::String(format!("{d}")));
        log("try_move_to: {start}->{target} dir {dir}", args);
        let hx = (dx > 0) as i32 - (dx < 0) as i32;
        let hy = (dy > 0) as i32 - (dy < 0) as i32;
        builder.explore_heading = Some((hx, hy));
        pyrust::unwrap!(ct.move_(d));
        return true;
    }
    false
}

pub fn try_move_with_road(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    target_pos: Position,
) -> bool {
    if builder.get_cost(target_pos) > 1 && pyrust::unwrap!(ct.can_build_road(target_pos)) {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
        args.insert(
            pyrust::to_string!("cost"),
            serde_json::Value::Number(serde_json::Number::from(builder.get_cost(target_pos))),
        );
        log(
            "try_move_with_road: paving road at {target} (cost={cost} > 1)",
            args,
        );
        pyrust::unwrap!(ct.build_road(target_pos));
    }
    try_move_to(builder, ct, target_pos)
}

pub fn try_attack(ct: &mut Controller<'_>, pos: Position) -> bool {
    if pyrust::unwrap!(ct.can_fire(pos)) {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("pos"), auto_wrap_position(pos));
        log("try_attack: firing on {pos}", args);
        pyrust::unwrap!(ct.fire(pos));
        return true;
    }
    false
}

pub fn ti_needed(builder: &Builder, etype: EntityType) -> i32 {
    let base = pyrust::unwrap_or!(base_cost(etype).map(|c| c.0), 0);
    let scale = builder.state.scale;
    let foundry = if builder.state.round >= 500 && !builder.ax_harvester_adjacent.is_empty() {
        ((pyrust::unwrap!(base_cost(EntityType::Foundry)).0 as f64) * scale) as i32
    } else {
        0
    };
    match etype {
        EntityType::Foundry => ((base as f64) * scale) as i32,
        EntityType::Harvester => {
            let reserve = if builder.state.round < 35 { 10 } else { 20 };
            (((base + reserve) as f64) * (1.0 + scale)) as i32 + foundry
        }
        EntityType::Launcher => (((base + 15) as f64) * (1.0 + scale)) as i32 + foundry,
        EntityType::Sentinel | EntityType::Gunner => {
            ((base as f64) * (1.0 + scale)) as i32 + foundry
        }
        _ => ((base as f64) * scale) as i32 + foundry,
    }
}

pub fn can_afford(builder: &Builder, etype: EntityType) -> bool {
    builder.state.ti >= ti_needed(builder, etype)
}

/// Heuristic Ti cost to walk to `ore_pos`, place a harvester, ring
/// it inward (worst case 3 sides), and route the chain back to
/// `sink_pos`.
pub fn required_ti_for_ore_claim(builder: &Builder, ore_pos: Position, sink_pos: Position) -> i32 {
    let s = builder.state.scale;
    let h_cost = ((pyrust::unwrap!(base_cost(EntityType::Harvester)).0 as f64) * (1.0 + s)) as i32;
    let c_cost = ((pyrust::unwrap!(base_cost(EntityType::Conveyor)).0 as f64) * s) as i32;
    let b_cost = ((pyrust::unwrap!(base_cost(EntityType::Bridge)).0 as f64) * s) as i32;
    let r_cost = (((pyrust::unwrap!(base_cost(EntityType::Road)).0 as f64) * s) as i32).max(1);
    let d_pos = manhattan(builder.state.my_pos, ore_pos);
    let d_sink = manhattan(ore_pos, sink_pos);
    let walk_cost = d_pos * r_cost;
    let ring_cost = 3 * c_cost;
    let chain_cost =
        ((d_sink as f64) * (0.7 * (c_cost as f64) + 0.3 * (b_cost as f64) / 3.0)) as i32;
    h_cost + ring_cost + chain_cost + walk_cost
}

/// Leniency multiplier on `required_ti_for_ore_claim`. Decaying
/// exponential in friendly harvester count: starts at 0.65, asymptotes to 1.60.
pub fn ore_claim_leniency(builder: &Builder) -> f64 {
    let n = builder.my_harvesters.len() as f64;
    0.65 + 0.95 * (1.0 - 0.958f64.powf(n))
}

pub fn can_afford_ore_claim(builder: &Builder, ore_pos: Position, sink_pos: Position) -> bool {
    builder.state.ti
        >= ((required_ti_for_ore_claim(builder, ore_pos, sink_pos) as f64)
            * ore_claim_leniency(builder)) as i32
}

/// Type alias for the optional third argument to `try_place`.
/// Use `BuildExtra::None`, `BuildExtra::Direction(d)`, or
/// `BuildExtra::Position(p)`.
pub type TryPlaceExtra = BuildExtra;

pub fn try_place(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    etype: EntityType,
    pos: Position,
    extra: BuildExtra,
    destroy: bool,
) -> bool {
    if !can_afford(builder, etype) {
        let mut args = Map::new();
        args.insert(
            pyrust::to_string!("etype"),
            serde_json::Value::String(format!("{etype:?}")),
        );
        args.insert(pyrust::to_string!("pos"), auto_wrap_position(pos));
        args.insert(
            pyrust::to_string!("have"),
            serde_json::Value::Number(serde_json::Number::from(builder.state.ti)),
        );
        args.insert(
            pyrust::to_string!("need"),
            serde_json::Value::Number(serde_json::Number::from(ti_needed(builder, etype))),
        );
        let base_for_log = match base_cost(etype) {
            Some(c) => c.0,
            None => 0,
        };
        args.insert(
            pyrust::to_string!("base"),
            serde_json::Value::Number(serde_json::Number::from(base_for_log)),
        );
        args.insert(pyrust::to_string!("scale"), serde_json::json!(builder.state.scale));
        log(
            "try_place: cannot afford {etype} at {pos} (have {have}, need {need}; base {base}, scale {scale:.2f})",
            args,
        );
        return false;
    }
    if destroy && pyrust::unwrap!(ct.can_destroy(pos)) {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("pos"), auto_wrap_position(pos));
        args.insert(
            pyrust::to_string!("etype"),
            serde_json::Value::String(format!("{etype:?}")),
        );
        log(
            "try_place: destroying existing building at {pos} for {etype}",
            args,
        );
        pyrust::unwrap!(ct.destroy(pos));
        builder.apply_local_destroy(pos);
    }
    if pyrust::unwrap!(ct.can_build(etype, pos, extra)) {
        let mut args = Map::new();
        args.insert(
            pyrust::to_string!("etype"),
            serde_json::Value::String(format!("{etype:?}")),
        );
        args.insert(pyrust::to_string!("pos"), auto_wrap_position(pos));
        args.insert(
            pyrust::to_string!("extra"),
            serde_json::Value::String(format!("{extra:?}")),
        );
        args.insert(
            pyrust::to_string!("ti"),
            serde_json::Value::Number(serde_json::Number::from(builder.state.ti)),
        );
        args.insert(pyrust::to_string!("scale"), serde_json::json!(builder.state.scale));
        log(
            "try_place: built {etype} at {pos} extra={extra} (ti={ti}, scale={scale:.2f})",
            args,
        );
        pyrust::unwrap!(ct.build(etype, pos, extra));
        return true;
    }
    let mut args = Map::new();
    args.insert(
        pyrust::to_string!("etype"),
        serde_json::Value::String(format!("{etype:?}")),
    );
    args.insert(pyrust::to_string!("pos"), auto_wrap_position(pos));
    args.insert(
        pyrust::to_string!("extra"),
        serde_json::Value::String(format!("{extra:?}")),
    );
    log(
        "try_place: controller rejected {etype} at {pos} extra={extra} (can_build False)",
        args,
    );
    false
}

pub fn trace_downstream(
    builder: &Builder,
    start_pos: Position,
    target_head: Option<Position>,
) -> Vec<Position> {
    let mut path: Vec<Position> = pyrust::vec::new!();
    _trace_downstream_inner(builder, start_pos, target_head, &mut path);
    path
}

fn _trace_downstream_inner(
    builder: &Builder,
    start_pos: Position,
    target_head: Option<Position>,
    path: &mut Vec<Position>,
) {
    let mut current_pos = start_pos;
    loop {
        path.push(current_pos);
        let i = builder.idx(current_pos);
        let kind = builder.building_kind[i];
        match kind {
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge) => {
                if builder.out_edges[i].is_empty() {
                    break;
                }
                current_pos = builder.out_edges[i][0];
            }
            Some(EntityType::Splitter) => {
                // Splitter's 3 outputs (forward + two perpendicular sides).
                // Try each as a path branch.
                let outs: Vec<Position> = builder.out_edges[i].clone();
                let mut handled = false;
                for new_pos in pyrust::copied!(pyrust::iter!(outs)) {
                    if let Some(target_head) = target_head {
                        let mut new_path = path.clone();
                        _trace_downstream_inner(builder, new_pos, Some(target_head), &mut new_path);
                        if !new_path.is_empty() && new_path.contains(&target_head) {
                            *path = new_path;
                            return;
                        }
                    } else if pyrust::is_none!(builder.get_building(new_pos)) {
                        path.push(new_pos);
                        handled = true;
                        return;
                    }
                }
                if !handled {
                    if outs.is_empty() {
                        break;
                    }
                    // Forward = first output (canonical convention from
                    // `edge_targets`).
                    current_pos = outs[0];
                }
            }
            _ => break,
        }
        if path.contains(&current_pos) {
            break;
        }
    }
}

pub fn try_heal(
    builder: &Builder,
    ct: &mut Controller<'_>,
    position: Position,
    conserve_ti: bool,
) -> bool {
    if conserve_ti && let Some(repair_pos) = builder.repair_pos {
        let i = builder.idx(repair_pos);
        if pyrust::is_none!(builder.building_kind[i]) || builder.hp[i] > builder.max_hp[i] - 4 {
            return false;
        }
    }
    if pyrust::unwrap!(ct.can_heal(position)) {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("pos"), auto_wrap_position(position));
        log("try_heal: healing {pos}", args);
        pyrust::unwrap!(ct.heal(position));
        return true;
    }
    false
}

pub fn move_random(builder: &mut Builder, ct: &mut Controller<'_>) -> bool {
    let mut dir8: Vec<Direction> = DIR8.to_vec();
    builder.state.rng.shuffle(&mut dir8);
    for direction in dir8 {
        if pyrust::unwrap!(ct.can_move(direction)) {
            pyrust::unwrap!(ct.move_(direction));
            return true;
        }
    }
    false
}

pub fn trace_upstream(builder: &Builder, position: Position) -> Vec<Position> {
    let mut path: Vec<Position> = pyrust::vec::new!();
    let mut feeders: Vec<Position> = vec![position];
    while !feeders.is_empty() {
        let position = feeders[0];
        feeders = builder.get_in_edges(position);
        if path.contains(&position) {
            break;
        }
        path.push(position);
    }
    path
}

pub fn ore_available(builder: &Builder, pos: Position) -> bool {
    if let Some((kind, _team)) = builder.get_building(pos) {
        let allowed = matches!(
            kind,
            EntityType::Road | EntityType::Marker | EntityType::Barrier
        ) || (matches!(kind, EntityType::Conveyor | EntityType::ArmouredConveyor)
            && is_inward_guard(builder, pos));
        if !allowed {
            return false;
        }
    }
    if let Some(&uid) = builder.state.all_bots.get(&pos)
        && uid != builder.state.my_id
    {
        return false;
    }
    true
}

/// The cardinal of `ore_pos` chosen as the future flow-feed slot.
pub fn harvester_feed_cardinal(builder: &Builder, ore_pos: Position) -> Option<Position> {
    let sink: Option<Position> = if on_enemy_side(builder, ore_pos) {
        if pyrust::is_some!(builder.symmetry()) {
            Some(builder.en_core_guess())
        } else {
            None
        }
    } else if let Some(t) = builder.ti_sink {
        Some(t)
    } else {
        Some(builder.my_core)
    };
    let Some(sink) = sink else {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("ore"), auto_wrap_position(ore_pos));
        log(
            "harvester_feed_cardinal({ore}): no sink — symmetry unresolved",
            args,
        );
        return None;
    };

    let mut tier1: Vec<Position> = pyrust::vec::new!();
    let mut tier2: Vec<Position> = pyrust::vec::new!();
    let mut classification: Vec<(Position, &'static str)> = pyrust::vec::new!();
    for d in DIR4 {
        let c = ore_pos.add(d);
        if !builder.in_bounds(c) {
            continue;
        }
        if c == builder.state.my_pos {
            classification.push((c, "my_pos"));
            continue;
        }
        if builder.get_env(c) == Some(Environment::Wall) {
            classification.push((c, "wall"));
            continue;
        }
        let ci = builder.idx(c);
        let kind = builder.building_kind[ci];
        let team = builder.building_team[ci];
        if matches!(
            kind,
            Some(
                EntityType::Bridge
                    | EntityType::Conveyor
                    | EntityType::ArmouredConveyor
                    | EntityType::Splitter
            )
        ) && team != Some(builder.state.my_team)
        {
            classification.push((c, "enemy_transport"));
            continue;
        }
        match kind {
            Some(EntityType::Bridge) => {
                let target = pyrust::unwrap_or!(builder.out_edges[ci].first().copied(), c);
                if target == ore_pos {
                    classification.push((c, "inward_guard: bridge target == ore"));
                } else {
                    tier1.push(c);
                    classification.push((c, "tier1: bridge"));
                }
                continue;
            }
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor) => {
                let target = pyrust::unwrap_or!(builder.out_edges[ci].first().copied(), c);
                if target == ore_pos {
                    classification.push((c, "inward_guard: conveyor output -> ore"));
                } else {
                    tier1.push(c);
                    classification.push((c, "tier1: outward conveyor"));
                }
                continue;
            }
            Some(EntityType::Splitter) => {
                // Splitter back-input cell = mirror of forward across c.
                // From the 3 outputs: 4*c - sum(outputs) = c - forward_dir.
                let outs = &builder.out_edges[ci];
                if outs.len() == 3 {
                    let back = crate::building::splitter_back_input(c, outs);
                    if back == ore_pos {
                        tier1.push(c);
                        classification.push((c, "tier1: outward splitter"));
                    } else {
                        classification.push((c, "inward_guard: splitter back not -> ore"));
                    }
                }
                continue;
            }
            Some(
                EntityType::Foundry
                | EntityType::Core
                | EntityType::Harvester
                | EntityType::Barrier,
            ) => {
                classification.push((c, "blocking_building"));
                continue;
            }
            _ => {}
        }
        // Escape check for tier 2.
        let dx = c.x - ore_pos.x;
        let dy = c.y - ore_pos.y;
        let Some(d_away) = delta_to_dir(dx, dy) else {
            continue;
        };
        let u_shape = [
            c.add(d_away),
            c.add(rotate_left(rotate_left(d_away))),
            c.add(rotate_right(rotate_right(d_away))),
            c.add(rotate_left(d_away)),
            c.add(rotate_right(d_away)),
        ];
        let has_escape = pyrust::any!(pyrust::iter!(u_shape), |p| builder.in_bounds(*p) && builder.is_passable(*p));
        if !has_escape {
            classification.push((c, "no_escape"));
            continue;
        }
        tier2.push(c);
        classification.push((c, "tier2"));
    }

    let chosen: Option<Position> = if !tier1.is_empty() {
        Some(
            *pyrust::unwrap!(tier1
                .iter()
                .min_by_key(|c| c.distance_squared(sink))),
        )
    } else if !tier2.is_empty() {
        Some(
            *pyrust::unwrap!(tier2
                .iter()
                .min_by_key(|c| c.distance_squared(sink))),
        )
    } else {
        None
    };

    if pyrust::is_none!(chosen) {
        let label = format!("feed_pick_{}_{}", ore_pos.x, ore_pos.y);
        let _g = Scope::new(&label);
        let mut args = Map::new();
        args.insert(pyrust::to_string!("ore"), auto_wrap_position(ore_pos));
        log("feed_pick({ore}): NONE", args);
        for d in DIR4 {
            let c = ore_pos.add(d);
            if !builder.in_bounds(c) {
                continue;
            }
            let status = pyrust::unwrap_or!(classification
                .iter()
                .find_map(|t| if t.0 == c { Some(t.1) } else { None }), "?");
            let mut args = Map::new();
            args.insert(pyrust::to_string!("c"), auto_wrap_position(c));
            args.insert(
                pyrust::to_string!("status"),
                serde_json::Value::String(pyrust::to_string!(status)),
            );
            log("  {c}: {status}", args);
        }
    }

    chosen
}

/// Cardinals of `ore_pos` that must NOT be barriered.
pub fn harvester_io_cardinals(builder: &Builder, ore_pos: Position) -> HashSet<Position> {
    let cardinals: Vec<Position> = pyrust::collect!(pyrust::filter!(pyrust::map!(pyrust::iter!(DIR4), |&d| ore_pos.add(d)), |p| builder.in_bounds(*p)));
    let mut reserved: HashSet<Position> = pyrust::set::new!();
    for c in &cardinals {
        if *c == builder.state.my_pos {
            reserved.insert(*c);
            continue;
        }
        if matches!(
            builder.kind_at(*c),
            Some(
                EntityType::Conveyor
                    | EntityType::ArmouredConveyor
                    | EntityType::Splitter
                    | EntityType::Bridge
                    | EntityType::Foundry
                    | EntityType::Core
                    | EntityType::Harvester
            )
        ) {
            reserved.insert(*c);
        }
    }
    if let Some(feed) = harvester_feed_cardinal(builder, ore_pos) {
        reserved.insert(feed);
    }
    reserved
}

/// True iff at least 3 of `ore_pos`'s 4 in-bounds cardinals already host a barrier.
pub fn harvester_barrier_saturated(builder: &Builder, ore_pos: Position) -> bool {
    let mut barriers = 0;
    for d in DIR4 {
        let c = ore_pos.add(d);
        if !builder.in_bounds(c) {
            continue;
        }
        if builder.kind_at(c) == Some(EntityType::Barrier) {
            barriers += 1;
        }
    }
    barriers >= 3
}

pub fn pick_ore_target(builder: &Builder) -> Option<Position> {
    _pick_ore(builder, Environment::OreTitanium)
}

pub fn pick_ax_ore_target(builder: &Builder) -> Option<Position> {
    _pick_ore(builder, Environment::OreAxionite)
}

/// Pick a Ti ore tile outside our econ disc for an offensive harvester.
pub fn pick_offensive_ti_ore_target(builder: &Builder) -> Option<Position> {
    let mut best_target: Option<Position> = None;
    let mut min_dist = i32::MAX;
    for pos in &builder.state.nearby_tiles {
        if builder.get_env(*pos) != Some(Environment::OreTitanium) {
            continue;
        }
        match builder.kind_at(*pos) {
            Some(EntityType::Harvester) => continue,
            None
            | Some(EntityType::Road | EntityType::Marker | EntityType::Barrier) => {}
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor) => {
                if !is_inward_guard(builder, *pos) {
                    continue;
                }
            }
            _ => continue,
        }
        if !builder.is_reachable(*pos) {
            continue;
        }
        let d = builder.state.my_pos.distance_squared(*pos);
        if !ore_available(builder, *pos) {
            continue;
        }
        if pos.distance_squared(builder.my_core) <= builder.econ_radius_sq {
            continue;
        }
        if harvester_would_contaminate(builder, *pos) {
            continue;
        }
        let friends_iter = pyrust::filter_map!(pyrust::iter!(builder.state.all_bots), |t| {
            if *t.1 != builder.state.my_id && builder.state.friendly_bots.contains(t.0) {
                Some((*t.0, *t.1))
            } else {
                None
            }
        });
        if !claims_by_proximity(
            builder.state.my_pos,
            builder.state.my_id,
            *pos,
            friends_iter,
        ) {
            continue;
        }
        if d < min_dist {
            min_dist = d;
            best_target = Some(*pos);
        }
    }
    best_target
}

pub fn harvester_would_contaminate(builder: &Builder, pos: Position) -> bool {
    let ore_env = builder.get_env(pos);
    let (bad_upstream, bad_flows): (&HashSet<Position>, &[ResourceType]) =
        if ore_env == Some(Environment::OreTitanium) {
            (
                &builder.ax_upstream,
                &[ResourceType::RawAxionite, ResourceType::RefinedAxionite],
            )
        } else if ore_env == Some(Environment::OreAxionite) {
            (&builder.ti_upstream, &[ResourceType::Titanium])
        } else {
            return false;
        };
    let mut pure_ti_conveyor_count = 0;
    let mut heavy_hostile_count = 0;
    let mut hostile_found = false;
    for d in DIR4 {
        let n = pos.add(d);
        if !builder.in_bounds(n) {
            continue;
        }
        let Some((kind, team)) = builder.get_building(n) else { continue };
        if !matches!(
            kind,
            EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Splitter
                | EntityType::Bridge
        ) {
            continue;
        }
        if team != builder.state.my_team {
            continue;
        }
        let ni = (n.y as usize) * MAX_WIDTH + (n.x as usize);
        let is_bad = bad_upstream.contains(&n)
            || pyrust::any!(pyrust::iter!(builder.flow_history[ni]), |t| t.0.is_some_and(|res| bad_flows.contains(&res)));
        if !is_bad {
            continue;
        }
        hostile_found = true;
        if ore_env == Some(Environment::OreAxionite) {
            if kind == EntityType::Conveyor {
                pure_ti_conveyor_count += 1;
            } else {
                heavy_hostile_count += 1;
            }
        }
    }
    if !hostile_found {
        return false;
    }
    !(ore_env == Some(Environment::OreAxionite)
        && heavy_hostile_count == 0
        && pure_ti_conveyor_count == 1)
}

/// True if `pos` is outside our econ disc — i.e. more than
/// sqrt(econ_radius_sq) (= 0.7·max(w,h)) from our core.
pub fn on_enemy_side(builder: &Builder, pos: Position) -> bool {
    pos.distance_squared(builder.my_core) > builder.econ_radius_sq
}

/// True if `pos` hosts a friendly conveyor whose flow direction
/// points at an adjacent friendly harvester.
pub fn is_inward_guard(builder: &Builder, pos: Position) -> bool {
    let i = builder.idx(pos);
    let kind = builder.building_kind[i];
    let team = builder.building_team[i];
    if !matches!(
        kind,
        Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
    ) {
        return false;
    }
    if team != Some(builder.state.my_team) {
        return false;
    }
    if builder.out_edges[i].is_empty() {
        return false;
    }
    let target = builder.out_edges[i][0];
    if !builder.in_bounds(target) {
        return false;
    }
    builder.kind_at(target) == Some(EntityType::Harvester)
        && builder.team_at(target) == Some(builder.state.my_team)
}

fn _pick_ore(builder: &Builder, wanted: Environment) -> Option<Position> {
    let mut best_target: Option<Position> = None;
    let mut min_dist = i32::MAX;
    for pos in &builder.state.nearby_tiles {
        if builder.get_env(*pos) != Some(wanted) {
            continue;
        }
        match builder.kind_at(*pos) {
            Some(EntityType::Harvester) => continue,
            None
            | Some(EntityType::Road | EntityType::Marker | EntityType::Barrier) => {}
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor) => {
                if !is_inward_guard(builder, *pos) {
                    continue;
                }
            }
            _ => continue,
        }
        if !builder.is_reachable(*pos) {
            continue;
        }
        let d = builder.state.my_pos.distance_squared(*pos);
        if !ore_available(builder, *pos) {
            continue;
        }
        if pos.distance_squared(builder.my_core) > builder.econ_radius_sq {
            continue;
        }
        if harvester_would_contaminate(builder, *pos) {
            continue;
        }
        if pyrust::is_none!(harvester_feed_cardinal(builder, *pos)) {
            continue;
        }
        let friends_iter = pyrust::filter_map!(pyrust::iter!(builder.state.all_bots), |t| {
            if *t.1 != builder.state.my_id && builder.state.friendly_bots.contains(t.0) {
                Some((*t.0, *t.1))
            } else {
                None
            }
        });
        if !claims_by_proximity(
            builder.state.my_pos,
            builder.state.my_id,
            *pos,
            friends_iter,
        ) {
            continue;
        }
        if d < min_dist {
            min_dist = d;
            best_target = Some(*pos);
        }
    }
    best_target
}

const _UPSTREAM_MAX_NODES: usize = 80;
const _DOWNSTREAM_MAX_NODES: usize = 80;

/// BFS backwards via `in_edges` — all friendly transport tiles whose
/// output structurally reaches `start`.
pub fn upstream_tree(builder: &Builder, start: Position) -> HashSet<Position> {
    let mut visited: HashSet<Position> = pyrust::set::new!();
    visited.insert(start);
    let mut queue: Vec<Position> = vec![start];
    while let Some(pos) = queue.pop() {
        if visited.len() >= _UPSTREAM_MAX_NODES {
            break;
        }
        for &u in &builder.in_edges[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)] {
            if visited.contains(&u) {
                continue;
            }
            visited.insert(u);
            queue.push(u);
        }
    }
    visited
}

/// BFS forwards via `out_edges`.
pub fn downstream_tree(builder: &Builder, start: Position) -> HashSet<Position> {
    let mut visited: HashSet<Position> = pyrust::set::new!();
    visited.insert(start);
    let mut queue: Vec<Position> = vec![start];
    while let Some(pos) = queue.pop() {
        if visited.len() >= _DOWNSTREAM_MAX_NODES {
            break;
        }
        for &out in &builder.out_edges[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)] {
            if visited.contains(&out) {
                continue;
            }
            visited.insert(out);
            queue.push(out);
        }
    }
    visited
}

pub fn chain_has_foundry(builder: &Builder, start: Position) -> bool {
    let my_team = builder.state.my_team;
    for pos in upstream_tree(builder, start) {
        if builder.kind_at(pos) == Some(EntityType::Foundry)
            && builder.team_at(pos) == Some(my_team)
        {
            return true;
        }
    }
    for pos in downstream_tree(builder, start) {
        if builder.kind_at(pos) == Some(EntityType::Foundry)
            && builder.team_at(pos) == Some(my_team)
        {
            return true;
        }
    }
    false
}

pub fn ax_feeds_target(builder: &Builder, target: Position) -> bool {
    for &feeder in &builder.in_edges[(target.y as usize) * MAX_WIDTH + (target.x as usize)] {
        if builder.ax_upstream.contains(&feeder) {
            return true;
        }
    }
    for d in DIR4 {
        let n = target.add(d);
        if !builder.in_bounds(n) {
            continue;
        }
        let ni = (n.y as usize) * MAX_WIDTH + (n.x as usize);
        if builder.building_kind[ni] == Some(EntityType::Harvester)
            && builder.building_team[ni] == Some(builder.state.my_team)
            && builder.env[ni] == Some(Environment::OreAxionite)
        {
            return true;
        }
    }
    false
}

pub fn tile_has_ax_flow(builder: &Builder, pos: Position) -> bool {
    for &(r, _rid) in &builder.flow_history[(pos.y as usize) * MAX_WIDTH + (pos.x as usize)] {
        if matches!(
            r,
            Some(ResourceType::RawAxionite | ResourceType::RefinedAxionite)
        ) {
            return true;
        }
    }
    false
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
