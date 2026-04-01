use eframe::egui;
use egui::{Color32, Mesh, Pos2, Rect, Shape, Stroke, StrokeKind, Vec2};

use crate::app::App;
use crate::proto;
use crate::state::{Entity, EntityKind, Indicator};

const BG_COLOR: Color32 = Color32::from_rgb(0x1d, 0x15, 0x0f);
const TILE_COLOR: Color32 = Color32::from_rgb(0x2a, 0x20, 0x18);
const CURSOR_COLOR: Color32 = Color32::from_rgba_premultiplied(0x80, 0x80, 0x00, 0x80);
const SELECTED_COLOR: Color32 = Color32::from_rgba_premultiplied(0x00, 0x80, 0x00, 0x80);

fn tile_rect(x: i32, y: i32, ts: f32, origin: Pos2, zoom: f32) -> Rect {
    let px = (x as f32).mul_add(ts * zoom, origin.x);
    let py = (y as f32).mul_add(ts * zoom, origin.y);
    Rect::from_min_size(Pos2::new(px, py), Vec2::splat(ts * zoom))
}

fn tile_center(x: i32, y: i32, ts: f32, origin: Pos2, zoom: f32) -> Pos2 {
    Pos2::new(
        (x as f32 + 0.5).mul_add(ts * zoom, origin.x),
        (y as f32 + 0.5).mul_add(ts * zoom, origin.y),
    )
}

fn premul(c: u8) -> u8 {
    (u16::from(c) * 0xc0 / 0xff) as u8
}

#[allow(clippy::too_many_lines)]
pub fn render_map_panel(ui: &mut egui::Ui, app: &mut App) {
    egui::CentralPanel::default().show_inside(ui, |ui| {
        let (response, painter) =
            ui.allocate_painter(ui.available_size(), egui::Sense::click_and_drag());
        let rect = response.rect;

        let ts = app.atlas.tile_size;
        let zoom = app.zoom;
        let origin = Pos2::new(rect.left() + app.pan.x, rect.top() + app.pan.y);

        painter.rect_filled(rect, 0.0, BG_COLOR);

        for gy in 0..app.game.height {
            for gx in 0..app.game.width {
                let env = app
                    .game
                    .env
                    .get(gy as usize)
                    .and_then(|row| row.get(gx as usize))
                    .copied()
                    .unwrap_or(proto::Environment::EnvEmpty);

                let r = tile_rect(gx, gy, ts, origin, zoom);
                match env {
                    proto::Environment::EnvWall => {
                        if let Some(tex) = app.atlas.get("natural_wall") {
                            painter.image(
                                tex.id(),
                                r,
                                Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)),
                                Color32::from_rgb(0x30, 0x0c, 0x08),
                            );
                        } else {
                            painter.rect_filled(r, 0.0, Color32::from_rgb(0x30, 0x0c, 0x08));
                        }
                    }
                    proto::Environment::EnvOreTitanium => {
                        draw_sprite(&painter, app, "titanium_ore", r);
                    }
                    proto::Environment::EnvOreAxionite => {
                        draw_sprite(&painter, app, "axionite_ore", r);
                    }
                    proto::Environment::EnvEmpty => {
                        painter.rect_filled(r, 0.0, TILE_COLOR);
                    }
                }
            }
        }

        let turn_state = &app.game.turns[app.turn];
        let mut entities: Vec<&Entity> = turn_state.entities.values().collect();
        entities.sort_by_key(|e| entity_z_order(&e.kind));

        for e in &entities {
            if matches!(e.kind, EntityKind::Core { .. }) {
                let road_name = match e.team {
                    proto::Team::A => "road_gold",
                    proto::Team::B => "road_silver",
                };
                for dy in -1..=1_i32 {
                    for dx in -1..=1_i32 {
                        let rx = (e.pos.0 + dx).max(0);
                        let ry = (e.pos.1 + dy).max(0);
                        let r = tile_rect(rx, ry, ts, origin, zoom);
                        draw_sprite(&painter, app, road_name, r);
                    }
                }
            }

            let sprite_name = entity_sprite_name(e);
            let r = if matches!(e.kind, EntityKind::Core { .. }) {
                let px = ((e.pos.0 - 1).max(0) as f32 * ts).mul_add(zoom, origin.x);
                let py = ((e.pos.1 - 1).max(0) as f32 * ts).mul_add(zoom, origin.y);
                Rect::from_min_size(Pos2::new(px, py), Vec2::splat(ts * 3.0 * zoom))
            } else {
                tile_rect(e.pos.0, e.pos.1, ts, origin, zoom)
            };
            draw_sprite(&painter, app, &sprite_name, r);

            if !matches!(
                e.kind,
                EntityKind::Core { .. } | EntityKind::CoreEdge { .. }
            ) && let Some(res_name) = entity_resource_sprite(e)
            {
                let center = tile_center(e.pos.0, e.pos.1, ts, origin, zoom);
                let half = ts * zoom * 0.25;
                let rr = Rect::from_center_size(center, Vec2::splat(half * 2.0));
                draw_sprite(&painter, app, res_name, rr);
            }
        }

        for e in turn_state.entities.values() {
            if let EntityKind::Bridge { target, .. } = &e.kind {
                let beam_name = match e.team {
                    proto::Team::A => "bridge_gold",
                    proto::Team::B => "bridge_silver",
                };
                let from = tile_center(e.pos.0, e.pos.1, ts, origin, zoom);
                let to = tile_center(target.0, target.1, ts, origin, zoom);
                let width = ts * zoom * 0.6;
                draw_beam(&painter, app, beam_name, from, to, width);
            }
        }

        if app.show_indicators {
            for ind in &turn_state.indicators {
                match *ind {
                    Indicator::Line {
                        pos_a,
                        pos_b,
                        r,
                        g,
                        b,
                    } => {
                        let from = tile_center(pos_a.0, pos_a.1, ts, origin, zoom);
                        let to = tile_center(pos_b.0, pos_b.1, ts, origin, zoom);
                        let color =
                            Color32::from_rgba_premultiplied(premul(r), premul(g), premul(b), 0xc0);
                        painter.line_segment([from, to], Stroke::new(2.0 * zoom, color));
                    }
                    Indicator::Dot { pos, r, g, b } => {
                        let c = tile_center(pos.0, pos.1, ts, origin, zoom);
                        let color =
                            Color32::from_rgba_premultiplied(premul(r), premul(g), premul(b), 0xc0);
                        painter.circle_filled(c, ts * zoom * 0.25, color);
                    }
                }
            }
        }

        if let Some(sel_id) = app.selected_entity
            && let Some(e) = turn_state.entities.get(&sel_id)
        {
            let r = tile_rect(e.pos.0, e.pos.1, ts, origin, zoom);
            painter.rect_stroke(
                r,
                0.0,
                Stroke::new(2.0, SELECTED_COLOR),
                StrokeKind::Outside,
            );

            if let EntityKind::Bridge { target, .. } = &e.kind {
                let from = tile_center(e.pos.0, e.pos.1, ts, origin, zoom);
                let to = tile_center(target.0, target.1, ts, origin, zoom);
                painter.line_segment([from, to], Stroke::new(2.0, Color32::GREEN));
            }
        }

        {
            let r = tile_rect(app.cursor.0, app.cursor.1, ts, origin, zoom);
            painter.rect_stroke(r, 0.0, Stroke::new(2.0, CURSOR_COLOR), StrokeKind::Outside);
        }

        if response.dragged_by(egui::PointerButton::Primary) {
            app.pan += response.drag_delta();
            ui.ctx().set_cursor_icon(egui::CursorIcon::Grabbing);
        } else if response.clicked()
            && let Some(pos) = response.interact_pointer_pos()
        {
            let gx = ((pos.x - origin.x) / (ts * zoom)) as i32;
            let gy = ((pos.y - origin.y) / (ts * zoom)) as i32;
            app.cursor = (
                gx.clamp(0, app.game.width - 1),
                gy.clamp(0, app.game.height - 1),
            );
            app.select_at_cursor();
        }

        if response.hovered() && !response.dragged()
            && let Some(pos) = ui.input(|i| i.pointer.hover_pos())
        {
            let gx = ((pos.x - origin.x) / (ts * zoom)) as i32;
            let gy = ((pos.y - origin.y) / (ts * zoom)) as i32;
            if gx >= 0 && gx < app.game.width && gy >= 0 && gy < app.game.height {
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
            }
        }

        let raw_scroll = ui.input(|i| {
            let mut total = 0.0_f32;
            for event in &i.raw.events {
                if let egui::Event::MouseWheel { delta, .. } = event {
                    total += delta.y;
                }
            }
            total
        });
        if raw_scroll != 0.0 && response.hovered() {
            let factor = (raw_scroll * 0.1).exp();
            if let Some(pointer) = ui.input(|i| i.pointer.hover_pos()) {
                let old_zoom = app.zoom;
                app.zoom = (app.zoom * factor).clamp(0.1, 10.0);
                let dz = app.zoom / old_zoom;
                app.pan.x =
                    (pointer.x - app.pan.x - rect.left()).mul_add(-dz, pointer.x) - rect.left();
                app.pan.y =
                    (pointer.y - app.pan.y - rect.top()).mul_add(-dz, pointer.y) - rect.top();
            }
        }
    });
}

fn draw_beam(
    painter: &egui::Painter,
    app: &App,
    name: &str,
    from: Pos2,
    to: Pos2,
    width: f32,
) {
    let Some(tex) = app.atlas.get(name) else {
        return;
    };
    let dx = to.x - from.x;
    let dy = to.y - from.y;
    let len = dx.hypot(dy);
    if len < 0.5 {
        return;
    }
    let ux = dx / len;
    let uy = dy / len;
    let vx = -uy * width * 0.5;
    let vy = ux * width * 0.5;

    let tl = Pos2::new(from.x + vx, from.y + vy);
    let bl = Pos2::new(from.x - vx, from.y - vy);
    let tr = Pos2::new(to.x + vx, to.y + vy);
    let br = Pos2::new(to.x - vx, to.y - vy);

    let mut mesh = Mesh::with_texture(tex.id());
    mesh.add_triangle(0, 1, 2);
    mesh.add_triangle(2, 1, 3);
    mesh.colored_vertex(tl, Color32::WHITE);
    mesh.colored_vertex(bl, Color32::WHITE);
    mesh.colored_vertex(tr, Color32::WHITE);
    mesh.colored_vertex(br, Color32::WHITE);
    mesh.vertices[0].uv = Pos2::new(0.0, 0.0);
    mesh.vertices[1].uv = Pos2::new(0.0, 1.0);
    mesh.vertices[2].uv = Pos2::new(1.0, 0.0);
    mesh.vertices[3].uv = Pos2::new(1.0, 1.0);

    painter.add(Shape::mesh(mesh));
}

fn draw_sprite(painter: &egui::Painter, app: &App, name: &str, rect: Rect) {
    if let Some(tex) = app.atlas.get(name) {
        painter.image(
            tex.id(),
            rect,
            Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)),
            Color32::WHITE,
        );
    }
}

fn entity_sprite_name(e: &Entity) -> String {
    let team = match e.team {
        proto::Team::A => "gold",
        proto::Team::B => "silver",
    };
    match &e.kind {
        EntityKind::BuilderBot { .. } => format!("builderbot_front_{team}"),
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => format!("base_{team}"),
        EntityKind::Conveyor { dir, .. } => {
            let d = dir_suffix(*dir);
            format!("conveyor_{team}_{d}")
        }
        EntityKind::ArmouredConveyor { dir, .. } => {
            let d = dir_suffix(*dir);
            format!("armoured_conveyor_{team}_{d}")
        }
        EntityKind::Splitter { dir, .. } => {
            let d = dir_suffix(*dir);
            format!("splitter_{d}_{team}")
        }
        EntityKind::Bridge { .. } => format!("bridge_stand_{team}"),
        EntityKind::Harvester { .. } => format!("harvester_{team}"),
        EntityKind::Foundry { .. } => format!("foundry_{team}"),
        EntityKind::Road => format!("road_{team}"),
        EntityKind::Barrier => format!("barrier_{team}"),
        EntityKind::Marker { .. } => format!("marker_{team}"),
        EntityKind::Gunner { dir, .. } => {
            let d = dir_suffix(*dir);
            format!("gunner_{d}_{team}")
        }
        EntityKind::Sentinel { dir, .. } => {
            let d = dir_suffix(*dir);
            format!("sentinel_{d}_{team}")
        }
        EntityKind::Breach { dir, .. } => {
            let d = dir_suffix(*dir);
            format!("breach_{d}_{team}")
        }
        EntityKind::Launcher { .. } => format!("launcher_{team}"),
    }
}

const fn dir_suffix(dir: proto::Direction) -> &'static str {
    match dir {
        proto::Direction::DirNorth | proto::Direction::DirCentre => "n",
        proto::Direction::DirNortheast => "ne",
        proto::Direction::DirEast => "e",
        proto::Direction::DirSoutheast => "se",
        proto::Direction::DirSouth => "s",
        proto::Direction::DirSouthwest => "sw",
        proto::Direction::DirWest => "w",
        proto::Direction::DirNorthwest => "nw",
    }
}

const fn entity_resource_sprite(e: &Entity) -> Option<&'static str> {
    let res = match &e.kind {
        EntityKind::Conveyor { stored, .. }
        | EntityKind::ArmouredConveyor { stored, .. }
        | EntityKind::Splitter { stored, .. }
        | EntityKind::Bridge { stored, .. }
        | EntityKind::Foundry { stored } => *stored,
        _ => return None,
    };
    match res {
        proto::ResourceType::ResourceTitanium => Some("titanium"),
        proto::ResourceType::ResourceRawAxionite => Some("axionite_raw"),
        proto::ResourceType::ResourceRefinedAxionite => Some("axionite_processed"),
        proto::ResourceType::ResourceNone => None,
    }
}

const fn entity_z_order(kind: &EntityKind) -> i32 {
    match kind {
        EntityKind::Road => 0,
        EntityKind::Marker { .. } => 1,
        EntityKind::Barrier => 2,
        EntityKind::CoreEdge { .. } => 3,
        EntityKind::Conveyor { .. }
        | EntityKind::ArmouredConveyor { .. }
        | EntityKind::Splitter { .. }
        | EntityKind::Bridge { .. } => 4,
        EntityKind::Harvester { .. } | EntityKind::Foundry { .. } => 5,
        EntityKind::Gunner { .. }
        | EntityKind::Sentinel { .. }
        | EntityKind::Breach { .. }
        | EntityKind::Launcher { .. } => 6,
        EntityKind::Core { .. } => 7,
        EntityKind::BuilderBot { .. } => 8,
    }
}
