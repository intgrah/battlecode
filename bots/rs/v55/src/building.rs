//! Per-tile building helpers. The bot stores building state in the
//! `Builder`'s SoA arrays (`building_kind[i]`, `building_team[i]`,
//! `out_edges[i]`) — there's no separate `Building` ADT.
//!
//! These free functions handle reading from `ct` at `_add_topology` time
//! (the only place Building info enters the bot's state).

use cambc::{Controller, ControllerApi, Direction, EntityType, Position, Team};

/// Read kind + team at `bid` from `ct`. Panics on `BuilderBot` (not a
/// building) — by convention callers gate on `is_in_vision` first.
#[must_use]
pub fn make_building(ct: &Controller<'_>, bid: i32) -> (EntityType, Team) {
    let kind = ct.get_entity_type(Some(bid)).unwrap();
    let team = ct.get_team(Some(bid)).unwrap();
    if matches!(kind, EntityType::BuilderBot) {
        panic!("BUILDER_BOT is not a building");
    }
    (kind, team)
}

/// Routing output positions for the building at `pos` (id `bid`, kind
/// `kind`). Empty for non-routing variants. Used by `_add_topology` to
/// populate `out_edges[i]`.
#[must_use]
pub fn edge_targets(
    ct: &Controller<'_>,
    pos: Position,
    bid: i32,
    kind: EntityType,
) -> Vec<Position> {
    match kind {
        EntityType::Conveyor | EntityType::ArmouredConveyor => {
            vec![pos.add(ct.get_direction(Some(bid)).unwrap())]
        }
        EntityType::Bridge => vec![ct.get_bridge_target(bid).unwrap()],
        EntityType::Splitter => {
            let d = ct.get_direction(Some(bid)).unwrap();
            vec![
                pos.add(d),
                pos.add(rotate_right_2(d)),
                pos.add(rotate_left_2(d)),
            ]
        }
        _ => Vec::new(),
    }
}

/// Splitter back-input cell (the side opposite its forward output). Sum
/// of the three outputs = `3*pos + d`, so `4*pos - sum = pos - d`.
/// Order-independent.
#[must_use]
pub fn splitter_back_input(pos: Position, outputs: &[Position]) -> Position {
    let sum_x: i32 = outputs.iter().map(|p| p.x).sum();
    let sum_y: i32 = outputs.iter().map(|p| p.y).sum();
    Position {
        x: 4 * pos.x - sum_x,
        y: 4 * pos.y - sum_y,
    }
}

const fn rotate_right_2(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::East,
        Direction::Northeast => Direction::Southeast,
        Direction::East => Direction::South,
        Direction::Southeast => Direction::Southwest,
        Direction::South => Direction::West,
        Direction::Southwest => Direction::Northwest,
        Direction::West => Direction::North,
        Direction::Northwest => Direction::Northeast,
        Direction::Centre => Direction::Centre,
    }
}

const fn rotate_left_2(d: Direction) -> Direction {
    match d {
        Direction::North => Direction::West,
        Direction::Northeast => Direction::Northwest,
        Direction::East => Direction::North,
        Direction::Southeast => Direction::Northeast,
        Direction::South => Direction::East,
        Direction::Southwest => Direction::Southeast,
        Direction::West => Direction::South,
        Direction::Northwest => Direction::Southwest,
        Direction::Centre => Direction::Centre,
    }
}
