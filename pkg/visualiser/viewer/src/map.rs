use cambc_common::constants;
use cambc_common::map::BG_COLOR;
use cambc_common::tile::{premul, tile_center, tile_rect, tile_rect_f32};
use eframe::egui;
use egui::{Color32, Mesh, Pos2, Rect, Shape, Stroke, StrokeKind, Vec2};

use crate::app::App;
use crate::entity;
use crate::proto;
use crate::state::{Entity, EntityKind, Indicator};

const CURSOR_COLOR: Color32 = Color32::from_rgba_premultiplied(0x80, 0x80, 0x00, 0x80);
const SELECTED_COLOR: Color32 = Color32::from_rgba_premultiplied(0x00, 0x80, 0x00, 0x80);
const HOVER_COLOR: Color32 = Color32::from_rgba_premultiplied(0xff, 0xff, 0xff, 0xff);
const PINNED_COLOR: Color32 = Color32::from_rgba_premultiplied(0xc0, 0xe0, 0x40, 0xc0);

fn build_static_map_shapes(app: &App, origin: Pos2) -> Vec<Shape> {
    cambc_common::map::build_static_map_shapes(
        &app.atlas,
        app.game.width,
        app.game.height,
        app.zoom,
        origin,
        |gx, gy| {
            app.game
                .env
                .get(gy as usize)
                .and_then(|row| row.get(gx as usize))
                .copied()
                .unwrap_or(proto::Environment::EnvEmpty)
        },
    )
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

        let coord_font = egui::FontId::monospace(10.0 * zoom.clamp(0.3, 1.0));
        let coord_dim = Color32::from_rgb(0x70, 0x70, 0x70);
        let coord_bright = Color32::WHITE;
        let (sel_x, sel_y) = app.cursor;
        let sz = ts * zoom;
        for gx in 0..app.game.width {
            let x = (gx as f32 + 0.5).mul_add(sz, origin.x);
            let y = origin.y - 2.0;
            let color = if gx == sel_x { coord_bright } else { coord_dim };
            painter.text(
                Pos2::new(x, y),
                egui::Align2::CENTER_BOTTOM,
                format!("{gx}"),
                coord_font.clone(),
                color,
            );
        }
        for gy in 0..app.game.height {
            let x = origin.x - 2.0;
            let y = (gy as f32 + 0.5).mul_add(sz, origin.y);
            let color = if gy == sel_y { coord_bright } else { coord_dim };
            painter.text(
                Pos2::new(x, y),
                egui::Align2::RIGHT_CENTER,
                format!("{gy}"),
                coord_font.clone(),
                color,
            );
        }

        let origin_vec = egui::Vec2::new(origin.x, origin.y);
        #[allow(clippy::float_cmp)]
        if origin_vec != app.cached_map_origin || zoom != app.cached_map_zoom {
            app.cached_map_shapes = build_static_map_shapes(app, origin);
            app.cached_map_origin = origin_vec;
            app.cached_map_zoom = zoom;
        }
        painter.extend(app.cached_map_shapes.clone());

        let turn_state = &app.game.turns[app.turn];
        let next_state = app.game.turns.get(app.turn + 1);
        let interp_t = app.interp_t;
        let animating_dests: std::collections::HashSet<(i32, i32)> =
            if app.playing && interp_t > 0.0 {
                turn_state.resource_moves.iter().map(|m| m.to).collect()
            } else {
                std::collections::HashSet::new()
            };
        let mut entities: Vec<&Entity> = turn_state.entities.values().collect();
        entities.sort_by_key(|e| entity::z_order(&e.kind));

        let by_pos: std::collections::HashMap<(i32, i32), Vec<&Entity>> =
            if app.show_connected_textures {
                let mut m: std::collections::HashMap<(i32, i32), Vec<&Entity>> =
                    std::collections::HashMap::new();
                for e in turn_state.entities.values() {
                    m.entry(e.pos).or_default().push(e);
                }
                m
            } else {
                std::collections::HashMap::new()
            };

        for e in &entities {
            if matches!(e.kind, EntityKind::Core { .. }) {
                let road_name = match (e.team, app.use_plain_roads) {
                    (proto::Team::A, false) => "road_gold",
                    (proto::Team::B, false) => "road_silver",
                    (proto::Team::A, true) => "road_gold_plain",
                    (proto::Team::B, true) => "road_silver_plain",
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

            // Interpolate builder bot positions between turns.
            let interp_pos: Option<(f32, f32)> = if matches!(e.kind, EntityKind::BuilderBot { .. })
            {
                next_state
                    .and_then(|ns| ns.entities.get(&e.id))
                    .map(|next_e| {
                        let t = interp_t;
                        (
                            ((next_e.pos.0 - e.pos.0) as f32).mul_add(t, e.pos.0 as f32),
                            ((next_e.pos.1 - e.pos.1) as f32).mul_add(t, e.pos.1 as f32),
                        )
                    })
            } else {
                None
            };

            let sprite_name = if app.show_connected_textures
                && let Some(n) = conveyor_junction_sprite_name(e, &by_pos)
                    .or_else(|| bridge_base_sprite_name(e, &by_pos))
            {
                n
            } else if app.use_plain_roads && matches!(e.kind, EntityKind::Road) {
                match e.team {
                    proto::Team::A => "road_gold_plain".to_string(),
                    proto::Team::B => "road_silver_plain".to_string(),
                }
            } else {
                entity::sprite_name(e)
            };
            let r = if matches!(e.kind, EntityKind::Core { .. }) {
                let px = ((e.pos.0 - 1).max(0) as f32 * ts).mul_add(zoom, origin.x);
                let py = ((e.pos.1 - 1).max(0) as f32 * ts).mul_add(zoom, origin.y);
                Rect::from_min_size(Pos2::new(px, py), Vec2::splat(ts * 3.0 * zoom))
            } else if let Some((ix, iy)) = interp_pos {
                tile_rect_f32(ix, iy, ts, origin, zoom)
            } else {
                tile_rect(e.pos.0, e.pos.1, ts, origin, zoom)
            };
            if app.highlight_builders && matches!(e.kind, EntityKind::BuilderBot { .. }) {
                let fill = match e.team {
                    proto::Team::A => Color32::from_rgba_premultiplied(0x00, 0xc8, 0xc8, 0x80),
                    proto::Team::B => Color32::from_rgba_premultiplied(0xc8, 0x00, 0xc8, 0x80),
                };
                let ring = match e.team {
                    proto::Team::A => Color32::from_rgb(0x00, 0xff, 0xff),
                    proto::Team::B => Color32::from_rgb(0xff, 0x00, 0xff),
                };
                let centre = r.center();
                let radius = r.width() * 0.55;
                painter.circle_filled(centre, radius, fill);
                painter.circle_stroke(centre, radius, Stroke::new((2.0 * zoom).max(1.5), ring));
            }
            let draw_rect = if matches!(e.kind, EntityKind::Marker { .. }) {
                Rect::from_center_size(r.center(), r.size() * 0.5)
            } else {
                r
            };
            draw_sprite(&painter, app, &sprite_name, draw_rect);

            if !matches!(
                e.kind,
                EntityKind::Core { .. } | EntityKind::CoreEdge { .. }
            ) && !animating_dests.contains(&e.pos)
                && let Some(res_name) = entity::resource_sprite(&e.kind)
            {
                let center = if let Some((ix, iy)) = interp_pos {
                    Pos2::new(
                        (ix + 0.5).mul_add(ts * zoom, origin.x),
                        (iy + 0.5).mul_add(ts * zoom, origin.y),
                    )
                } else {
                    tile_center(e.pos.0, e.pos.1, ts, origin, zoom)
                };
                let half = ts * zoom * 0.25;
                let rr = Rect::from_center_size(center, Vec2::splat(half * 2.0));
                draw_sprite(&painter, app, res_name, rr);
            }

            if e.hp < e.max_hp && e.max_hp > 0 {
                let tr = if let Some((ix, iy)) = interp_pos {
                    tile_rect_f32(ix, iy, ts, origin, zoom)
                } else {
                    tile_rect(e.pos.0, e.pos.1, ts, origin, zoom)
                };
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
                let beam_name = match (app.show_connected_textures, e.team) {
                    (true, proto::Team::A) => "bridge_beam_gold",
                    (true, proto::Team::B) => "bridge_beam_silver",
                    (false, proto::Team::A) => "bridge_gold",
                    (false, proto::Team::B) => "bridge_silver",
                };
                let from = tile_center(e.pos.0, e.pos.1, ts, origin, zoom);
                let to = tile_center(target.0, target.1, ts, origin, zoom);
                let width = ts * zoom * 0.6;
                draw_beam(&painter, app, beam_name, from, to, width);
            }
        }

        if app.playing && interp_t > 0.0 {
            for m in &turn_state.resource_moves {
                let sprite = match m.resource {
                    proto::ResourceType::ResourceTitanium => "titanium",
                    proto::ResourceType::ResourceRawAxionite => "axionite_raw",
                    proto::ResourceType::ResourceRefinedAxionite => "axionite_processed",
                    proto::ResourceType::ResourceNone => continue,
                };
                let x = ((m.to.0 - m.from.0) as f32).mul_add(interp_t, m.from.0 as f32 + 0.5);
                let y = ((m.to.1 - m.from.1) as f32).mul_add(interp_t, m.from.1 as f32 + 0.5);
                let center = Pos2::new(
                    x.mul_add(ts * zoom, origin.x),
                    y.mul_add(ts * zoom, origin.y),
                );
                let half = ts * zoom * 0.25;
                let r = Rect::from_center_size(center, Vec2::splat(half * 2.0));
                draw_sprite(&painter, app, sprite, r);
            }
        }

        if app.show_flow {
            draw_flow_overlay(&painter, app, ts, origin, zoom);
        }

        // Render every sticky-selected overlay, plus the transient
        // hover overlay (if any and not already in the sticky set).
        for field_name in &app.selected_vis_overlays {
            draw_vis_overlay(&painter, app, turn_state, field_name, ts, origin, zoom);
        }
        if let Some(field_name) = &app.hovered_vis_overlay
            && !app.selected_vis_overlays.contains(field_name)
        {
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

        for &(from, to) in &turn_state.fire_events {
            let a = tile_center(from.0, from.1, ts, origin, zoom);
            let b = tile_center(to.0, to.1, ts, origin, zoom);
            painter.line_segment(
                [a, b],
                Stroke::new(
                    2.0 * zoom,
                    Color32::from_rgba_premultiplied(0xee, 0xee, 0xee, 0xc0),
                ),
            );
        }

        for &pos in &turn_state.deaths {
            let r = tile_rect(pos.0, pos.1, ts, origin, zoom);
            painter.rect_stroke(
                r,
                0.0,
                Stroke::new(
                    2.0 * zoom,
                    Color32::from_rgba_premultiplied(0xcc, 0x33, 0x33, 0xc0),
                ),
                StrokeKind::Inside,
            );
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
                app.hover_tile = Some((gx, gy));
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
            }
        }

        if let Some((hx, hy)) = app.hover_tile {
            let r = tile_rect(hx, hy, ts, origin, zoom);
            painter.rect_stroke(
                r,
                0.0,
                Stroke::new(2.0, HOVER_COLOR),
                StrokeKind::Outside,
            );
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

fn gunner_attack_tiles(cx: i32, cy: i32, dir: proto::Direction, r_sq: i32) -> Vec<(i32, i32)> {
    let (dx, dy) = entity::dir_delta(dir);
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
    let (dx, dy) = entity::dir_delta(dir);
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
    let (dx, dy) = entity::dir_delta(dir);
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
            let mut vision = radius_tiles(cx, cy, constants::BUILDER_BOT_VISION_RADIUS_SQ);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut action = radius_tiles(cx, cy, constants::ACTION_RADIUS_SQ);
            clamp(&mut action);
            draw_tile_outline(painter, &action, ts, origin, zoom, red);
        }
        EntityKind::Core { .. } => {
            let mut vision = radius_tiles(cx, cy, constants::CORE_VISION_RADIUS_SQ);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut action = radius_tiles(cx, cy, constants::CORE_ACTION_RADIUS_SQ);
            clamp(&mut action);
            draw_tile_outline(painter, &action, ts, origin, zoom, red);
        }
        EntityKind::Gunner { dir, .. } => {
            let mut vision = radius_tiles(cx, cy, constants::GUNNER_VISION_RADIUS_SQ);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack = gunner_attack_tiles(cx, cy, *dir, constants::GUNNER_VISION_RADIUS_SQ);
            clamp(&mut attack);
            draw_tile_outline(painter, &attack, ts, origin, zoom, red);
        }
        EntityKind::Sentinel { dir, .. } => {
            let mut vision = radius_tiles(cx, cy, constants::SENTINEL_VISION_RADIUS_SQ);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack =
                sentinel_attack_tiles(cx, cy, *dir, constants::SENTINEL_VISION_RADIUS_SQ);
            clamp(&mut attack);
            draw_tile_outline(painter, &attack, ts, origin, zoom, red);
        }
        EntityKind::Breach { dir, .. } => {
            let mut vision = radius_tiles(cx, cy, constants::BREACH_VISION_RADIUS_SQ);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack = breach_attack_tiles(cx, cy, *dir, constants::BREACH_ATTACK_RADIUS_SQ);
            clamp(&mut attack);
            draw_tile_outline(painter, &attack, ts, origin, zoom, red);
        }
        EntityKind::Launcher { .. } => {
            let mut vision = radius_tiles(cx, cy, constants::LAUNCHER_VISION_RADIUS_SQ);
            clamp(&mut vision);
            draw_tile_outline(painter, &vision, ts, origin, zoom, blue);
            let mut attack = radius_tiles(cx, cy, constants::LAUNCHER_VISION_RADIUS_SQ);
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
    let Some(fields) = turn_state.vis_data.get(&id) else {
        return;
    };
    let Some(field) = fields.get(field_name) else {
        return;
    };

    let w = app.game.width as usize;
    let h = app.game.height as usize;

    match field.as_ref() {
        crate::vis::VisField::Grid { data, palette } => {
            let font = egui::FontId::monospace(8.0 * zoom.min(2.0));
            let is_bool = matches!(data, crate::vis::GridData::Bool(_));

            for gy in 0..h {
                for gx in 0..w {
                    let i = gy * w + gx;
                    let Some(v) = data.get_f64(i) else {
                        continue;
                    };
                    let Some(c) = crate::vis::sample_palette(palette, v) else {
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

                    // Bool grids carry no quantitative info — the
                    // colour already distinguishes true from false.
                    if !is_bool && zoom > 0.8 {
                        let label = match data.get_i64(i) {
                            Some(iv) if (v - v.round()).abs() < 1e-6 => format!("{iv}"),
                            _ if v.abs() < 100.0 => format!("{v:.2}"),
                            _ => format!("{v:.0}"),
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
            let color = Color32::from_rgba_premultiplied(0x80, 0x80, 0x30, 0x40);
            for &(gx, gy) in data {
                let r = tile_rect(gx, gy, ts, origin, zoom);
                painter.rect_filled(r, 0.0, color);
            }
        }
        crate::vis::VisField::VectorField(arrow_data) => {
            let arrows = &arrow_data.arrows;
            let arrow_color = Color32::from_rgba_premultiplied(0xff, 0xff, 0xff, 0xc0);
            let max_mag = arrows
                .iter()
                .filter_map(|a| a.map(|a| a.magnitude))
                .reduce(f32::max)
                .unwrap_or(1.0)
                .max(1e-9);

            for gy in 0..h {
                for gx in 0..w {
                    let i = gy * w + gx;
                    let Some(arrow) = arrows.get(i).copied().flatten() else {
                        continue;
                    };
                    let mag_frac = arrow.magnitude / max_mag * 0.4;
                    let center = tile_center(gx as i32, gy as i32, ts, origin, zoom);
                    let half_len = ts * zoom * mag_frac;
                    let dx = arrow.angle.cos() * half_len;
                    let dy = arrow.angle.sin() * half_len;
                    let tip = Pos2::new(center.x + dx, center.y + dy);
                    let tail = Pos2::new(center.x - dx, center.y - dy);
                    let stroke = Stroke::new((1.5 * zoom).max(1.0), arrow_color);
                    painter.line_segment([tail, tip], stroke);

                    let head_len = 3.0 * zoom;
                    let half = head_len * 0.5;
                    let ux = arrow.angle.cos();
                    let uy = arrow.angle.sin();
                    let bx = (-ux).mul_add(head_len, tip.x);
                    let by = (-uy).mul_add(head_len, tip.y);
                    let lx = uy.mul_add(half, bx);
                    let ly = (-ux).mul_add(half, by);
                    let rx = (-uy).mul_add(half, bx);
                    let ry = ux.mul_add(half, by);
                    painter.line_segment([tip, Pos2::new(lx, ly)], stroke);
                    painter.line_segment([tip, Pos2::new(rx, ry)], stroke);
                }
            }
        }
        crate::vis::VisField::Scalar { data } => {
            if let crate::vis::ScalarValue::Pos(x, y) = data {
                let r = tile_rect(*x, *y, ts, origin, zoom);
                painter.rect_stroke(
                    r,
                    0.0,
                    Stroke::new(2.0, PINNED_COLOR),
                    StrokeKind::Outside,
                );
            }
        }
    }
}

#[allow(clippy::many_single_char_names)]
fn draw_flow_overlay(painter: &egui::Painter, app: &App, ts: f32, origin: Pos2, zoom: f32) {
    let flow = crate::flow::compute_empirical_flow(&app.game, app.turn);
    let font = egui::FontId::monospace(9.0 * zoom.min(2.0));

    for (&(gx, gy), tf) in &flow.tiles {
        let total = tf.ti + tf.raw_ax + tf.refined_ax;
        if total < 0.005 {
            continue;
        }

        let r = tile_rect(gx, gy, ts, origin, zoom);

        let intensity = (total.min(1.0) * 0.5 * 255.0) as u8;
        if tf.stagnant {
            painter.rect_filled(
                r,
                0.0,
                Color32::from_rgba_premultiplied(intensity, 0, 0, 0x30),
            );
        } else {
            painter.rect_filled(
                r,
                0.0,
                Color32::from_rgba_premultiplied(0, intensity, 0, 0x30),
            );
        }

        if zoom > 0.5 {
            use std::fmt::Write;
            let mut label = String::new();
            let ti_color = Color32::from_rgb(0xc0, 0xc0, 0xc0);
            let ax_color = Color32::from_rgb(0x60, 0xd0, 0x60);
            let rax_color = Color32::from_rgb(0x80, 0x80, 0xff);

            if tf.ti > 0.005 {
                let _ = write!(label, "T{:.2}", tf.ti);
            }
            if tf.raw_ax > 0.005 {
                if !label.is_empty() {
                    label.push('\n');
                }
                let _ = write!(label, "A{:.2}", tf.raw_ax);
            }
            if tf.refined_ax > 0.005 {
                if !label.is_empty() {
                    label.push('\n');
                }
                let _ = write!(label, "R{:.2}", tf.refined_ax);
            }

            if !label.is_empty() {
                // Use dominant resource colour for the label
                let color = if tf.refined_ax >= tf.ti && tf.refined_ax >= tf.raw_ax {
                    rax_color
                } else if tf.raw_ax >= tf.ti {
                    ax_color
                } else {
                    ti_color
                };
                painter.text(
                    egui::pos2(r.left() + 1.0, r.top() + 1.0),
                    egui::Align2::LEFT_TOP,
                    label,
                    font.clone(),
                    color,
                );
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

const CARDINALS: [(i32, i32); 4] = [(0, -1), (1, 0), (0, 1), (-1, 0)];

const fn dir_unit(d: proto::Direction) -> Option<(i32, i32)> {
    match d {
        proto::Direction::DirNorth => Some((0, -1)),
        proto::Direction::DirEast => Some((1, 0)),
        proto::Direction::DirSouth => Some((0, 1)),
        proto::Direction::DirWest => Some((-1, 0)),
        _ => None,
    }
}

fn conveyor_feeds_into(neighbor: &Entity, target: (i32, i32)) -> bool {
    match &neighbor.kind {
        EntityKind::Conveyor { dir, .. } | EntityKind::ArmouredConveyor { dir, .. } => {
            let Some((dx, dy)) = dir_unit(*dir) else {
                return false;
            };
            (neighbor.pos.0 + dx, neighbor.pos.1 + dy) == target
        }
        EntityKind::Splitter { dir, .. } => {
            let Some((dx, dy)) = dir_unit(*dir) else {
                return false;
            };
            let back = (-dx, -dy);
            let delta = (target.0 - neighbor.pos.0, target.1 - neighbor.pos.1);
            CARDINALS.contains(&delta) && delta != back
        }
        EntityKind::Bridge { target: bt, .. } => *bt == target,
        EntityKind::Harvester { .. } | EntityKind::Foundry { .. } => true,
        _ => false,
    }
}

const fn dir_suffix_cardinal(d: (i32, i32)) -> Option<&'static str> {
    match d {
        (0, -1) => Some("n"),
        (1, 0) => Some("e"),
        (0, 1) => Some("s"),
        (-1, 0) => Some("w"),
        _ => None,
    }
}

fn bridge_base_sprite_name(
    entity: &Entity,
    by_pos: &std::collections::HashMap<(i32, i32), Vec<&Entity>>,
) -> Option<String> {
    if !matches!(entity.kind, EntityKind::Bridge { .. }) {
        return None;
    }
    let team_s = match entity.team {
        proto::Team::A => "gold",
        proto::Team::B => "silver",
    };
    let pos = entity.pos;
    let mut openings: Vec<(i32, i32)> = Vec::new();
    for (dx, dy) in CARDINALS {
        let n = (pos.0 + dx, pos.1 + dy);
        let feeds = by_pos.get(&n).is_some_and(|list| {
            list.iter()
                .any(|e| e.team == entity.team && conveyor_feeds_into(e, pos))
        });
        if feeds {
            openings.push((dx, dy));
        }
    }
    openings.sort_by_key(|d| CARDINALS.iter().position(|c| c == d).unwrap_or(4));
    let suffix: String = if openings.is_empty() {
        "x".to_string()
    } else {
        openings
            .iter()
            .filter_map(|d| dir_suffix_cardinal(*d))
            .collect::<Vec<&str>>()
            .join("")
    };
    Some(format!("bridge_base_{team_s}_{suffix}"))
}

fn conveyor_junction_sprite_name(
    entity: &Entity,
    by_pos: &std::collections::HashMap<(i32, i32), Vec<&Entity>>,
) -> Option<String> {
    let (team_s, base, out_dir) = match &entity.kind {
        EntityKind::Conveyor { dir, .. } => {
            let team = match entity.team {
                proto::Team::A => "gold",
                proto::Team::B => "silver",
            };
            (team, "conveyor", *dir)
        }
        EntityKind::ArmouredConveyor { dir, .. } => {
            let team = match entity.team {
                proto::Team::A => "gold",
                proto::Team::B => "silver",
            };
            (team, "armoured_conveyor", *dir)
        }
        _ => return None,
    };
    let out = dir_unit(out_dir)?;
    let out_s = dir_suffix_cardinal(out)?;

    let pos = entity.pos;
    let mut inputs: Vec<(i32, i32)> = Vec::new();
    for (dx, dy) in CARDINALS {
        if (dx, dy) == out {
            continue;
        }
        let n = (pos.0 + dx, pos.1 + dy);
        let feeds = by_pos.get(&n).is_some_and(|list| {
            list.iter()
                .any(|e| e.team == entity.team && conveyor_feeds_into(e, pos))
        });
        if feeds {
            inputs.push((dx, dy));
        }
    }
    // Sort in canonical N,E,S,W order (already the iteration order of CARDINALS)
    inputs.sort_by_key(|d| CARDINALS.iter().position(|c| c == d).unwrap_or(4));
    let in_s: String = if inputs.is_empty() {
        "x".to_string()
    } else {
        inputs
            .iter()
            .filter_map(|d| dir_suffix_cardinal(*d))
            .collect::<Vec<&str>>()
            .join("")
    };
    Some(format!("{base}_{team_s}_{out_s}_{in_s}"))
}
