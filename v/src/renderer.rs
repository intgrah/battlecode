use image::{Rgba, RgbaImage, imageops};

use crate::proto;
use crate::sprites::SpriteAtlas;
use crate::state::{Entity, EntityKind, GameState, TurnState};

const BG_COLOR: Rgba<u8> = Rgba([0x1d, 0x15, 0x0f, 0xff]);
const CURSOR_COLOR: Rgba<u8> = Rgba([0xff, 0xff, 0x00, 0x80]);
const SELECTED_COLOR: Rgba<u8> = Rgba([0x00, 0xff, 0x00, 0x80]);

pub fn render_map(
    game: &GameState,
    turn_state: &TurnState,
    atlas: &SpriteAtlas,
    cursor: (i32, i32),
    selected_entity: Option<i32>,
) -> RgbaImage {
    let ts = atlas.tile_size;
    let w = game.width as u32;
    let h = game.height as u32;
    let mut img = RgbaImage::from_pixel(w * ts, h * ts, BG_COLOR);

    for gy in 0..game.height {
        for gx in 0..game.width {
            let px = gx as u32 * ts;
            let py = gy as u32 * ts;

            let env = game
                .env
                .get(gy as usize)
                .and_then(|row| row.get(gx as usize))
                .copied()
                .unwrap_or(proto::Environment::EnvEmpty);

            match env {
                proto::Environment::EnvWall => {
                    if let Some(wall_sprite) = atlas.get("natural_wall") {
                        imageops::overlay(&mut img, wall_sprite, i64::from(px), i64::from(py));
                        tint_rect(&mut img, px, py, ts, ts, Rgba([0x30, 0x0c, 0x08, 0xff]));
                        fill_rect_alpha(&mut img, px, py, ts, ts, Rgba([0x44, 0x44, 0x44, 0x4d]));
                    } else {
                        fill_rect(&mut img, px, py, ts, ts, Rgba([0x30, 0x0c, 0x08, 0xff]));
                    }
                }
                proto::Environment::EnvOreTitanium => {
                    if let Some(sprite) = atlas.get("titanium_ore") {
                        imageops::overlay(&mut img, sprite, i64::from(px), i64::from(py));
                    }
                }
                proto::Environment::EnvOreAxionite => {
                    if let Some(sprite) = atlas.get("axionite_ore") {
                        imageops::overlay(&mut img, sprite, i64::from(px), i64::from(py));
                    }
                }
                proto::Environment::EnvEmpty => {}
            }
        }
    }

    let mut entities: Vec<&Entity> = turn_state.entities.values().collect();
    entities.sort_by_key(|e| entity_z_order(&e.kind));

    for e in entities {
        let sprite_name = entity_sprite_name(e);

        if matches!(e.kind, EntityKind::Core { .. }) {
            let road_name = match e.team {
                proto::Team::A => "road_gold",
                proto::Team::B => "road_silver",
            };
            if let Some(road_sprite) = atlas.get(road_name) {
                for dy in -1..=1_i32 {
                    for dx in -1..=1_i32 {
                        let rx = (e.pos.0 + dx).max(0) as u32 * ts;
                        let ry = (e.pos.1 + dy).max(0) as u32 * ts;
                        imageops::overlay(&mut img, road_sprite, i64::from(rx), i64::from(ry));
                    }
                }
            }
        }

        let (px, py) = if matches!(e.kind, EntityKind::Core { .. }) {
            (
                (e.pos.0 - 1).max(0) as u32 * ts,
                (e.pos.1 - 1).max(0) as u32 * ts,
            )
        } else {
            (e.pos.0 as u32 * ts, e.pos.1 as u32 * ts)
        };

        if let Some(sprite) = atlas.get(&sprite_name) {
            imageops::overlay(&mut img, sprite, i64::from(px), i64::from(py));
        }

        if !matches!(
            e.kind,
            EntityKind::Core { .. } | EntityKind::CoreEdge { .. }
        ) && let Some(res_name) = entity_resource_sprite(e)
            && let Some(res_sprite) = atlas.get(res_name)
        {
            let rpx = e.pos.0 as u32 * ts;
            let rpy = e.pos.1 as u32 * ts;
            imageops::overlay(&mut img, res_sprite, i64::from(rpx), i64::from(rpy));
        }
    }

    for e in turn_state.entities.values() {
        if let EntityKind::Bridge { target, .. } = &e.kind {
            let beam_name = match e.team {
                proto::Team::A => "bridge_gold",
                proto::Team::B => "bridge_silver",
            };
            if let Some(beam) = atlas.get(beam_name) {
                let from = (
                    f64::from(e.pos.0 as u32 * ts + ts / 2),
                    f64::from(e.pos.1 as u32 * ts + ts / 2),
                );
                let to = (
                    f64::from(target.0 as u32 * ts + ts / 2),
                    f64::from(target.1 as u32 * ts + ts / 2),
                );
                overlay_beam(&mut img, beam, from, to, f64::from(ts) * 0.6);
            }
        }
    }

    if let Some(sel_id) = selected_entity
        && let Some(e) = turn_state.entities.get(&sel_id)
    {
        let px = e.pos.0 as u32 * ts;
        let py = e.pos.1 as u32 * ts;
        draw_border(&mut img, px, py, ts, ts, SELECTED_COLOR, 2);

        if let EntityKind::Bridge { target, .. } = &e.kind {
            let tx = target.0 as u32 * ts + ts / 2;
            let ty = target.1 as u32 * ts + ts / 2;
            let sx = px + ts / 2;
            let sy = py + ts / 2;
            draw_line(&mut img, sx, sy, tx, ty, Rgba([0x00, 0xff, 0x00, 0xc0]));
        }
    }

    {
        let cx = cursor.0 as u32 * ts;
        let cy = cursor.1 as u32 * ts;
        draw_border(&mut img, cx, cy, ts, ts, CURSOR_COLOR, 2);
    }

    img
}

fn entity_sprite_name(e: &Entity) -> String {
    let team = match e.team {
        proto::Team::A => "gold",
        proto::Team::B => "silver",
    };
    match &e.kind {
        EntityKind::BuilderBot { .. } => format!("builderbot_front_{team}"),
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => format!("base_{team}"),
        EntityKind::Conveyor { .. } => format!("conveyor_{team}"),
        EntityKind::ArmouredConveyor { .. } => format!("armoured_conveyor_{team}"),
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

fn tint_rect(img: &mut RgbaImage, x: u32, y: u32, w: u32, h: u32, tint: Rgba<u8>) {
    for py in y..y + h {
        for px in x..x + w {
            if px < img.width() && py < img.height() {
                let p = img.get_pixel(px, py);
                img.put_pixel(
                    px,
                    py,
                    Rgba([
                        (u16::from(p.0[0]) * u16::from(tint.0[0]) / 255) as u8,
                        (u16::from(p.0[1]) * u16::from(tint.0[1]) / 255) as u8,
                        (u16::from(p.0[2]) * u16::from(tint.0[2]) / 255) as u8,
                        p.0[3],
                    ]),
                );
            }
        }
    }
}

fn fill_rect(img: &mut RgbaImage, x: u32, y: u32, w: u32, h: u32, color: Rgba<u8>) {
    for py in y..y + h {
        for px in x..x + w {
            if px < img.width() && py < img.height() {
                img.put_pixel(px, py, color);
            }
        }
    }
}

fn fill_rect_alpha(img: &mut RgbaImage, x: u32, y: u32, w: u32, h: u32, color: Rgba<u8>) {
    for py in y..y + h {
        for px in x..x + w {
            if px < img.width() && py < img.height() {
                let bg = img.get_pixel(px, py);
                let a = f32::from(color.0[3]) / 255.0;
                let blended = Rgba([
                    blend_channel(bg.0[0], color.0[0], a),
                    blend_channel(bg.0[1], color.0[1], a),
                    blend_channel(bg.0[2], color.0[2], a),
                    255,
                ]);
                img.put_pixel(px, py, blended);
            }
        }
    }
}

fn blend_channel(bg: u8, fg: u8, a: f32) -> u8 {
    f32::from(bg).mul_add(1.0 - a, f32::from(fg) * a) as u8
}

#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    clippy::cast_precision_loss
)]
fn overlay_beam(
    img: &mut RgbaImage,
    beam: &RgbaImage,
    from: (f64, f64),
    to: (f64, f64),
    width: f64,
) {
    let dx = to.0 - from.0;
    let dy = to.1 - from.1;
    let length = dx.hypot(dy);
    if length < 0.5 {
        return;
    }

    let ux = dx / length;
    let uy = dy / length;
    let vx = -uy;
    let vy = ux;

    let beam_w = f64::from(beam.width());
    let beam_h = f64::from(beam.height());
    let half_w = width / 2.0;

    let corners = [
        (vx.mul_add(-half_w, from.0), vy.mul_add(-half_w, from.1)),
        (vx.mul_add(half_w, from.0), vy.mul_add(half_w, from.1)),
        (vx.mul_add(-half_w, to.0), vy.mul_add(-half_w, to.1)),
        (vx.mul_add(half_w, to.0), vy.mul_add(half_w, to.1)),
    ];
    let min_x = corners.iter().map(|c| c.0).fold(f64::MAX, f64::min).floor() as i32;
    let max_x = corners.iter().map(|c| c.0).fold(f64::MIN, f64::max).ceil() as i32;
    let min_y = corners.iter().map(|c| c.1).fold(f64::MAX, f64::min).floor() as i32;
    let max_y = corners.iter().map(|c| c.1).fold(f64::MIN, f64::max).ceil() as i32;

    let img_w = img.width() as i32;
    let img_h = img.height() as i32;

    for py in min_y.max(0)..max_y.min(img_h) {
        for px in min_x.max(0)..max_x.min(img_w) {
            let rel_x = f64::from(px) - from.0;
            let rel_y = f64::from(py) - from.1;

            let along = rel_x.mul_add(ux, rel_y * uy);
            let across = rel_x.mul_add(vx, rel_y * vy);

            let src_y = along / length * beam_h;
            let src_x = (across / width + 0.5) * beam_w;

            if src_x >= 0.0 && src_x < beam_w && src_y >= 0.0 && src_y < beam_h {
                let sx = (src_x as u32).min(beam.width() - 1);
                let sy = (src_y as u32).min(beam.height() - 1);
                let src_pixel = beam.get_pixel(sx, sy);
                if src_pixel.0[3] > 0 {
                    let bg = img.get_pixel(px as u32, py as u32);
                    let a = f32::from(src_pixel.0[3]) / 255.0;
                    let blended = Rgba([
                        blend_channel(bg.0[0], src_pixel.0[0], a),
                        blend_channel(bg.0[1], src_pixel.0[1], a),
                        blend_channel(bg.0[2], src_pixel.0[2], a),
                        255,
                    ]);
                    img.put_pixel(px as u32, py as u32, blended);
                }
            }
        }
    }
}

fn draw_border(
    img: &mut RgbaImage,
    x: u32,
    y: u32,
    w: u32,
    h: u32,
    color: Rgba<u8>,
    thickness: u32,
) {
    for t in 0..thickness {
        for px in x..x + w {
            if px < img.width() {
                if y + t < img.height() {
                    img.put_pixel(px, y + t, color);
                }
                if y + h - 1 - t < img.height() {
                    img.put_pixel(px, y + h - 1 - t, color);
                }
            }
        }
        for py in y..y + h {
            if py < img.height() {
                if x + t < img.width() {
                    img.put_pixel(x + t, py, color);
                }
                if x + w - 1 - t < img.width() {
                    img.put_pixel(x + w - 1 - t, py, color);
                }
            }
        }
    }
}

fn draw_line(img: &mut RgbaImage, x0: u32, y0: u32, x1: u32, y1: u32, color: Rgba<u8>) {
    let dx = (i64::from(x1) - i64::from(x0)).abs();
    let dy = (i64::from(y1) - i64::from(y0)).abs();
    let sx: i64 = if x0 < x1 { 1 } else { -1 };
    let sy: i64 = if y0 < y1 { 1 } else { -1 };
    let mut err = dx - dy;
    let mut cx = i64::from(x0);
    let mut cy = i64::from(y0);

    loop {
        if cx >= 0 && cy >= 0 && (cx as u32) < img.width() && (cy as u32) < img.height() {
            img.put_pixel(cx as u32, cy as u32, color);
        }
        if cx == i64::from(x1) && cy == i64::from(y1) {
            break;
        }
        let e2 = 2 * err;
        if e2 > -dy {
            err -= dy;
            cx += sx;
        }
        if e2 < dx {
            err += dx;
            cy += sy;
        }
    }
}
