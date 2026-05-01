//! Engine `Entity` → asset-sprite-name conversions, and rendering of
//! the live engine state on top of the static map.

use eframe::egui;
use libre_engine::common::{Direction, Team};
use libre_engine::game::Game;
use libre_engine::game_map::Entity;
use titan_core::SpriteSet;
use titan_core::tile::tile_rect;

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

/// Paint priority for entity kinds. Mirrors the replay viewer's
/// `z_order` so the two apps render overlapping units identically:
/// flat ground stuff first (roads / markers / barriers), then
/// directional buildings, then production buildings, then turrets,
/// then cores, then BuilderBots last so they always sit on top.
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
    for (id, e) in entries {
        paint_entity(painter, atlas, id, e, ts, origin, zoom, show_ids);
    }
}

#[allow(clippy::too_many_arguments)]
fn paint_entity(
    painter: &egui::Painter,
    atlas: &SpriteSet,
    id: i32,
    e: &Entity,
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
    let name = sprite_name(e);
    if let Some(tex) = atlas.get(&name) {
        painter.image(
            tex,
            rect,
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
