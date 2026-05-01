//! Engine `Entity` → asset-sprite-name conversions, and rendering of
//! the live engine state on top of the static map.

use std::collections::HashMap;

use eframe::egui;
use libre_engine::common::{Direction, ResourceType, Team};
use libre_engine::game::Game;
use libre_engine::game_map::Entity;
use titan_core::SpriteSet;
use titan_core::connected::{
    CARDINALS, bridge_base_sprite_name as connected_bridge_base, conveyor_sprite_name,
};
use titan_core::tile::{tile_center, tile_rect};

const fn dir_suffix(d: Direction) -> &'static str {
    match d {
        Direction::North => "n",
        Direction::Northeast => "ne",
        Direction::East => "e",
        Direction::Southeast => "se",
        Direction::South => "s",
        Direction::Southwest => "sw",
        Direction::West => "w",
        Direction::Northwest => "nw",
        Direction::Centre => "n",
    }
}

const fn cardinal_suffix(d: Direction) -> &'static str {
    match d {
        Direction::North => "n",
        Direction::East => "e",
        Direction::South => "s",
        Direction::West => "w",
        _ => "e",
    }
}

const fn team_str(t: Team) -> &'static str {
    match t {
        Team::A => "gold",
        Team::B => "silver",
    }
}

#[must_use]
pub fn sprite_name(e: &Entity) -> String {
    let team = team_str(e.team);
    match e {
        Entity::BuilderBot(_) => format!("builderbot_front_{team}"),
        Entity::Core(_) => format!("base_{team}"),
        Entity::Conveyor(c) => format!("conveyor_{team}_{}", cardinal_suffix(c.direction)),
        Entity::ArmouredConveyor(c) => {
            format!("armoured_conveyor_{team}_{}", cardinal_suffix(c.direction))
        }
        Entity::Splitter(s) => format!("splitter_{}_{team}", cardinal_suffix(s.direction)),
        Entity::Bridge(_) => format!("bridge_stand_{team}"),
        Entity::Harvester(_) => format!("harvester_{team}"),
        Entity::Foundry(_) => format!("foundry_{team}"),
        Entity::Road(_) => format!("road_{team}"),
        Entity::Barrier(_) => format!("barrier_{team}"),
        Entity::Marker(_) => format!("marker_{team}"),
        Entity::Gunner(t) => format!("gunner_{}_{team}", dir_suffix(t.direction)),
        Entity::Sentinel(t) => format!("sentinel_{}_{team}", dir_suffix(t.direction)),
        Entity::Breach(t) => format!("breach_{}_{team}", dir_suffix(t.direction)),
        Entity::Launcher(_) => format!("launcher_{team}"),
    }
}

/// Atlas sprite name for the resource currently sitting on a logistics
/// entity, if any. Conveyors / armoured conveyors / splitters /
/// bridges / foundries each carry one stack at a time. Returns
/// `None` for kinds that don't store anything or for entities whose
/// `stored` slot is empty.
#[must_use]
pub fn resource_sprite(e: &Entity) -> Option<&'static str> {
    let res = match e {
        Entity::Conveyor(c) => c.stored,
        Entity::ArmouredConveyor(c) => c.stored,
        Entity::Splitter(s) => s.stored,
        Entity::Bridge(b) => b.stored,
        Entity::Foundry(f) => f.stored,
        _ => return None,
    };
    match res? {
        ResourceType::Titanium => Some("titanium"),
        ResourceType::RawAxionite => Some("axionite_raw"),
        ResourceType::RefinedAxionite => Some("axionite_processed"),
    }
}

/// Paint priority for entity kinds. Mirrors the replay viewer's
/// `z_order` so the two apps render overlapping units identically:
/// flat ground stuff first (roads / markers / barriers), then
/// directional buildings, then production buildings, then turrets,
/// then cores, then `BuilderBots` last so they always sit on top.
const fn z_order(e: &Entity) -> i32 {
    match e {
        Entity::Road(_) => 0,
        Entity::Marker(_) => 1,
        Entity::Barrier(_) => 2,
        Entity::Conveyor(_)
        | Entity::ArmouredConveyor(_)
        | Entity::Splitter(_)
        | Entity::Bridge(_) => 3,
        Entity::Harvester(_) | Entity::Foundry(_) => 4,
        Entity::Gunner(_) | Entity::Sentinel(_) | Entity::Breach(_) | Entity::Launcher(_) => 5,
        Entity::Core(_) => 6,
        Entity::BuilderBot(_) => 7,
    }
}

pub fn render_entities(
    painter: &egui::Painter,
    atlas: &SpriteSet,
    game: &Game,
    ts: f32,
    origin: egui::Pos2,
    zoom: f32,
    show_ids: bool,
) {
    let mut entries: Vec<(i32, &Entity)> = game.entities.iter().map(|(&id, e)| (id, e)).collect();
    entries.sort_by_key(|(id, e)| (z_order(e), *id));
    // Same lookup the replay viewer builds: tile → entities on it.
    // Used by `conveyor_junction_sprite_name` / `bridge_base_sprite_name`
    // to detect which neighbours feed into a given conveyor / bridge.
    let by_pos: HashMap<(i32, i32), Vec<&Entity>> = {
        let mut m: HashMap<(i32, i32), Vec<&Entity>> = HashMap::new();
        for e in game.entities.values() {
            m.entry((e.position.x, e.position.y)).or_default().push(e);
        }
        m
    };
    for (id, e) in entries {
        paint_entity(painter, atlas, id, e, &by_pos, ts, origin, zoom, show_ids);
    }
}

#[allow(clippy::too_many_arguments)]
fn paint_entity(
    painter: &egui::Painter,
    atlas: &SpriteSet,
    id: i32,
    e: &Entity,
    by_pos: &HashMap<(i32, i32), Vec<&Entity>>,
    ts: f32,
    origin: egui::Pos2,
    zoom: f32,
    show_ids: bool,
) {
    let pos = e.position;
    let rect = match e {
        Entity::Core(_) => {
            // Core is 3x3, rendered from the centre tile.
            let r = tile_rect(pos.x - 1, pos.y - 1, ts, origin, zoom);
            egui::Rect::from_min_size(r.min, egui::Vec2::splat(ts * zoom * 3.0))
        }
        _ => tile_rect(pos.x, pos.y, ts, origin, zoom),
    };
    // Connected-texture variants for conveyors / armoured conveyors
    // and bridges: pick a sprite that reflects which neighbours feed
    // into this tile. Fall back to the plain `sprite_name(e)` if the
    // entity isn't a connection-aware kind or no specific variant
    // exists in the atlas.
    let name = conveyor_junction_sprite_name(e, by_pos)
        .or_else(|| bridge_base_sprite_name(e, by_pos))
        .unwrap_or_else(|| sprite_name(e));
    if let Some(tex) = atlas.get(&name) {
        painter.image(
            tex,
            rect,
            egui::Rect::from_min_max(egui::Pos2::ZERO, egui::Pos2::new(1.0, 1.0)),
            egui::Color32::WHITE,
        );
    }
    // Resource overlay: small icon over conveyors / splitters /
    // bridges / foundries that currently carry a stack.
    if let Some(res_name) = resource_sprite(e)
        && let Some(tex) = atlas.get(res_name)
    {
        let centre = tile_center(pos.x, pos.y, ts, origin, zoom);
        let half = ts * zoom * 0.25;
        let r = egui::Rect::from_center_size(centre, egui::Vec2::splat(half * 2.0));
        painter.image(
            tex,
            r,
            egui::Rect::from_min_max(egui::Pos2::ZERO, egui::Pos2::new(1.0, 1.0)),
            egui::Color32::WHITE,
        );
    }
    if show_ids {
        let cx = rect.center().x;
        let cy = rect.center().y;
        let size = (ts * zoom * 0.32).clamp(8.0, 24.0);
        painter.text(
            egui::pos2(cx, cy),
            egui::Align2::CENTER_CENTER,
            id.to_string(),
            egui::FontId::monospace(size),
            egui::Color32::WHITE,
        );
    }
}

// ── Connected-texture helpers ────────────────────────────────────
// Same logic the replay viewer uses (`titan-replay/src/map.rs`),
// retargeted at libre-engine's `Entity` enum. A conveyor / armoured
// conveyor's sprite encodes (out direction, set of feeding inputs);
// a bridge's base encodes (set of openings).

const fn dir_unit(d: Direction) -> Option<(i32, i32)> {
    match d {
        Direction::North => Some((0, -1)),
        Direction::East => Some((1, 0)),
        Direction::South => Some((0, 1)),
        Direction::West => Some((-1, 0)),
        _ => None,
    }
}

/// True if `neighbor` (a player-or-enemy entity adjacent to `target`)
/// would direct a resource into `target`. Mirrors the replay's
/// `conveyor_feeds_into`.
fn feeds_into(neighbor: &Entity, target: (i32, i32)) -> bool {
    match neighbor {
        Entity::Conveyor(c) => {
            let Some((dx, dy)) = dir_unit(c.direction) else {
                return false;
            };
            (neighbor.position.x + dx, neighbor.position.y + dy) == target
        }
        Entity::ArmouredConveyor(c) => {
            let Some((dx, dy)) = dir_unit(c.direction) else {
                return false;
            };
            (neighbor.position.x + dx, neighbor.position.y + dy) == target
        }
        Entity::Splitter(s) => {
            let Some((dx, dy)) = dir_unit(s.direction) else {
                return false;
            };
            let back = (-dx, -dy);
            let delta = (
                target.0 - neighbor.position.x,
                target.1 - neighbor.position.y,
            );
            CARDINALS.contains(&delta) && delta != back
        }
        Entity::Bridge(b) => (b.target.x, b.target.y) == target,
        Entity::Harvester(_) | Entity::Foundry(_) => true,
        _ => false,
    }
}

/// Cardinal directions whose neighbour entity would feed `entity`.
/// `out` (when `Some`) excludes the conveyor's own output side from
/// the returned input set.
fn collect_feeding_inputs(
    entity: &Entity,
    by_pos: &HashMap<(i32, i32), Vec<&Entity>>,
    out: Option<(i32, i32)>,
) -> Vec<(i32, i32)> {
    let pos = (entity.position.x, entity.position.y);
    let mut inputs: Vec<(i32, i32)> = Vec::new();
    for (dx, dy) in CARDINALS {
        if Some((dx, dy)) == out {
            continue;
        }
        let n = (pos.0 + dx, pos.1 + dy);
        let feeds = by_pos.get(&n).is_some_and(|list| {
            list.iter()
                .any(|e| e.team == entity.team && feeds_into(e, pos))
        });
        if feeds {
            inputs.push((dx, dy));
        }
    }
    inputs
}

fn conveyor_junction_sprite_name(
    e: &Entity,
    by_pos: &HashMap<(i32, i32), Vec<&Entity>>,
) -> Option<String> {
    let (base, out_dir) = match e {
        Entity::Conveyor(c) => ("conveyor", c.direction),
        Entity::ArmouredConveyor(c) => ("armoured_conveyor", c.direction),
        _ => return None,
    };
    let out = dir_unit(out_dir)?;
    let inputs = collect_feeding_inputs(e, by_pos, Some(out));
    conveyor_sprite_name(base, team_str(e.team), out, &inputs)
}

fn bridge_base_sprite_name(
    e: &Entity,
    by_pos: &HashMap<(i32, i32), Vec<&Entity>>,
) -> Option<String> {
    if !matches!(e, Entity::Bridge(_)) {
        return None;
    }
    let openings = collect_feeding_inputs(e, by_pos, None);
    Some(connected_bridge_base(team_str(e.team), &openings))
}
