//! Translation of `bots/intgrah/v54.7.9/builder/helpers.py`.

use std::collections::HashSet;

use cambc::{
    BuildExtra, Controller, ControllerApi, Direction, EntityType, Environment, Position,
    ResourceType,
};
use serde_json::Map;

use crate::builder::Builder;
use crate::config::DEBUG_LOG;
use crate::util::constants::{MAX_WIDTH, STRIDE, base_cost};
use crate::util::debug::{Scope, debug as log};
use crate::util::directions::{DIR4, DIR8, delta_to_dir};
use crate::util::metrics::{chebyshev, claims_by_proximity, claims_by_proximity_p, manhattan};
use crate::util::posint::{DIR4_INT, DIR8_INT, PosInt, dist_sq, idx_of, manhat, pos_of};
use crate::util::visualiser::auto_wrap_position;

/// Return True iff this call actually issued a move. 'Already at target'
/// and 'no plan' both return False — neither advances the builder, so the
/// caller shouldn't treat the turn as productive.
pub fn make_move(builder: &mut Builder, ct: &mut Controller<'_>, target: Position) -> bool {
    if builder.state.my_pos == target {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("target"),
                auto_wrap_position(target)
            );
            log("make_move: already on target {target}", args);
        }
        return false;
    }
    let next_move = builder.bugnav_step(target);
    let Some(next_move) = next_move else {
        if move_random(builder, ct) {
            if DEBUG_LOG {
                let mut args = Map::new();
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("start"),
                    auto_wrap_position(builder.state.my_pos)
                );
                pyrust::dict::insert!(
                    args,
                    pyrust::to_string!("target"),
                    auto_wrap_position(target)
                );
                log(
                    "make_move: bugnav stuck, took random step {start}->{target}",
                    args,
                );
            }
            return true;
        }
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("start"),
                auto_wrap_position(builder.state.my_pos)
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("target"),
                auto_wrap_position(target)
            );
            log(
                "make_move: FAILED {start}->{target} (bugnav: no plan, random step also blocked)",
                args,
            );
        }
        return false;
    };
    if DEBUG_LOG {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("start"),
            auto_wrap_position(builder.state.my_pos)
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("target"),
            auto_wrap_position(target)
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("next"),
            auto_wrap_position(next_move)
        );
        log("make_move: bugnav {start}->{target} step {next}", args);
    }
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
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("target"),
                auto_wrap_position(target)
            );
            log(
                "make_move_or_adjacent: {target} impassable AND no passable cardinal",
                args,
            );
        }
        return false;
    };
    if builder.state.my_pos == best {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("target"),
                auto_wrap_position(target)
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("pos"),
                auto_wrap_position(builder.state.my_pos)
            );
            log(
                "make_move_or_adjacent: already adjacent to {target} (at {pos})",
                args,
            );
        }
        return false;
    }
    if DEBUG_LOG {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("target"),
            auto_wrap_position(target)
        );
        pyrust::dict::insert!(args, pyrust::to_string!("adj"), auto_wrap_position(best));
        log(
            "make_move_or_adjacent: {target} impassable, routing to cardinal {adj}",
            args,
        );
    }
    make_move(builder, ct, best)
}

pub fn try_move_dir(ct: &mut Controller<'_>, d: Direction) -> bool {
    if pyrust::unwrap!(ct.can_move(d)) {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("dir"),
                serde_json::Value::String(format!("{d}"))
            );
            log("try_move_dir: moving {dir}", args);
        }
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
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("start"),
                auto_wrap_position(builder.state.my_pos)
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("target"),
                auto_wrap_position(target_pos)
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("dir"),
                serde_json::Value::String(format!("{d}"))
            );
            log("try_move_to: {start}->{target} dir {dir}", args);
        }
        let hx = i32::from(dx > 0) - i32::from(dx < 0);
        let hy = i32::from(dy > 0) - i32::from(dy < 0);
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
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("target"),
                auto_wrap_position(target_pos)
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("cost"),
                serde_json::Value::Number(serde_json::Number::from(builder.get_cost(target_pos)))
            );
            log(
                "try_move_with_road: paving road at {target} (cost={cost} > 1)",
                args,
            );
        }
        pyrust::unwrap!(ct.build_road(target_pos));
    }
    try_move_to(builder, ct, target_pos)
}

pub fn try_attack(ct: &mut Controller<'_>, pos: Position) -> bool {
    if pyrust::unwrap!(ct.can_fire(pos)) {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(args, pyrust::to_string!("pos"), auto_wrap_position(pos));
            log("try_attack: firing on {pos}", args);
        }
        pyrust::unwrap!(ct.fire(pos));
        return true;
    }
    false
}

#[must_use]
pub fn ti_needed(builder: &Builder, etype: EntityType) -> i32 {
    let base = if let Some(c) = base_cost(etype) {
        c.0
    } else {
        0
    };
    let scale = builder.state.scale;
    let foundry =
        if builder.state.round >= 500 && !pyrust::vec::is_empty!(builder.ax_harvester_adjacent) {
            (pyrust::float!(pyrust::unwrap!(base_cost(EntityType::Foundry)).0) * scale) as i32
        } else {
            0
        };
    match etype {
        EntityType::Foundry => (pyrust::float!(base) * scale) as i32,
        EntityType::Harvester => {
            let reserve = if builder.state.round < 35 { 10 } else { 20 };
            (pyrust::float!(base + reserve) * (1.0 + scale)) as i32 + foundry
        }
        EntityType::Launcher => (pyrust::float!(base + 15) * (1.0 + scale)) as i32 + foundry,
        EntityType::Sentinel | EntityType::Gunner => {
            (pyrust::float!(base) * (1.0 + scale)) as i32 + foundry
        }
        _ => (pyrust::float!(base) * scale) as i32 + foundry,
    }
}

#[must_use]
pub fn can_afford(builder: &Builder, etype: EntityType) -> bool {
    builder.state.ti >= ti_needed(builder, etype)
}

/// Heuristic Ti cost to walk to `ore_pos`, place a harvester, ring
/// it inward (worst case 3 sides), and route the chain back to
/// `sink_pos`.
#[must_use]
pub fn required_ti_for_ore_claim(builder: &Builder, ore_pos: Position, sink_pos: Position) -> i32 {
    let s = builder.state.scale;
    let h_cost =
        (pyrust::float!(pyrust::unwrap!(base_cost(EntityType::Harvester)).0) * (1.0 + s)) as i32;
    let c_cost = (pyrust::float!(pyrust::unwrap!(base_cost(EntityType::Conveyor)).0) * s) as i32;
    let b_cost = (pyrust::float!(pyrust::unwrap!(base_cost(EntityType::Bridge)).0) * s) as i32;
    let r_cost = pyrust::max!(
        ((pyrust::float!(pyrust::unwrap!(base_cost(EntityType::Road)).0) * s) as i32),
        1
    );
    let d_pos = manhattan(builder.state.my_pos, ore_pos);
    let d_sink = manhattan(ore_pos, sink_pos);
    let walk_cost = d_pos * r_cost;
    let ring_cost = 3 * c_cost;
    let chain_cost = (pyrust::float!(d_sink)
        * (0.7 * pyrust::float!(c_cost) + 0.3 * pyrust::float!(b_cost) / 3.0))
        as i32;
    h_cost + ring_cost + chain_cost + walk_cost
}

/// Leniency multiplier on `required_ti_for_ore_claim`. Decaying
/// exponential in friendly harvester count: starts at 0.65, asymptotes to 1.60.
#[must_use]
pub fn ore_claim_leniency(builder: &Builder) -> f64 {
    let n = pyrust::len!(builder.my_harvesters) as f64;
    let mut decay = 1.0f64;
    for _ in 0..(n as i32) {
        decay *= 0.958;
    }
    0.65 + 0.95 * (1.0 - decay)
}

#[must_use]
pub fn can_afford_ore_claim(builder: &Builder, ore_pos: Position, sink_pos: Position) -> bool {
    builder.state.ti
        >= (pyrust::float!(required_ti_for_ore_claim(builder, ore_pos, sink_pos))
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
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("etype"),
            serde_json::Value::String(format!("{etype:?}"))
        );
        pyrust::dict::insert!(args, pyrust::to_string!("pos"), auto_wrap_position(pos));
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("have"),
            serde_json::Value::Number(serde_json::Number::from(builder.state.ti))
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("need"),
            serde_json::Value::Number(serde_json::Number::from(ti_needed(builder, etype)))
        );
        let base_for_log = match base_cost(etype) {
            Some(c) => c.0,
            None => 0,
        };
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("base"),
            serde_json::Value::Number(serde_json::Number::from(base_for_log))
        );
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("scale"),
            serde_json::json!(builder.state.scale)
        );
        log(
            "try_place: cannot afford {etype} at {pos} (have {have}, need {need}; base {base}, scale {scale:.2f})",
            args,
        );
        return false;
    }
    if destroy && pyrust::unwrap!(ct.can_destroy(pos)) {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(args, pyrust::to_string!("pos"), auto_wrap_position(pos));
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("etype"),
                serde_json::Value::String(format!("{etype:?}"))
            );
            log(
                "try_place: destroying existing building at {pos} for {etype}",
                args,
            );
        }
        pyrust::unwrap!(ct.destroy(pos));
        builder.apply_local_destroy(pos);
    }
    if pyrust::unwrap!(ct.can_build(etype, pos, extra)) {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("etype"),
                serde_json::Value::String(format!("{etype:?}"))
            );
            pyrust::dict::insert!(args, pyrust::to_string!("pos"), auto_wrap_position(pos));
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("extra"),
                serde_json::Value::String(format!("{extra:?}"))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("ti"),
                serde_json::Value::Number(serde_json::Number::from(builder.state.ti))
            );
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("scale"),
                serde_json::json!(builder.state.scale)
            );
            log(
                "try_place: built {etype} at {pos} extra={extra} (ti={ti}, scale={scale:.2f})",
                args,
            );
        }
        pyrust::unwrap!(ct.build(etype, pos, extra));
        return true;
    }
    if DEBUG_LOG {
        let mut args = Map::new();
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("etype"),
            serde_json::Value::String(format!("{etype:?}"))
        );
        pyrust::dict::insert!(args, pyrust::to_string!("pos"), auto_wrap_position(pos));
        pyrust::dict::insert!(
            args,
            pyrust::to_string!("extra"),
            serde_json::Value::String(format!("{extra:?}"))
        );
        log(
            "try_place: controller rejected {etype} at {pos} extra={extra} (can_build False)",
            args,
        );
    }
    false
}

#[must_use]
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
        pyrust::vec::push!(path, current_pos);
        let i = builder.idx(current_pos);
        let kind = builder.building_kind[i];
        match kind {
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge) => {
                if pyrust::vec::is_empty!(builder.out_edges[i]) {
                    break;
                }
                current_pos = builder.out_edges[i][0];
            }
            Some(EntityType::Splitter) => {
                // Splitter's 3 outputs (forward + two perpendicular sides).
                // Try each as a path branch.
                let outs: Vec<Position> = pyrust::clone!(builder.out_edges[i]);
                let mut handled = false;
                for new_pos in pyrust::copied!(pyrust::iter!(outs)) {
                    if let Some(target_head) = target_head {
                        let mut new_path = pyrust::clone!(path);
                        _trace_downstream_inner(builder, new_pos, Some(target_head), &mut new_path);
                        if !pyrust::vec::is_empty!(new_path)
                            && pyrust::vec::contains!(new_path, &target_head)
                        {
                            *path = new_path;
                            return;
                        }
                    } else if pyrust::is_none!(builder.get_building(new_pos)) {
                        pyrust::vec::push!(path, new_pos);
                        handled = true;
                        return;
                    }
                }
                if !handled {
                    if pyrust::vec::is_empty!(outs) {
                        break;
                    }
                    // Forward = first output (canonical convention from
                    // `edge_targets`).
                    current_pos = outs[0];
                }
            }
            _ => break,
        }
        if pyrust::vec::contains!(path, &current_pos) {
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
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(
                args,
                pyrust::to_string!("pos"),
                auto_wrap_position(position)
            );
            log("try_heal: healing {pos}", args);
        }
        pyrust::unwrap!(ct.heal(position));
        return true;
    }
    false
}

pub fn move_random(builder: &mut Builder, ct: &mut Controller<'_>) -> bool {
    let mut dir8: Vec<Direction> = pyrust::collect!(pyrust::copied!(pyrust::iter!(DIR8)));
    builder.state.rng.shuffle(&mut dir8);
    for direction in dir8 {
        if pyrust::unwrap!(ct.can_move(direction)) {
            pyrust::unwrap!(ct.move_(direction));
            return true;
        }
    }
    false
}

#[must_use]
pub fn trace_upstream(builder: &Builder, position: Position) -> Vec<Position> {
    let mut path: Vec<Position> = pyrust::vec::new!();
    let mut feeders: Vec<Position> = vec![position];
    while !pyrust::vec::is_empty!(feeders) {
        let position = feeders[0];
        feeders = builder.get_in_edges(position);
        if pyrust::vec::contains!(path, &position) {
            break;
        }
        pyrust::vec::push!(path, position);
    }
    path
}

#[must_use]
pub fn ore_available(builder: &Builder, pos: Position) -> bool {
    ore_available_p(builder, idx_of(pos), pos)
}

/// PosInt-native variant. Pass `pos = pos_of(p)` only for the engine-side
/// bot-presence check.
#[must_use]
pub fn ore_available_p(builder: &Builder, p: PosInt, pos: Position) -> bool {
    if let Some((kind, _team)) = builder.get_building_p(p) {
        let allowed = matches!(
            kind,
            EntityType::Road | EntityType::Marker | EntityType::Barrier
        ) || (matches!(kind, EntityType::Conveyor | EntityType::ArmouredConveyor)
            && is_inward_guard_p(builder, p));
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
#[must_use]
pub fn harvester_feed_cardinal(builder: &Builder, ore_pos: Position) -> Option<Position> {
    if let Some(p) = harvester_feed_cardinal_p(builder, idx_of(ore_pos)) {
        Some(pos_of(p))
    } else {
        None
    }
}

/// True iff the friendly transport at `p` has its first out-edge land
/// on a friendly tile that hosts a chain consumer.
#[must_use]
fn _transport_output_to_friendly_chain_p(builder: &Builder, p: PosInt) -> bool {
    let i = p as usize;
    if pyrust::vec::is_empty!(builder.out_edges[i]) {
        return false;
    }
    let target = builder.out_edges[i][0];
    if !builder.in_bounds(target) {
        return false;
    }
    let ti = idx_of(target) as usize;
    if builder.building_team[ti] != Some(builder.state.my_team) {
        return false;
    }
    matches!(
        builder.building_kind[ti],
        Some(
            EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Bridge
                | EntityType::Splitter
                | EntityType::Foundry
                | EntityType::Core
        )
    )
}

/// PosInt-native variant. Returns the chosen feed cardinal as a `PosInt`.
#[must_use]
pub fn harvester_feed_cardinal_p(builder: &Builder, ore_p: PosInt) -> Option<PosInt> {
    let ore_pos = pos_of(ore_p);
    let sink_p: Option<PosInt> = if on_enemy_side_p(builder, ore_p) {
        if pyrust::is_some!(builder.symmetry) {
            Some(builder.en_core_guess_p)
        } else {
            None
        }
    } else if let Some(t) = builder.ti_sink {
        Some(idx_of(t))
    } else {
        Some(builder.my_core_p)
    };
    let Some(sink_p) = sink_p else {
        if DEBUG_LOG {
            let mut args = Map::new();
            pyrust::dict::insert!(args, pyrust::to_string!("ore"), auto_wrap_position(ore_pos));
            log(
                "harvester_feed_cardinal({ore}): no sink — symmetry unresolved",
                args,
            );
        }
        return None;
    };

    // v56-ported PRIMARY/FALLBACK feed cardinal:
    // PRIMARY = empty / friendly Road / friendly Marker / friendly transport
    //   whose first out-edge lands on a friendly chain consumer / friendly
    //   Splitter with back-input == ore / friendly Core
    // FALLBACK = inward conveyors (output points back at ore)
    // Among feedable, pick closest-to-sink within highest non-empty tier.
    let posint_valid = &builder.posint_valid;
    let my_team = builder.state.my_team;
    let mut primary: Option<(i32, PosInt)> = None;
    let mut fallback: Option<(i32, PosInt)> = None;
    for &d in &DIR4_INT {
        let np = ore_p + d;
        if np < 0 || posint_valid[np as usize] == 0 {
            continue;
        }
        let ci = np as usize;
        if builder.env[ci] == Some(Environment::Wall) {
            continue;
        }
        let kind = builder.building_kind[ci];
        let team = builder.building_team[ci];
        let primary_feedable = match kind {
            None => true,
            Some(EntityType::Road | EntityType::Marker) => true,
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor | EntityType::Bridge) => {
                team == Some(my_team) && _transport_output_to_friendly_chain_p(builder, np)
            }
            Some(EntityType::Splitter) => {
                team == Some(my_team)
                    && pyrust::len!(builder.out_edges[ci]) == 3
                    && crate::building::splitter_back_input(pos_of(np), &builder.out_edges[ci])
                        == ore_pos
            }
            Some(EntityType::Core) => team == Some(my_team),
            _ => false,
        };
        let inward = !primary_feedable
            && matches!(
                kind,
                Some(EntityType::Conveyor | EntityType::ArmouredConveyor)
            )
            && is_inward_guard_p(builder, np);
        let dsq = dist_sq(np, sink_p);
        if primary_feedable {
            if pyrust::is_none_or!(primary, |p: (i32, PosInt)| dsq < p.0) {
                primary = Some((dsq, np));
            }
        } else if inward && pyrust::is_none_or!(fallback, |p: (i32, PosInt)| dsq < p.0) {
            fallback = Some((dsq, np));
        }
    }

    if let Some(t) = primary {
        Some(t.1)
    } else if let Some(t) = fallback {
        Some(t.1)
    } else {
        None
    }
}

/// Cardinals of `ore_pos` that must NOT be barriered.
#[must_use]
pub fn harvester_io_cardinals(builder: &Builder, ore_pos: Position) -> HashSet<Position> {
    let cardinals: Vec<Position> = pyrust::collect!(pyrust::filter!(
        pyrust::map!(pyrust::iter!(DIR4), |&d| ore_pos.add(d)),
        |p| builder.in_bounds(*p)
    ));
    let mut reserved: HashSet<Position> = pyrust::set::new!();
    for c in &cardinals {
        if *c == builder.state.my_pos {
            pyrust::set::add!(reserved, *c);
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
            pyrust::set::add!(reserved, *c);
        }
    }
    if let Some(feed) = harvester_feed_cardinal(builder, ore_pos) {
        pyrust::set::add!(reserved, feed);
    }
    reserved
}

/// True iff at least 3 of `ore_pos`'s 4 in-bounds cardinals already host a barrier.
#[must_use]
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

#[must_use]
pub fn pick_ore_target(builder: &Builder) -> Option<Position> {
    _pick_ore(builder, Environment::OreTitanium)
}

#[must_use]
pub fn pick_ax_ore_target(builder: &Builder) -> Option<Position> {
    _pick_ore(builder, Environment::OreAxionite)
}

/// Pick a Ti ore tile outside our econ disc for an offensive harvester.
///
/// Scoring (WS-8 / AUDIT O6): prefer ore *closer to enemy infrastructure*
/// over ore deep in empty enemy territory. Enemy infra = visible enemy
/// harvester or chain tile (conveyor/armoured conveyor/splitter/bridge/
/// foundry). Falls back to `en_core_guess` when no enemy infra is visible.
///
/// ```text
/// score(pos) = (1.0 if on_enemy_side else 0.0)
///            + 5.0 / (1.0 + manhattan(pos, nearest_enemy_infra))
///            - 0.05 * manhattan(pos, my_pos)
/// ```
#[must_use]
pub fn pick_offensive_ti_ore_target(builder: &Builder) -> Option<Position> {
    // Collect visible enemy infra positions once as PosInts (avoid idx_of
    // per inner loop iteration).
    let mut enemy_infra_p: Vec<PosInt> = Vec::new();
    for pos in &builder.state.nearby_tiles {
        let p = idx_of(*pos);
        let Some((kind, team)) = builder.get_building_p(p) else {
            continue;
        };
        if team == builder.state.my_team {
            continue;
        }
        if matches!(
            kind,
            EntityType::Harvester
                | EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Splitter
                | EntityType::Bridge
                | EntityType::Foundry
        ) {
            pyrust::vec::push!(enemy_infra_p, p);
        }
    }
    let infra_fallback_p: Option<PosInt> = if pyrust::is_some!(builder.symmetry) {
        Some(idx_of(builder.en_core_guess))
    } else {
        None
    };
    let core_p = idx_of(builder.my_core);
    let my_idx = idx_of(builder.state.my_pos);
    let econ_radius_sq = builder.econ_radius_sq;
    let my_id = builder.state.my_id;
    // Materialise friendlies once instead of rebuilding per candidate.
    // Without this the inner loop is O(ores * friendly_builders) with a
    // large constant — the dominant TLE source per intgrah's diagnosis.
    let mut friends: Vec<(PosInt, i32)> = pyrust::vec::new!();
    for (fb_pos, fb_id) in &builder.state.all_bots {
        if *fb_id != my_id && pyrust::set::contains!(builder.state.friendly_bots, fb_pos) {
            pyrust::vec::push!(friends, (idx_of(*fb_pos), *fb_id));
        }
    }

    let mut best_target: Option<Position> = None;
    let mut best_score: f64 = f64::NEG_INFINITY;
    // Iterate the pre-filtered visible_ti_ore set (typically ~5-10 tiles)
    // instead of nearby_tiles (~60). Cheapest filters first.
    for &p in &builder.visible_ti_ore {
        if !builder.is_reachable_p(p) {
            continue;
        }
        if dist_sq(p, core_p) <= econ_radius_sq {
            continue;
        }
        let pos = pos_of(p);
        if !ore_available_p(builder, p, pos) {
            continue;
        }
        let i = p as usize;
        match builder.building_kind[i] {
            Some(EntityType::Harvester) => continue,
            None | Some(EntityType::Road | EntityType::Marker | EntityType::Barrier) => {}
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor) => {
                if !is_inward_guard_p(builder, p) {
                    continue;
                }
            }
            _ => continue,
        }
        if !claims_by_proximity_p(my_idx, my_id, p, pyrust::copied!(pyrust::iter!(friends))) {
            continue;
        }
        if harvester_would_contaminate_p(builder, p) {
            continue;
        }

        let nearest_infra_md: Option<i32> = if pyrust::vec::is_empty!(enemy_infra_p) {
            if let Some(fp) = infra_fallback_p {
                Some(manhat(p, fp))
            } else {
                None
            }
        } else {
            pyrust::min!(pyrust::map!(pyrust::iter!(enemy_infra_p), |ip| manhat(
                p, *ip
            )))
        };
        let infra_term = match nearest_infra_md {
            Some(md) => 5.0 / (1.0 + md as f64),
            None => 0.0,
        };
        let side_term = if on_enemy_side_p(builder, p) {
            1.0
        } else {
            0.0
        };
        let walk_term = 0.05 * manhat(my_idx, p) as f64;
        let score = side_term + infra_term - walk_term;
        if score > best_score {
            best_score = score;
            best_target = Some(pos);
        }
    }
    best_target
}

#[must_use]
pub fn harvester_would_contaminate(builder: &Builder, pos: Position) -> bool {
    harvester_would_contaminate_p(builder, idx_of(pos))
}

/// PosInt-native variant.
#[must_use]
pub fn harvester_would_contaminate_p(builder: &Builder, p: PosInt) -> bool {
    let ore_env = builder.get_env_p(p);
    let (bad_upstream, bad_flows): (&HashSet<i32>, &[ResourceType]) =
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
    let bk = &builder.building_kind;
    let bt = &builder.building_team;
    let posint_valid = &builder.posint_valid;
    for &d in &DIR4_INT {
        let np = p + d;
        if np < 0 || posint_valid[np as usize] == 0 {
            continue;
        }
        let nu = np as usize;
        let Some(kind) = bk[nu] else { continue };
        if !matches!(
            kind,
            EntityType::Conveyor
                | EntityType::ArmouredConveyor
                | EntityType::Splitter
                | EntityType::Bridge
        ) {
            continue;
        }
        let Some(team) = bt[nu] else { continue };
        if team != builder.state.my_team {
            continue;
        }
        let is_bad = pyrust::vec::contains!(bad_upstream, &np)
            || pyrust::any!(
                pyrust::iter!(builder.flow_history[nu]),
                |t| pyrust::is_some_and!(t.0, |res| pyrust::vec::contains!(bad_flows, &res))
            );
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

#[pyrust::inline]
/// True if `pos` is outside our econ disc — i.e. more than
/// `sqrt(econ_radius_sq)` (= 0.7·max(w,h)) from our core.
#[must_use]
pub const fn on_enemy_side(builder: &Builder, pos: Position) -> bool {
    pos.distance_squared(builder.my_core) > builder.econ_radius_sq
}

/// PosInt-native variant of `on_enemy_side`. Uses the precomputed dist_sq
/// table.
#[must_use]
#[inline]
pub fn on_enemy_side_p(builder: &Builder, p: PosInt) -> bool {
    let core_p = idx_of(builder.my_core);
    dist_sq(p, core_p) > builder.econ_radius_sq
}

/// True if `pos` hosts a friendly conveyor whose flow direction
/// points at an adjacent friendly harvester.
#[must_use]
pub fn is_inward_guard(builder: &Builder, pos: Position) -> bool {
    is_inward_guard_p(builder, idx_of(pos))
}

/// PosInt-native variant of `is_inward_guard`. Skip the `idx_of` round-trip
/// when the caller already has a `PosInt`.
#[must_use]
pub fn is_inward_guard_p(builder: &Builder, p: PosInt) -> bool {
    let i = p as usize;
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
    if pyrust::vec::is_empty!(builder.out_edges[i]) {
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
    // Iterate the pre-filtered ore tile list maintained by update_vision
    // instead of scanning all ~60 nearby_tiles. Typically ~5-10 ore tiles
    // visible vs 60 — 6× fewer iterations on the outer loop.
    let bk = &builder.building_kind;
    let my_pos = builder.state.my_pos;
    let my_core = builder.my_core;
    let my_idx = idx_of(my_pos);
    let core_idx = idx_of(my_core);
    let econ_radius_sq = builder.econ_radius_sq;
    let my_id = builder.state.my_id;
    // Pre-compute friends list once instead of rebuilding the
    // filter_map iterator per ore-candidate. Store as PosInt so the
    // claims_by_proximity_p inner loop avoids per-call chebyshev arithmetic.
    let mut friends: Vec<(PosInt, i32)> = pyrust::vec::new!();
    for (fb_pos, fb_id) in &builder.state.all_bots {
        if *fb_id != my_id && pyrust::set::contains!(builder.state.friendly_bots, fb_pos) {
            pyrust::vec::push!(friends, (idx_of(*fb_pos), *fb_id));
        }
    }
    let ore_list: &Vec<i32> = match wanted {
        Environment::OreAxionite => &builder.visible_ax_ore,
        _ => &builder.visible_ti_ore,
    };
    let mut best_target: Option<Position> = None;
    let mut min_dist = i32::MAX;
    // Filter order: cheapest gates first, compute distance, **early-exit
    // on `d >= min_dist`** before expensive checks (claims_by_proximity,
    // harvester_would_contaminate, harvester_feed_cardinal). With many
    // friendly bots in the friendlies list, this dominated the search
    // budget before the reorder.
    //
    // Each rejection emits a `_pick_ore` log line under DEBUG_LOG so the
    // debug-dump scope tree records why a candidate was filtered. Reads
    // back via `scripts/dump_decode.py` for skip-ore investigation.
    for &pi in ore_list {
        if !builder.is_reachable_p(pi) {
            _log_pick_reject(pi, "unreachable");
            continue;
        }
        if dist_sq(pi, core_idx) > econ_radius_sq {
            _log_pick_reject(pi, "outside_econ_disc");
            continue;
        }
        let pos = pos_of(pi);
        if !ore_available_p(builder, pi, pos) {
            _log_pick_reject(pi, "ore_unavailable");
            continue;
        }
        let d = dist_sq(my_idx, pi);
        if d >= min_dist {
            // No log: we already have a closer pick, this isn't a "skip".
            continue;
        }
        let i = pi as usize;
        match bk[i] {
            Some(EntityType::Harvester) => {
                _log_pick_reject(pi, "harvester_already");
                continue;
            }
            None | Some(EntityType::Road | EntityType::Marker | EntityType::Barrier) => {}
            Some(EntityType::Conveyor | EntityType::ArmouredConveyor) => {
                if !is_inward_guard_p(builder, pi) {
                    _log_pick_reject(pi, "conveyor_not_inward");
                    continue;
                }
            }
            _ => {
                _log_pick_reject(pi, "blocking_kind");
                continue;
            }
        }
        if !claims_by_proximity_p(my_idx, my_id, pi, pyrust::copied!(pyrust::iter!(friends))) {
            _log_pick_reject(pi, "friend_closer");
            continue;
        }
        if harvester_would_contaminate_p(builder, pi) {
            _log_pick_reject(pi, "would_contaminate");
            continue;
        }
        if pyrust::is_none!(harvester_feed_cardinal_p(builder, pi)) {
            _log_pick_reject(pi, "no_feed_cardinal");
            continue;
        }
        min_dist = d;
        best_target = Some(pos);
    }
    best_target
}

#[cfg(any())]
fn _log_pick_reject(_pi: PosInt, _reason: &'static str) {}

#[cfg(not(any()))]
fn _log_pick_reject(pi: PosInt, reason: &'static str) {
    if !crate::config::DEBUG_LOG {
        return;
    }
    let mut args = serde_json::Map::new();
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("pos"),
        crate::util::visualiser::auto_wrap_position(pos_of(pi))
    );
    pyrust::dict::insert!(
        args,
        pyrust::to_string!("reason"),
        serde_json::Value::String(pyrust::to_string!(reason))
    );
    crate::util::debug::debug("_pick_ore reject {pos}: {reason}", args);
}

const _UPSTREAM_MAX_NODES: usize = 80;
const _DOWNSTREAM_MAX_NODES: usize = 80;

/// BFS backwards via `in_edges` — all friendly transport tiles whose
/// output structurally reaches `start`.
#[must_use]
pub fn upstream_tree(builder: &Builder, start: Position) -> HashSet<Position> {
    let mut visited: HashSet<Position> = pyrust::set::new!();
    pyrust::set::add!(visited, start);
    let mut queue: Vec<Position> = vec![start];
    while let Some(pos) = pyrust::vec::pop!(queue) {
        if pyrust::len!(visited) >= _UPSTREAM_MAX_NODES {
            break;
        }
        for &u in &builder.in_edges[idx_of(pos) as usize] {
            if pyrust::vec::contains!(visited, &u) {
                continue;
            }
            pyrust::set::add!(visited, u);
            pyrust::vec::push!(queue, u);
        }
    }
    visited
}

/// BFS forwards via `out_edges`.
#[must_use]
pub fn downstream_tree(builder: &Builder, start: Position) -> HashSet<Position> {
    let mut visited: HashSet<Position> = pyrust::set::new!();
    pyrust::set::add!(visited, start);
    let mut queue: Vec<Position> = vec![start];
    while let Some(pos) = pyrust::vec::pop!(queue) {
        if pyrust::len!(visited) >= _DOWNSTREAM_MAX_NODES {
            break;
        }
        for &out in &builder.out_edges[idx_of(pos) as usize] {
            if pyrust::vec::contains!(visited, &out) {
                continue;
            }
            pyrust::set::add!(visited, out);
            pyrust::vec::push!(queue, out);
        }
    }
    visited
}

#[must_use]
pub fn chain_has_foundry(builder: &Builder, start: Position) -> bool {
    let my_team = builder.state.my_team;
    for pos in upstream_tree(builder, start) {
        let p = idx_of(pos);
        if builder.kind_at_p(p) == Some(EntityType::Foundry)
            && builder.team_at_p(p) == Some(my_team)
        {
            return true;
        }
    }
    for pos in downstream_tree(builder, start) {
        let p = idx_of(pos);
        if builder.kind_at_p(p) == Some(EntityType::Foundry)
            && builder.team_at_p(p) == Some(my_team)
        {
            return true;
        }
    }
    false
}

#[must_use]
pub fn ax_feeds_target(builder: &Builder, target: Position) -> bool {
    let tp = idx_of(target);
    for &feeder in &builder.in_edges[tp as usize] {
        if pyrust::vec::contains!(builder.ax_upstream, &idx_of(feeder)) {
            return true;
        }
    }
    let posint_valid = &builder.posint_valid;
    for &d in &DIR4_INT {
        let np = tp + d;
        if np < 0 || posint_valid[np as usize] == 0 {
            continue;
        }
        let ni = np as usize;
        if builder.building_kind[ni] == Some(EntityType::Harvester)
            && builder.building_team[ni] == Some(builder.state.my_team)
            && builder.env[ni] == Some(Environment::OreAxionite)
        {
            return true;
        }
    }
    false
}

#[must_use]
pub fn tile_has_ax_flow(builder: &Builder, pos: Position) -> bool {
    for &(r, _rid) in &builder.flow_history[idx_of(pos) as usize] {
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
