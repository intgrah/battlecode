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

pub fn render_entities(
    painter: &egui::Painter,
    atlas: &SpriteSet,
    game: &Game,
    ts: f32,
    origin: egui::Pos2,
    zoom: f32,
    show_ids: bool,
) {
    // Sort by id so paint order is deterministic — buildings drawn
    // before bots that stand on them.
    let mut ids: Vec<i32> = game.entities.keys().copied().collect();
    ids.sort_unstable();
    for id in ids {
        let Some(e) = game.entities.get(&id) else {
            continue;
        };
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
}
