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
                        if let Some(tex_id) = app.atlas.get("natural_wall") {
                            painter.image(
                                tex_id,
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

            if e.hp < e.max_hp && e.max_hp > 0 {
                let tr = tile_rect(e.pos.0, e.pos.1, ts, origin, zoom);
                let bar_h = (2.0 * zoom).max(1.0);
                let bar_y = tr.bottom() - bar_h;
                let bg =
                    Rect::from_min_size(Pos2::new(tr.left(), bar_y), Vec2::new(tr.width(), bar_h));
                painter.rect_filled(bg, 0.0, Color32::from_rgba_premultiplied(0, 0, 0, 0x80));
                let frac = e.hp as f32 / e.max_hp as f32;
                let r_ch = ((1.0 - frac) * 255.0) as u8;
                let g_ch = (frac * 255.0) as u8;
                let fill = Rect::from_min_size(
                    Pos2::new(tr.left(), bar_y),
                    Vec2::new(tr.width() * frac, bar_h),
                );
                painter.rect_filled(fill, 0.0, Color32::from_rgb(r_ch, g_ch, 0));
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

        if app.show_flow {
            draw_flow_overlay(&painter, app, turn_state, ts, origin, zoom);
        }

        for field_name in &app.vis_overlays {
            draw_vis_overlay(&painter, app, turn_state, field_name, ts, origin, zoom);
        }

        for ind in &turn_state.indicators {
            let should_draw = match *ind {
                Indicator::Line { id, .. } | Indicator::Dot { id, .. } => {
                    app.show_indicators || app.selected_entity == Some(id)
                }
            };
            if !should_draw {
                continue;
            }
            match *ind {
                Indicator::Line {
                    pos_a,
                    pos_b,
                    r,
                    g,
                    b,
                    ..
                } => {
                    let from = tile_center(pos_a.0, pos_a.1, ts, origin, zoom);
                    let to = tile_center(pos_b.0, pos_b.1, ts, origin, zoom);
                    let color =
                        Color32::from_rgba_premultiplied(premul(r), premul(g), premul(b), 0xc0);
                    painter.line_segment([from, to], Stroke::new(2.0 * zoom, color));
                }
                Indicator::Dot { pos, r, g, b, .. } => {
                    let c = tile_center(pos.0, pos.1, ts, origin, zoom);
                    let color =
                        Color32::from_rgba_premultiplied(premul(r), premul(g), premul(b), 0xc0);
                    painter.circle_filled(c, ts * zoom * 0.25, color);
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

            if app.show_ranges {
                draw_range_overlay(&painter, e, &app.game, ts, origin, zoom);
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

        if response.hovered()
            && !response.dragged()
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

fn radius_tiles(cx: i32, cy: i32, r_sq: i32) -> Vec<(i32, i32)> {
    let r = (r_sq as f32).sqrt().ceil() as i32;
    let mut tiles = Vec::new();
    for dy in -r..=r {
        for dx in -r..=r {
            if dx * dx + dy * dy <= r_sq {
                tiles.push((cx + dx, cy + dy));
            }
        }
    }
    tiles
}

const fn dir_delta_map(dir: proto::Direction) -> (i32, i32) {
    match dir {
        proto::Direction::DirNorth => (0, -1),
        proto::Direction::DirSouth => (0, 1),
        proto::Direction::DirEast => (1, 0),
        proto::Direction::DirWest => (-1, 0),
        proto::Direction::DirNortheast => (1, -1),
        proto::Direction::DirSoutheast => (1, 1),
        proto::Direction::DirSouthwest => (-1, 1),
        proto::Direction::DirNorthwest => (-1, -1),
        proto::Direction::DirCentre => (0, 0),
    }
}

fn gunner_attack_tiles(cx: i32, cy: i32, dir: proto::Direction, r_sq: i32) -> Vec<(i32, i32)> {
    let (dx, dy) = dir_delta_map(dir);
    if dx == 0 && dy == 0 {
        return Vec::new();
    }
    let mut tiles = Vec::new();
    let mut x = cx + dx;
    let mut y = cy + dy;
    loop {
        let dist_sq = (x - cx) * (x - cx) + (y - cy) * (y - cy);
        if dist_sq > r_sq {
            break;
        }
        tiles.push((x, y));
        x += dx;
        y += dy;
    }
    tiles
}

fn sentinel_attack_tiles(cx: i32, cy: i32, dir: proto::Direction, r_sq: i32) -> Vec<(i32, i32)> {
    let (dx, dy) = dir_delta_map(dir);
    if dx == 0 && dy == 0 {
        return Vec::new();
    }
    let mut tiles = Vec::new();
    let mut x = cx + dx;
    let mut y = cy + dy;
    loop {
        let dist_sq = (x - cx) * (x - cx) + (y - cy) * (y - cy);
        if dist_sq > r_sq {
            break;
        }
        for cdy in -1..=1_i32 {
            for cdx in -1..=1_i32 {
                let tx = x + cdx;
                let ty = y + cdy;
                if (tx, ty) != (cx, cy) {
                    let d = (tx - cx) * (tx - cx) + (ty - cy) * (ty - cy);
                    if d <= r_sq && !tiles.contains(&(tx, ty)) {
                        tiles.push((tx, ty));
                    }
                }
            }
        }
        x += dx;
        y += dy;
    }
    tiles
}

fn breach_attack_tiles(cx: i32, cy: i32, dir: proto::Direction, r_sq: i32) -> Vec<(i32, i32)> {
    let (dx, dy) = dir_delta_map(dir);
    if dx == 0 && dy == 0 {
        return Vec::new();
    }
    let mut tiles = Vec::new();
    let r = (r_sq as f32).sqrt().ceil() as i32;
    for oy in -r..=r {
        for ox in -r..=r {
            if ox == 0 && oy == 0 {
                continue;
            }
            let dist_sq = ox * ox + oy * oy;
            if dist_sq > r_sq {
                continue;
            }
            let dot = ox * dx + oy * dy;
            if dot > 0 || (dot == 0 && (ox * dy - oy * dx).abs() <= 0) {
                tiles.push((cx + ox, cy + oy));
            }
        }
    }
    tiles
}

fn draw_tile_outline(
    painter: &egui::Painter,
    tiles: &[(i32, i32)],
    ts: f32,
    origin: Pos2,
    zoom: f32,
    color: Color32,
) {
    use std::collections::HashSet;
    let set: HashSet<(i32, i32)> = tiles.iter().copied().collect();
    let stroke = Stroke::new((1.5 * zoom).max(1.0), color);
    let sz = ts * zoom;

    for &(gx, gy) in tiles {
        let px = (gx as f32).mul_add(sz, origin.x);
        let py = (gy as f32).mul_add(sz, origin.y);

        if !set.contains(&(gx, gy - 1)) {
            painter.line_segment([Pos2::new(px, py), Pos2::new(px + sz, py)], stroke);
        }
        if !set.contains(&(gx, gy + 1)) {
            painter.line_segment(
                [Pos2::new(px, py + sz), Pos2::new(px + sz, py + sz)],
                stroke,
            );
        }
        if !set.contains(&(gx - 1, gy)) {
            painter.line_segment([Pos2::new(px, py), Pos2::new(px, py + sz)], stroke);
        }
        if !set.contains(&(gx + 1, gy)) {
            painter.line_segment(
                [Pos2::new(px + sz, py), Pos2::new(px + sz, py + sz)],
                stroke,
            );
        }
    }
}

fn draw_range_overlay(
    painter: &egui::Painter,
    e: &Entity,
    game: &crate::state::GameState,
    ts: f32,
    origin: Pos2,
    zoom: f32,
) {
    let (cx, cy) = e.pos;
    let blue = Color32::from_rgba_premultiplied(0x00, 0x00, 0xff, 0xc0);
    let red = Color32::from_rgba_premultiplied(0xff, 0x00, 0x00, 0xc0);

    let clamp = |tiles: &mut Vec<(i32, i32)>| {
        tiles.retain(|&(x, y)| x >= 0 && x < game.width && y >= 0 && y < game.height);
    };

    match &e.kind {
        EntityKind::BuilderBot { .. } => {
            let mut vision = radius_tiles(cx, cy, 20);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut action = radius_tiles(cx, cy, 2);
            clamp(&mut action);
            draw_tile_outline(painter, &action, ts, origin, zoom, red);
        }
        EntityKind::Core { .. } => {
            let mut vision = radius_tiles(cx, cy, 36);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut action = radius_tiles(cx, cy, 8);
            clamp(&mut action);
            draw_tile_outline(painter, &action, ts, origin, zoom, red);
        }
        EntityKind::Gunner { dir, .. } => {
            let mut vision = radius_tiles(cx, cy, 13);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack = gunner_attack_tiles(cx, cy, *dir, 13);
            clamp(&mut attack);
            draw_tile_outline(painter, &attack, ts, origin, zoom, red);
        }
        EntityKind::Sentinel { dir, .. } => {
            let mut vision = radius_tiles(cx, cy, 32);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack = sentinel_attack_tiles(cx, cy, *dir, 32);
            clamp(&mut attack);
            draw_tile_outline(painter, &attack, ts, origin, zoom, red);
        }
        EntityKind::Breach { dir, .. } => {
            let mut vision = radius_tiles(cx, cy, 13);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack = breach_attack_tiles(cx, cy, *dir, 5);
            clamp(&mut attack);
            draw_tile_outline(painter, &attack, ts, origin, zoom, red);
        }
        EntityKind::Launcher { .. } => {
            let mut vision = radius_tiles(cx, cy, 26);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack = radius_tiles(cx, cy, 26);
            clamp(&mut attack);
            draw_tile_outline(painter, &attack, ts, origin, zoom, red);
        }
        _ => {}
    }
}

#[allow(clippy::many_single_char_names, clippy::too_many_lines)]
fn draw_vis_overlay(
    painter: &egui::Painter,
    app: &App,
    turn_state: &crate::state::TurnState,
    field_name: &str,
    ts: f32,
    origin: Pos2,
    zoom: f32,
) {
    let id = app.selected_entity.unwrap_or(-1);
    let Some(jsons) = turn_state.vis_data.get(&id) else {
        return;
    };
    let fields = crate::vis::parse_vis(jsons);
    let Some(field) = fields.get(field_name) else {
        return;
    };

    let w = app.game.width as usize;
    let h = app.game.height as usize;

    match field {
        crate::vis::VisField::Grid { data, palette } => {
            let (mut min_v, mut max_v) = (f64::MAX, f64::MIN);
            for v in data.iter().flatten() {
                if !crate::vis::is_special(palette, *v) {
                    if *v < min_v {
                        min_v = *v;
                    }
                    if *v > max_v {
                        max_v = *v;
                    }
                }
            }
            if min_v > max_v {
                min_v = 0.0;
                max_v = 1.0;
            }

            let font = egui::FontId::monospace(8.0 * zoom.min(2.0));

            for gy in 0..h {
                for gx in 0..w {
                    let i = gy * w + gx;
                    if i >= data.len() {
                        continue;
                    }
                    let Some(v) = data[i] else {
                        continue;
                    };
                    let Some(c) = crate::vis::sample_palette(palette, v, min_v, max_v) else {
                        continue;
                    };
                    if c.a == 0 {
                        continue;
                    }
                    let r = tile_rect(gx as i32, gy as i32, ts, origin, zoom);
                    painter.rect_filled(
                        r,
                        0.0,
                        Color32::from_rgba_premultiplied(c.r, c.g, c.b, c.a),
                    );

                    if zoom > 0.8 {
                        let label = if (v - v.round()).abs() < 1e-6 {
                            format!("{}", v as i64)
                        } else if v.abs() < 100.0 {
                            format!("{v:.2}")
                        } else {
                            format!("{v:.0}")
                        };
                        painter.text(
                            egui::pos2(r.left() + 1.0, r.top() + 1.0),
                            egui::Align2::LEFT_TOP,
                            label,
                            font.clone(),
                            Color32::WHITE,
                        );
                    }
                }
            }
        }
        crate::vis::VisField::Tiles { data } => {
            let color = Color32::from_rgba_premultiplied(0xff, 0xff, 0x00, 0x60);
            for &[gx, gy] in data {
                let r = tile_rect(gx, gy, ts, origin, zoom);
                painter.rect_filled(r, 0.0, color);
            }
        }
        crate::vis::VisField::VectorField {
            angles,
            magnitudes,
        } => {
            let arrow_color = Color32::from_rgba_premultiplied(0xff, 0xff, 0xff, 0xc0);
            let max_mag = magnitudes
                .as_ref()
                .and_then(|m| m.iter().copied().reduce(f64::max))
                .unwrap_or(1.0)
                .max(1e-9);

            for gy in 0..h {
                for gx in 0..w {
                    let i = gy * w + gx;
                    if i >= angles.len() {
                        continue;
                    }
                    let Some(angle) = angles[i] else {
                        continue;
                    };
                    let mag_frac = magnitudes
                        .as_ref()
                        .map_or(0.35, |m| (m[i] / max_mag * 0.4) as f32);
                    let center = tile_center(gx as i32, gy as i32, ts, origin, zoom);
                    let half_len = ts * zoom * mag_frac;
                    let dx = (angle as f32).cos() * half_len;
                    let dy = (angle as f32).sin() * half_len;
                    let tip = Pos2::new(center.x + dx, center.y + dy);
                    let tail = Pos2::new(center.x - dx, center.y - dy);
                    let stroke = Stroke::new((1.5 * zoom).max(1.0), arrow_color);
                    painter.line_segment([tail, tip], stroke);

                    let head_len = 3.0 * zoom;
                    let half = head_len * 0.5;
                    let ux = (angle as f32).cos();
                    let uy = (angle as f32).sin();
                    let bx = (-ux).mul_add(head_len, tip.x);
                    let by = (-uy).mul_add(head_len, tip.y);
                    let lx = uy.mul_add(half, bx);
                    let ly = (-ux).mul_add(half, by);
                    let rx = (-uy).mul_add(half, bx);
                    let ry = ux.mul_add(half, by);
                    painter.line_segment(
                        [tip, Pos2::new(lx, ly)],
                        stroke,
                    );
                    painter.line_segment(
                        [tip, Pos2::new(rx, ry)],
                        stroke,
                    );
                }
            }
        }
        crate::vis::VisField::Scalar { .. } => {}
    }
}

#[allow(clippy::many_single_char_names)]
fn draw_flow_overlay(
    painter: &egui::Painter,
    app: &App,
    turn_state: &crate::state::TurnState,
    ts: f32,
    origin: Pos2,
    zoom: f32,
) {
    let w = app.game.width as usize;
    let h = app.game.height as usize;
    let flow = crate::flow::compute_flow(turn_state, &app.game.env, w, h);

    let font = egui::FontId::monospace(9.0 * zoom.min(2.0));

    for gy in 0..h {
        for gx in 0..w {
            let i = gy * w + gx;
            let ti = flow.ti[i];
            let ax = flow.ax[i];
            let rax = flow.rax[i];
            let excess = flow.excess[i];
            let total = ti + ax + rax;

            let r = tile_rect(gx as i32, gy as i32, ts, origin, zoom);

            if excess > 0.01 {
                let red_frac = (excess / total.max(0.01)).min(1.0);
                let g = ((1.0 - red_frac) * 0.6 * 255.0) as u8;
                let r_ch = (red_frac * 0.8 * 255.0) as u8;
                painter.rect_filled(r, 0.0, Color32::from_rgba_premultiplied(r_ch, g, 0, 0x50));
            } else if total > 0.01 {
                let green = (total.min(1.0) * 0.5 * 255.0) as u8;
                painter.rect_filled(r, 0.0, Color32::from_rgba_premultiplied(0, green, 0, 0x30));
            } else {
                continue;
            }

            if zoom > 0.5 {
                use std::fmt::Write;
                let mut label = String::new();
                if ti > 0.005 {
                    let _ = write!(label, "T{ti:.2}");
                }
                if ax > 0.005 {
                    if !label.is_empty() {
                        label.push('\n');
                    }
                    let _ = write!(label, "A{ax:.2}");
                }
                if rax > 0.005 {
                    if !label.is_empty() {
                        label.push('\n');
                    }
                    let _ = write!(label, "R{rax:.2}");
                }

                if !label.is_empty() {
                    painter.text(
                        egui::pos2(r.left() + 1.0, r.top() + 1.0),
                        egui::Align2::LEFT_TOP,
                        label,
                        font.clone(),
                        Color32::WHITE,
                    );
                }
            }
        }
    }
}

fn draw_beam(painter: &egui::Painter, app: &App, name: &str, from: Pos2, to: Pos2, width: f32) {
    let Some(tex_id) = app.atlas.get(name) else {
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

    let mut mesh = Mesh::with_texture(tex_id);
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
    if let Some(tex_id) = app.atlas.get(name) {
        painter.image(
            tex_id,
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
