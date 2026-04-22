use cambc_proto as proto;
use eframe::egui;
use egui::{Color32, Mesh, Pos2, Rect, Shape};

use crate::SpriteAtlas;
use crate::tile::tile_rect;

pub const BG_COLOR: Color32 = Color32::from_rgb(0x1d, 0x15, 0x0f);
pub const TILE_COLOR: Color32 = Color32::from_rgb(0x2a, 0x20, 0x18);
pub const WALL_COLOR: Color32 = Color32::from_rgb(0x30, 0x0c, 0x08);

#[must_use]
pub fn build_static_map_shapes(
    atlas: &SpriteAtlas,
    width: i32,
    height: i32,
    zoom: f32,
    origin: Pos2,
    tile_at: impl Fn(i32, i32) -> proto::Environment,
) -> Vec<Shape> {
    let ts = atlas.tile_size;
    let mut shapes = Vec::with_capacity((width * height) as usize);
    let uv = Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0));

    for gy in 0..height {
        for gx in 0..width {
            let r = tile_rect(gx, gy, ts, origin, zoom);
            match tile_at(gx, gy) {
                proto::Environment::EnvWall => {
                    if let Some(tex_id) = atlas.get("natural_wall") {
                        let mut mesh = Mesh::with_texture(tex_id);
                        mesh.add_rect_with_uv(r, uv, WALL_COLOR);
                        shapes.push(Shape::mesh(mesh));
                    } else {
                        shapes.push(Shape::rect_filled(r, 0.0, WALL_COLOR));
                    }
                }
                proto::Environment::EnvOreTitanium => {
                    shapes.push(Shape::rect_filled(r, 0.0, TILE_COLOR));
                    if let Some(tex_id) = atlas.get("titanium_ore") {
                        let mut mesh = Mesh::with_texture(tex_id);
                        mesh.add_rect_with_uv(r, uv, Color32::WHITE);
                        shapes.push(Shape::mesh(mesh));
                    }
                }
                proto::Environment::EnvOreAxionite => {
                    shapes.push(Shape::rect_filled(r, 0.0, TILE_COLOR));
                    if let Some(tex_id) = atlas.get("axionite_ore") {
                        let mut mesh = Mesh::with_texture(tex_id);
                        mesh.add_rect_with_uv(r, uv, Color32::WHITE);
                        shapes.push(Shape::mesh(mesh));
                    }
                }
                proto::Environment::EnvEmpty => {
                    shapes.push(Shape::rect_filled(r, 0.0, TILE_COLOR));
                }
            }
        }
    }
    shapes
}
