use cambc::{Controller, ControllerApi, EntityType, Environment, Position};

use crate::builder::Builder;
use crate::util::constants::ROAD_COST;

fn building_kind(ct: &mut Controller<'_>, pos: Position) -> Option<EntityType> {
    let bid = pyrust::unwrap!(ct.get_tile_building_id(pos))?;
    Some(pyrust::unwrap!(ct.get_entity_type(Some(bid))))
}

/// End-of-turn cleanup: for each cardinal neighbour that is a friendly road,
/// if both diagonal tiles flanking it (the two tiles sharing a corner with
/// both the bot and the road tile) are passable, destroy the road.
///
/// These roads are bypassed by diagonal movement and only add to scale cost.
pub fn end_of_turn_trim_roads(builder: &mut Builder, ct: &mut Controller<'_>) {
    let pos = builder.state.my_pos;
    if building_kind(ct, pos) != Some(EntityType::Road) {
        return;
    }
    for (cdx, cdy) in [(0i32, -1i32), (1, 0), (0, 1), (-1, 0)] {
        let np = Position { x: pos.x + cdx, y: pos.y + cdy };
        if !builder.in_bounds(np) {
            continue;
        }
        let ni = builder.idx(np);
        if building_kind(ct, np) != Some(EntityType::Road) {
            continue;
        }
        if builder.building_team[ni] != Some(builder.state.my_team) {
            continue;
        }
        // Skip if the road or any of its cardinal neighbours is on ore.
        let is_ore = |p: Position| {
            matches!(
                builder.get_env(p),
                Some(Environment::OreAxionite | Environment::OreTitanium)
            )
        };
        if is_ore(np) {
            continue;
        }
        // Skip if the road is cardinally adjacent to any building other than roads or markers.
        let mut adj_non_road = false;
        let mut adj_ore = false;
        for (dx, dy) in [(0i32, -1i32), (-1, 0), (1, 0), (0, 1)] {
            let neighbor = Position { x: np.x + dx, y: np.y + dy };
            if !builder.in_bounds(neighbor) {
                continue;
            }
            if is_ore(neighbor) {
                adj_ore = true;
                break;
            }
            let nk = building_kind(ct, neighbor);
            if matches!(nk, Some(k) if k != EntityType::Road && k != EntityType::Marker) {
                adj_non_road = true;
                break;
            }
        }
        if adj_ore || adj_non_road {
            continue;
        }
        // The two diagonal tiles flanking the road (sharing a corner with
        // both bot and road). For cardinal (cdx, cdy) the perpendicular is
        // (cdy.abs(), cdx.abs()).
        let perp_x = cdy.abs();
        let perp_y = cdx.abs();
        let d0 = Position { x: pos.x + cdx + perp_x, y: pos.y + cdy + perp_y };
        let d1 = Position { x: pos.x + cdx - perp_x, y: pos.y + cdy - perp_y };
        let passable = |p: Position| {
            builder.in_bounds(p) && builder.cost_grid[builder.idx(p)] < ROAD_COST
        };
        if passable(d0) && passable(d1) {
            if pyrust::unwrap!(ct.can_destroy(np)) {
                pyrust::unwrap!(ct.destroy(np));
                builder.apply_local_destroy(np);
            }
        }
    }
}
