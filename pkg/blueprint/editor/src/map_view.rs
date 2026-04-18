use std::collections::HashMap;

use eframe::egui;
use egui::{Color32, Mesh, Pos2, Rect, Shape, Stroke, StrokeKind, Vec2};

use crate::app::App;
use crate::blueprint::{BlueprintEntry, Direction, Entity};
use crate::map::Tile;
use crate::symmetry::mirror_entry;

const BG_COLOR: Color32 = Color32::from_rgb(0x1d, 0x15, 0x0f);
const TILE_COLOR: Color32 = Color32::from_rgb(0x2a, 0x20, 0x18);
const CURSOR_COLOR: Color32 = Color32::from_rgba_premultiplied(0x80, 0x80, 0x00, 0x80);
const GRID_COLOR: Color32 = Color32::from_rgba_premultiplied(0x20, 0x20, 0x28, 0x80);
const UNROUTED_COLOR: Color32 = Color32::from_rgb(0xdc, 0x3c, 0x3c);
const CORE_A_COLOR: Color32 = Color32::from_rgb(0x78, 0xc8, 0x78);
const CORE_B_COLOR: Color32 = Color32::from_rgb(0xd2, 0x78, 0x78);
const BRIDGE_LINE: Color32 = Color32::from_rgba_premultiplied(0xd2, 0xaa, 0x5a, 0xdc);

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

const fn dir_suffix(d: Direction) -> &'static str {
    match d {
        Direction::North => "n",
        Direction::NorthEast => "ne",
        Direction::East => "e",
        Direction::SouthEast => "se",
        Direction::South => "s",
        Direction::SouthWest => "sw",
        Direction::West => "w",
        Direction::NorthWest => "nw",
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

const CARDINAL_DELTAS: [(i32, i32); 4] = [(0, -1), (1, 0), (0, 1), (-1, 0)];

fn cardinal_from_dir(d: Direction) -> Option<(i32, i32)> {
    match d {
        Direction::North => Some((0, -1)),
        Direction::East => Some((1, 0)),
        Direction::South => Some((0, 1)),
        Direction::West => Some((-1, 0)),
        _ => None,
    }
}

const fn cardinal_suffix_delta(d: (i32, i32)) -> Option<&'static str> {
    match d {
        (0, -1) => Some("n"),
        (1, 0) => Some("e"),
        (0, 1) => Some("s"),
        (-1, 0) => Some("w"),
        _ => None,
    }
}

fn conveyor_feeds_into(neighbour: &BlueprintEntry, target: (i32, i32)) -> bool {
    match neighbour.kind {
        Entity::Conveyor | Entity::ArmouredConveyor => {
            let Some(d) = neighbour.direction else { return false };
            let Some((dx, dy)) = cardinal_from_dir(d) else { return false };
            (neighbour.pos.0 + dx, neighbour.pos.1 + dy) == target
        }
        Entity::Splitter => {
            let Some(d) = neighbour.direction else { return false };
            let Some((dx, dy)) = cardinal_from_dir(d) else { return false };
            let back = (-dx, -dy);
            let delta = (target.0 - neighbour.pos.0, target.1 - neighbour.pos.1);
            CARDINAL_DELTAS.contains(&delta) && delta != back
        }
        Entity::Bridge => neighbour.bridge_target == Some(target),
        Entity::Harvester | Entity::Foundry => true,
        _ => false,
    }
}

fn conveyor_junction_sprite(
    entry: &BlueprintEntry,
    entries: &HashMap<(i32, i32), BlueprintEntry>,
    team_a: bool,
) -> Option<String> {
    let team = if team_a { "gold" } else { "silver" };
    let base = match entry.kind {
        Entity::Conveyor => "conveyor",
        Entity::ArmouredConveyor => "armoured_conveyor",
        _ => return None,
    };
    let out_dir = entry.direction?;
    let out = cardinal_from_dir(out_dir)?;
    let out_s = cardinal_suffix_delta(out)?;

    let mut inputs: Vec<(i32, i32)> = Vec::new();
    for (dx, dy) in CARDINAL_DELTAS {
        if (dx, dy) == out {
            continue;
        }
        let n = (entry.pos.0 + dx, entry.pos.1 + dy);
        if let Some(ne) = entries.get(&n) {
            if conveyor_feeds_into(ne, entry.pos) {
                inputs.push((dx, dy));
            }
        }
    }
    inputs.sort_by_key(|d| CARDINAL_DELTAS.iter().position(|c| c == d).unwrap_or(4));
    let in_s: String = if inputs.is_empty() {
        "x".into()
    } else {
        inputs
            .iter()
            .filter_map(|d| cardinal_suffix_delta(*d))
            .collect::<Vec<_>>()
            .join("")
    };
    Some(format!("{base}_{team}_{out_s}_{in_s}"))
}

fn sprite_name(e: &BlueprintEntry, team_a: bool) -> String {
    let team = if team_a { "gold" } else { "silver" };
    let d = e.direction;
    match e.kind {
        Entity::Harvester => format!("harvester_{team}"),
        Entity::Foundry => format!("foundry_{team}"),
        Entity::Launcher => format!("launcher_{team}"),
        Entity::Road => format!("road_{team}"),
        Entity::Barrier => format!("barrier_{team}"),
        Entity::Bridge => format!("bridge_stand_{team}"),
        Entity::Splitter => format!("splitter_{}_{team}", cardinal_suffix(d.unwrap_or(Direction::North))),
        Entity::Conveyor => {
            format!("conveyor_{team}_{}", cardinal_suffix(d.unwrap_or(Direction::East)))
        }
        Entity::ArmouredConveyor => format!(
            "armoured_conveyor_{team}_{}",
            cardinal_suffix(d.unwrap_or(Direction::East))
        ),
        Entity::Gunner => format!("gunner_{}_{team}", dir_suffix(d.unwrap_or(Direction::North))),
        Entity::Sentinel => format!("sentinel_{}_{team}", dir_suffix(d.unwrap_or(Direction::North))),
        Entity::Breach => format!("breach_{}_{team}", dir_suffix(d.unwrap_or(Direction::North))),
    }
}

fn draw_sprite(painter: &egui::Painter, app: &App, name: &str, rect: Rect, tint: Color32) {
    if let Some(tex_id) = app.atlas.get(name) {
        painter.image(
            tex_id,
            rect,
            Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)),
            tint,
        );
    }
}

fn build_static_map_shapes(app: &App, origin: Pos2) -> Vec<Shape> {
    let ts = app.atlas.tile_size;
    let zoom = app.zoom;
    let mut shapes = Vec::with_capacity((app.map.w * app.map.h) as usize);
    let uv = Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0));

    for gy in 0..app.map.h {
        for gx in 0..app.map.w {
            let r = tile_rect(gx, gy, ts, origin, zoom);
            match app.map.tile(gx, gy) {
                Tile::Wall => {
                    if let Some(tex_id) = app.atlas.get("natural_wall") {
                        let mut mesh = Mesh::with_texture(tex_id);
                        mesh.add_rect_with_uv(r, uv, Color32::from_rgb(0x30, 0x0c, 0x08));
                        shapes.push(Shape::mesh(mesh));
                    } else {
                        shapes.push(Shape::rect_filled(r, 0.0, Color32::from_rgb(0x30, 0x0c, 0x08)));
                    }
                }
                Tile::OreTitanium => {
                    shapes.push(Shape::rect_filled(r, 0.0, TILE_COLOR));
                    if let Some(tex_id) = app.atlas.get("titanium_ore") {
                        let mut mesh = Mesh::with_texture(tex_id);
                        mesh.add_rect_with_uv(r, uv, Color32::WHITE);
                        shapes.push(Shape::mesh(mesh));
                    }
                }
                Tile::OreAxionite => {
                    shapes.push(Shape::rect_filled(r, 0.0, TILE_COLOR));
                    if let Some(tex_id) = app.atlas.get("axionite_ore") {
                        let mut mesh = Mesh::with_texture(tex_id);
                        mesh.add_rect_with_uv(r, uv, Color32::WHITE);
                        shapes.push(Shape::mesh(mesh));
                    }
                }
                Tile::Empty => shapes.push(Shape::rect_filled(r, 0.0, TILE_COLOR)),
            }
        }
    }
    shapes
}

fn draw_bridge_line(painter: &egui::Painter, from: Pos2, to: Pos2, zoom: f32, color: Color32) {
    painter.line_segment([from, to], Stroke::new(3.0 * zoom.clamp(0.5, 2.0), color));
}

fn phase_alpha(app: &App, phase: i32, base: u8) -> Option<u8> {
    use crate::app::ViewMode;
    match app.view_mode {
        ViewMode::All => Some(base),
        ViewMode::UpTo => {
            if phase <= app.view_phase {
                Some(base)
            } else {
                None
            }
        }
        ViewMode::Only => {
            if phase == app.view_phase {
                Some(base)
            } else if phase < app.view_phase {
                Some(((base as u16 * 76) / 255) as u8)
            } else {
                None
            }
        }
    }
}

fn draw_entry(
    painter: &egui::Painter,
    app: &App,
    entry: &BlueprintEntry,
    rect: Rect,
    alpha: u8,
    team_a: bool,
    entries: Option<&HashMap<(i32, i32), BlueprintEntry>>,
) {
    let name = if app.show_conveyor_junctions
        && let Some(es) = entries
        && let Some(n) = conveyor_junction_sprite(entry, es, team_a)
    {
        n
    } else {
        sprite_name(entry, team_a)
    };
    let tint = Color32::from_rgba_premultiplied(alpha, alpha, alpha, alpha);
    draw_sprite(painter, app, &name, rect, tint);
}

pub fn render(ui: &mut egui::Ui, app: &mut App) {
    let (response, painter) =
        ui.allocate_painter(ui.available_size(), egui::Sense::click_and_drag());
    let rect = response.rect;
    let ts = app.atlas.tile_size;
    let zoom = app.zoom;
    let origin = Pos2::new(rect.left() + app.pan.x, rect.top() + app.pan.y);

    painter.rect_filled(rect, 0.0, BG_COLOR);

    let origin_vec = egui::Vec2::new(origin.x, origin.y);
    #[allow(clippy::float_cmp)]
    if origin_vec != app.cached_map_origin || zoom != app.cached_map_zoom {
        app.cached_map_shapes = build_static_map_shapes(app, origin);
        app.cached_map_origin = origin_vec;
        app.cached_map_zoom = zoom;
    }
    painter.extend(app.cached_map_shapes.clone());

    let sz = ts * zoom;
    for gy in 0..=app.map.h {
        let y = (gy as f32).mul_add(sz, origin.y);
        painter.line_segment(
            [Pos2::new(origin.x, y), Pos2::new((app.map.w as f32).mul_add(sz, origin.x), y)],
            Stroke::new(1.0, GRID_COLOR),
        );
    }
    for gx in 0..=app.map.w {
        let x = (gx as f32).mul_add(sz, origin.x);
        painter.line_segment(
            [Pos2::new(x, origin.y), Pos2::new(x, (app.map.h as f32).mul_add(sz, origin.y))],
            Stroke::new(1.0, GRID_COLOR),
        );
    }

    for (core, team_a, outline) in [
        (app.editor.core_a, true, CORE_A_COLOR),
        (app.editor.core_b, false, CORE_B_COLOR),
    ] {
        let cx = (core.0 - 1) as f32;
        let cy = (core.1 - 1) as f32;
        let r = Rect::from_min_size(
            Pos2::new(cx.mul_add(sz, origin.x), cy.mul_add(sz, origin.y)),
            Vec2::splat(sz * 3.0),
        );
        let name = if team_a { "base_gold" } else { "base_silver" };
        draw_sprite(&painter, app, name, r, Color32::WHITE);
        painter.rect_stroke(r, 0.0, Stroke::new(2.0, outline), StrokeKind::Outside);
    }

    let entries: HashMap<(i32, i32), BlueprintEntry> = app.editor.state.entries.clone();
    let bad = crate::sequencing::unrouted(&entries, app.editor.core_a);
    let mirrored: HashMap<(i32, i32), BlueprintEntry> = entries
        .values()
        .map(|e| {
            let me = mirror_entry(e, app.map.w, app.map.h, app.editor.sym);
            (me.pos, me)
        })
        .collect();

    let mut ordered: Vec<BlueprintEntry> = entries.values().copied().collect();
    ordered.sort_by_key(|e| (e.phase, e.pos.1, e.pos.0));
    for e in &ordered {
        let p = &e.pos;
        let Some(a) = phase_alpha(app, e.phase, 255) else {
            continue;
        };
        let r = tile_rect(e.pos.0, e.pos.1, ts, origin, zoom);
        draw_entry(&painter, app, e, r, a, true, Some(&entries));
        if e.kind == Entity::Bridge
            && let Some(tgt) = e.bridge_target
        {
            let from = tile_center(e.pos.0, e.pos.1, ts, origin, zoom);
            let to = tile_center(tgt.0, tgt.1, ts, origin, zoom);
            let c = BRIDGE_LINE;
            let aa = ((c.a() as u16 * a as u16) / 255) as u8;
            draw_bridge_line(
                &painter,
                from,
                to,
                zoom,
                Color32::from_rgba_premultiplied(c.r(), c.g(), c.b(), aa),
            );
        }
        if a == 255 && bad.contains(p) {
            painter.rect_stroke(r, 0.0, Stroke::new(2.0, UNROUTED_COLOR), StrokeKind::Inside);
        }

        let me = mirror_entry(e, app.map.w, app.map.h, app.editor.sym);
        if me.pos == e.pos {
            continue;
        }
        let Some(ma) = phase_alpha(app, me.phase, 140) else {
            continue;
        };
        let mr = tile_rect(me.pos.0, me.pos.1, ts, origin, zoom);
        draw_entry(&painter, app, &me, mr, ma, false, Some(&mirrored));
        if me.kind == Entity::Bridge
            && let Some(tgt) = me.bridge_target
        {
            let from = tile_center(me.pos.0, me.pos.1, ts, origin, zoom);
            let to = tile_center(tgt.0, tgt.1, ts, origin, zoom);
            draw_bridge_line(
                &painter,
                from,
                to,
                zoom,
                Color32::from_rgba_premultiplied(0xa0, 0x80, 0x40, ma.min(0x8c)),
            );
        }
    }

    if let Some(hover) = app.hover_tile
        && !entries.contains_key(&hover) && app.editor.bridge_source.is_none() {
            let tool = app.editor.tool;
            let direction = if tool.is_directional() {
                Some(
                    app.editor
                        .last_direction
                        .get(&tool)
                        .copied()
                        .unwrap_or(Direction::East),
                )
            } else {
                None
            };
            let ghost = BlueprintEntry {
                pos: hover,
                kind: tool,
                direction,
                bridge_target: None,
                phase: app.editor.current_phase,
            };
            let r = tile_rect(hover.0, hover.1, ts, origin, zoom);
            if tool != Entity::Bridge {
                let mut with_ghost = entries.clone();
                with_ghost.insert(hover, ghost);
                draw_entry(&painter, app, &ghost, r, 100, true, Some(&with_ghost));
            }
            painter.rect_stroke(r, 0.0, Stroke::new(2.0, CURSOR_COLOR), StrokeKind::Outside);
        }

    if let Some(src) = app.editor.bridge_source {
        let r = tile_rect(src.0, src.1, ts, origin, zoom);
        painter.rect_stroke(
            r,
            0.0,
            Stroke::new(3.0, Color32::from_rgb(255, 255, 80)),
            StrokeKind::Outside,
        );
    }

    if response.hovered() {
        if let Some(pos) = ui.input(|i| i.pointer.hover_pos()) {
            let gx = ((pos.x - origin.x) / (ts * zoom)).floor() as i32;
            let gy = ((pos.y - origin.y) / (ts * zoom)).floor() as i32;
            app.hover_tile = if gx >= 0 && gx < app.map.w && gy >= 0 && gy < app.map.h {
                Some((gx, gy))
            } else {
                None
            };
        }
    } else {
        app.hover_tile = None;
    }

    let shift = ui.input(|i| i.modifiers.shift);
    let space = ui.input(|i| i.key_down(egui::Key::Space));
    let tool = app.editor.tool;
    let is_chain_tool = matches!(tool, Entity::Conveyor | Entity::ArmouredConveyor);

    if response.dragged_by(egui::PointerButton::Primary) && (shift || space) {
        app.pan += response.drag_delta();
        ui.ctx().set_cursor_icon(egui::CursorIcon::Grabbing);
    } else if is_chain_tool && response.dragged_by(egui::PointerButton::Primary) {
        if let Some(h) = app.hover_tile {
            match app.drag_last_tile {
                None => app.drag_last_tile = Some(h),
                Some(prev) if prev != h => {
                    let mut cur = prev;
                    let mut steps = 0;
                    while cur != h && steps < 200 {
                        let (dx, dy) = (h.0 - cur.0, h.1 - cur.1);
                        let (sdx, sdy) = if dx.abs() >= dy.abs() {
                            (dx.signum(), 0)
                        } else {
                            (0, dy.signum())
                        };
                        if let Some(dir) = Direction::from_delta(sdx, sdy) {
                            app.editor
                                .place_conveyor_dir(&app.map, cur, tool, dir);
                        }
                        cur = (cur.0 + sdx, cur.1 + sdy);
                        steps += 1;
                    }
                    app.drag_last_tile = Some(h);
                }
                _ => {}
            }
        }
    } else if response.clicked_by(egui::PointerButton::Primary) {
        if let Some(h) = app.hover_tile {
            app.editor.place(&app.map, h, tool);
        }
    } else if response.clicked_by(egui::PointerButton::Secondary) {
        if let Some(h) = app.hover_tile {
            app.editor.rotate_at(h, 1);
        }
    } else if response.clicked_by(egui::PointerButton::Middle)
        && let Some(h) = app.hover_tile
    {
        app.editor.erase(h);
    }

    if response.drag_stopped_by(egui::PointerButton::Primary) {
        if let Some(last) = app.drag_last_tile {
            let dir = app
                .editor
                .last_direction
                .get(&tool)
                .copied()
                .unwrap_or(Direction::East);
            if is_chain_tool {
                app.editor.place_conveyor_dir(&app.map, last, tool, dir);
            }
        }
        app.drag_last_tile = None;
    }

    let raw_scroll = ui.input(|i| {
        let mut total = 0.0_f32;
        for ev in &i.raw.events {
            if let egui::Event::MouseWheel { delta, .. } = ev {
                total += delta.y;
            }
        }
        total
    });
    if raw_scroll != 0.0 && response.hovered() {
        let factor = (raw_scroll * 0.1).exp();
        if let Some(pointer) = ui.input(|i| i.pointer.hover_pos()) {
            let old_zoom = app.zoom;
            app.zoom = (app.zoom * factor).clamp(0.2, 6.0);
            let dz = app.zoom / old_zoom;
            app.pan.x =
                (pointer.x - app.pan.x - rect.left()).mul_add(-dz, pointer.x) - rect.left();
            app.pan.y =
                (pointer.y - app.pan.y - rect.top()).mul_add(-dz, pointer.y) - rect.top();
        }
    }
}
