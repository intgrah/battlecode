//! Helpers shared by the three ore-claim tasks (`claim_ore`,
//! `guard_harvester_neighbours`, `build_harvester`). The task layer dispatches
//! priority — these helpers are pure mechanism.
//!
//! Phases:
//!   1. `walk_to_ore_claim` — navigate onto the ore tile (with contest
//!      clearing of any adjacent enemy road/conveyor/splitter/bridge).
//!   2. `pave_inward_neighbour` — place ONE inward-facing conveyor on a
//!      cardinal of a friendly Ti harvester or a claimed ore tile, if any
//!      such cardinal needs guarding.
//!   3. `step_off_and_build_harvester` — step off the ore tile and place
//!      the harvester in the same turn.
//!
//! Walls and friendly harvesters / non-walkable buildings adjacent to the
//! target count as "already guarded" — the inward ring is only placed on
//! empty / friendly-road / marker cardinals.

use std::collections::HashSet;

use cambc::{Controller, ControllerApi, Direction, EntityType, Environment, Position, Team};
use serde_json::Map;

use crate::builder::Builder;
use crate::builder::helpers::{
    can_afford, harvester_feed_cardinal, make_move, make_move_or_adjacent, on_enemy_side,
    ore_available, try_move_with_road,
};
use crate::util::debug::debug as log;
use crate::util::directions::{DIR4, delta_to_dir};
use crate::util::visualiser::auto_wrap_position;

/// Enemy road/conveyor/splitter/bridge cardinal-adjacent to `pos`,
/// or None. Such a tile would dump our harvester's output into an
/// enemy chain — must be cleared before claim.
pub fn find_contest_target(builder: &Builder, pos: Position, my_team: Team) -> Option<Position> {
    for d in DIR4 {
        let n = pos.add(d);
        if !builder.in_bounds(n) {
            continue;
        }
        let Some((kind, team)) = builder.get_building(n) else {
            continue;
        };
        if team == my_team {
            continue;
        }
        if matches!(
            kind,
            EntityType::Road
                | EntityType::Conveyor
                | EntityType::Splitter
                | EntityType::Bridge
        ) {
            return Some(n);
        }
    }
    None
}

/// A cardinal is "already guarded" — no inward conveyor needed —
/// when an enemy can't easily place a parasitic conveyor there. That
/// is: walls, harvesters (any team), and any non-{road,marker} building
/// occupying the tile.
pub fn is_guarded_cardinal(builder: &Builder, pos: Position) -> bool {
    if builder.get_env(pos) == Some(Environment::Wall) {
        return true;
    }
    let Some(kind) = builder.kind_at(pos) else {
        return false;
    };
    !matches!(kind, EntityType::Road | EntityType::Marker)
}

/// Walk toward `target_pos`, clearing any contest tile along the way.
/// Returns True if the builder is already standing on the ore (claim
/// achieved — caller should defer to the next phase) OR if an action
/// was taken this turn (still claiming). Returns False only if no
/// progress could be made (e.g. no path).
pub fn walk_to_ore_claim(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    target_pos: Position,
) -> bool {
    if builder.state.my_pos == target_pos {
        if !ore_available(builder, target_pos) {
            let mut args = Map::new();
            args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
            log("walk_to_ore_claim: ore {target} no longer available", args);
            return false;
        }
        return true;
    }

    // Contest: an enemy road/conveyor/splitter/bridge adjacent to the
    // ore must be cleared before we can build the harvester safely.
    let contest_pos = find_contest_target(builder, target_pos, builder.state.my_team);
    if let Some(contest_pos) = contest_pos {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("contest"), auto_wrap_position(contest_pos));
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
        log(
            "walk_to_ore_claim: CONTEST enemy at {contest} adj to ore {target}",
            args,
        );
        if builder.state.my_pos == contest_pos {
            if builder.state.ti >= 2 && pyrust::unwrap!(ct.can_fire(builder.state.my_pos)) {
                pyrust::unwrap!(ct.fire(builder.state.my_pos));
            }
            return true;
        }
        if builder.state.my_pos.distance_squared(contest_pos) <= 2 {
            let dx = contest_pos.x - builder.state.my_pos.x;
            let dy = contest_pos.y - builder.state.my_pos.y;
            if let Some(d) = delta_to_dir(dx, dy)
                && pyrust::unwrap!(ct.can_move(d))
            {
                pyrust::unwrap!(ct.move_(d));
            }
            return true;
        }
        return make_move(builder, ct, contest_pos);
    }

    // If the ore tile itself has a friendly guard (barrier, conveyor,
    // armoured) placed earlier as the protective ring of an ADJACENT
    // harvester, tear it down so we can walk onto the now-empty tile.
    if builder.state.my_pos.distance_squared(target_pos) <= 2 {
        if matches!(
            builder.kind_at(target_pos),
            Some(EntityType::Barrier | EntityType::Conveyor | EntityType::ArmouredConveyor)
        ) && pyrust::unwrap!(ct.can_destroy(target_pos))
        {
            let mut args = Map::new();
            args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
            log(
                "walk_to_ore_claim: destroying friendly guard on ore {target}",
                args,
            );
            pyrust::unwrap!(ct.destroy(target_pos));
            builder.apply_local_destroy(target_pos);
        }
    }

    let mut args = Map::new();
    args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
    args.insert(
        pyrust::to_string!("d"),
        serde_json::Value::Number(serde_json::Number::from(
            builder.state.my_pos.distance_squared(target_pos),
        )),
    );
    log(
        "walk_to_ore_claim: walking toward ore {target} dist²={d}",
        args,
    );
    try_move_with_road(builder, ct, target_pos) || make_move_or_adjacent(builder, ct, target_pos)
}

/// Whether `cardinal` (a tile cardinal to harvester/claimed-ore
/// `target`) needs a guard (barrier or inward conveyor) placed.
pub fn needs_harvester_guard(
    builder: &Builder,
    cardinal: Position,
    target: Position,
    io_reserved: &HashSet<Position>,
) -> bool {
    if cardinal == builder.state.my_pos {
        return false;
    }
    if io_reserved.contains(&cardinal) {
        return false;
    }
    if is_guarded_cardinal(builder, cardinal) {
        return false;
    }
    let ci = builder.idx(cardinal);
    let kind = builder.building_kind[ci];
    let team = builder.building_team[ci];
    if matches!(kind, Some(EntityType::Conveyor | EntityType::ArmouredConveyor))
        && team == Some(builder.state.my_team)
        && !builder.out_edges[ci].is_empty()
        && builder.out_edges[ci][0] == target
    {
        return false;
    }
    true
}

/// Place a guard at `cardinal` of `target` (a harvester / claim).
pub fn place_harvester_guard(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    cardinal: Position,
    target: Position,
) -> bool {
    let use_barrier = _should_use_barrier(builder, cardinal, target);
    let etype = if use_barrier {
        EntityType::Barrier
    } else {
        EntityType::Conveyor
    };
    if builder.kind_at(cardinal) == Some(EntityType::Road)
        && pyrust::unwrap!(ct.can_destroy(cardinal))
        && can_afford(builder, etype)
    {
        pyrust::unwrap!(ct.destroy(cardinal));
        builder.apply_local_destroy(cardinal);
    }
    if !can_afford(builder, etype) {
        return false;
    }
    if use_barrier {
        if pyrust::unwrap!(ct.can_build_barrier(cardinal)) {
            let mut args = Map::new();
            args.insert(pyrust::to_string!("at"), auto_wrap_position(cardinal));
            log(
                "place_harvester_guard: BARRIER at {at} (>=3 walkable cardinals)",
                args,
            );
            pyrust::unwrap!(ct.build_barrier(cardinal));
            return true;
        }
        return false;
    }
    let dx = target.x - cardinal.x;
    let dy = target.y - cardinal.y;
    let Some(inward) = delta_to_dir(dx, dy) else {
        return false;
    };
    if pyrust::unwrap!(ct.can_build_conveyor(cardinal, inward)) {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("at"), auto_wrap_position(cardinal));
        args.insert(
            pyrust::to_string!("dir"),
            serde_json::Value::String(format!("{inward}")),
        );
        args.insert(pyrust::to_string!("target"), auto_wrap_position(target));
        log(
            "place_harvester_guard: CONVEYOR at {at} facing {dir} into {target}",
            args,
        );
        pyrust::unwrap!(ct.build_conveyor(cardinal, inward));
        return true;
    }
    false
}

/// U-shape local-connectivity check.
fn _should_use_barrier(builder: &Builder, guard_pos: Position, target: Position) -> bool {
    let dx = guard_pos.x - target.x;
    let dy = guard_pos.y - target.y;
    let Some(d) = delta_to_dir(dx, dy) else {
        return false;
    };
    let top = guard_pos.add(d);
    let left_perp = rotate_left(rotate_left(d));
    let right_perp = rotate_right(rotate_right(d));
    let left_diag = rotate_left(d);
    let right_diag = rotate_right(d);

    let passable = |p: Position| -> bool { builder.in_bounds(p) && builder.is_passable(p) };

    let top_p = passable(top);
    let left_p = passable(guard_pos.add(left_perp)) || passable(guard_pos.add(left_diag));
    let right_p = passable(guard_pos.add(right_perp)) || passable(guard_pos.add(right_diag));

    let must_use_conveyor = (!top_p) && left_p && right_p;
    !must_use_conveyor
}

/// Last-resort: when `harvester_feed_cardinal(target_pos)` returns
/// None because every cardinal is blocked, look for a friendly
/// barrier on a cardinal closest to the relevant sink and destroy
/// it (free for builders). Next turn `harvester_feed_cardinal` will
/// pick the now-empty tile as feed, and `guard_harvester_neighbours`
/// paves a road on it. Returns True if a destroy was issued.
pub fn clear_barriered_feed(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    target_pos: Position,
) -> bool {
    let sink = if on_enemy_side(builder, target_pos) {
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
        return false;
    };

    let mut candidates: Vec<Position> = pyrust::vec::new!();
    for d in DIR4 {
        let c = target_pos.add(d);
        if !builder.in_bounds(c) || c == builder.state.my_pos {
            continue;
        }
        if builder.get_env(c) == Some(Environment::Wall) {
            continue;
        }
        if builder.kind_at(c) == Some(EntityType::Barrier)
            && builder.team_at(c) == Some(builder.state.my_team)
            && pyrust::unwrap!(ct.can_destroy(c))
        {
            candidates.push(c);
        }
    }
    if candidates.is_empty() {
        return false;
    }
    let chosen = *pyrust::unwrap!(candidates
        .iter()
        .min_by_key(|c| c.distance_squared(sink)));
    let mut args = Map::new();
    args.insert(pyrust::to_string!("pos"), auto_wrap_position(chosen));
    args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
    log(
        "clear_barriered_feed: destroy friendly BARRIER on {pos} (last-resort feed clear for {target})",
        args,
    );
    pyrust::unwrap!(ct.destroy(chosen));
    builder.apply_local_destroy(chosen);
    true
}

/// Standing on the ore, step off ONTO THE FEED CARDINAL (the
/// harvester's chosen output tile) and place the harvester in the
/// same turn.
pub fn step_off_and_build_harvester(
    builder: &mut Builder,
    ct: &mut Controller<'_>,
    target_pos: Position,
) -> bool {
    let Some(feed) = harvester_feed_cardinal(builder, target_pos) else {
        return false;
    };

    let dx = feed.x - builder.state.my_pos.x;
    let dy = feed.y - builder.state.my_pos.y;
    let Some(d) = delta_to_dir(dx, dy) else {
        return false;
    };

    if !pyrust::unwrap!(ct.can_move(d))
        && builder.get_cost(feed) > 1
        && can_afford(builder, EntityType::Road)
        && pyrust::unwrap!(ct.can_build_road(feed))
    {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("feed"), auto_wrap_position(feed));
        log(
            "step_off_and_build_harvester: paving feed {feed} for step-off",
            args,
        );
        pyrust::unwrap!(ct.build_road(feed));
        return true;
    }

    if builder.kind_at(builder.state.my_pos) == Some(EntityType::Road)
        && pyrust::unwrap!(ct.can_destroy(builder.state.my_pos))
    {
        if !pyrust::unwrap!(ct.can_move(d)) {
            let mut args = Map::new();
            args.insert(pyrust::to_string!("feed"), auto_wrap_position(feed));
            log(
                "step_off_and_build_harvester: feed {feed} blocked; waiting",
                args,
            );
            return true;
        }
        let mut args = Map::new();
        args.insert(pyrust::to_string!("at"), auto_wrap_position(builder.state.my_pos));
        args.insert(pyrust::to_string!("feed"), auto_wrap_position(feed));
        log(
            "step_off_and_build_harvester: destroy own ROAD at {at}, step to feed {feed}",
            args,
        );
        let p = builder.state.my_pos;
        pyrust::unwrap!(ct.destroy(p));
        builder.apply_local_destroy(p);
    }

    if pyrust::unwrap!(ct.can_move(d)) {
        let mut args = Map::new();
        args.insert(pyrust::to_string!("d"), serde_json::Value::String(format!("{d}")));
        args.insert(pyrust::to_string!("feed"), auto_wrap_position(feed));
        log(
            "step_off_and_build_harvester: step {d} to feed {feed}",
            args,
        );
        pyrust::unwrap!(ct.move_(d));
        if pyrust::unwrap!(ct.can_build_harvester(target_pos)) {
            let mut args = Map::new();
            args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
            log(
                "step_off_and_build_harvester: HARVESTER placed on {target}",
                args,
            );
            pyrust::unwrap!(ct.build_harvester(target_pos));
            builder.ore_target = None;
        } else {
            let kind = builder.kind_at(target_pos);
            let mut args = Map::new();
            args.insert(pyrust::to_string!("feed"), auto_wrap_position(feed));
            args.insert(pyrust::to_string!("target"), auto_wrap_position(target_pos));
            args.insert(
                pyrust::to_string!("bld"),
                serde_json::Value::String(match kind {
                    Some(k) => format!("{k:?}"),
                    None => pyrust::to_string!("None"),
                }),
            );
            log(
                "step_off_and_build_harvester: stepped to {feed} but can_build_harvester({target}) is False — building at {bld}",
                args,
            );
        }
        return true;
    }
    let mut args = Map::new();
    args.insert(pyrust::to_string!("feed"), auto_wrap_position(feed));
    log(
        "step_off_and_build_harvester: cannot move to feed {feed}; waiting",
        args,
    );
    true
}

/// Tiles cardinal to `pos` that are friendly Ti harvesters OR a
/// claimed-but-unbuilt ore tile. Used by `guard_harvester_neighbours` to find
/// pave targets reachable from `pos`.
pub fn adjacent_pave_targets(builder: &Builder, pos: Position) -> Vec<Position> {
    let mut out: Vec<Position> = pyrust::vec::new!();
    let mut claimed_targets: HashSet<Position> = pyrust::set::new!();
    for tgt in [
        builder.ore_target,
        builder.ax_ore_target,
        builder.offensive_ore_target,
    ] {
        if let Some(t) = tgt
            && builder.state.my_pos == t
        {
            claimed_targets.insert(t);
        }
    }
    for d in DIR4 {
        let n = pos.add(d);
        if !builder.in_bounds(n) {
            continue;
        }
        if builder.kind_at(n) == Some(EntityType::Harvester)
            && builder.team_at(n) == Some(builder.state.my_team)
            && builder.get_env(n) == Some(Environment::OreTitanium)
        {
            out.push(n);
            continue;
        }
        if claimed_targets.contains(&n) {
            out.push(n);
        }
    }
    out
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
