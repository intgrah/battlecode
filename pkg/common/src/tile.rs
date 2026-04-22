use eframe::egui;
use egui::{Pos2, Rect, Vec2};

#[must_use]
pub fn tile_rect(x: i32, y: i32, ts: f32, origin: Pos2, zoom: f32) -> Rect {
    let px = (x as f32).mul_add(ts * zoom, origin.x);
    let py = (y as f32).mul_add(ts * zoom, origin.y);
    Rect::from_min_size(Pos2::new(px, py), Vec2::splat(ts * zoom))
}

#[must_use]
pub fn tile_rect_f32(x: f32, y: f32, ts: f32, origin: Pos2, zoom: f32) -> Rect {
    let px = x.mul_add(ts * zoom, origin.x);
    let py = y.mul_add(ts * zoom, origin.y);
    Rect::from_min_size(Pos2::new(px, py), Vec2::splat(ts * zoom))
}

#[must_use]
pub fn tile_center(x: i32, y: i32, ts: f32, origin: Pos2, zoom: f32) -> Pos2 {
    Pos2::new(
        (x as f32 + 0.5).mul_add(ts * zoom, origin.x),
        (y as f32 + 0.5).mul_add(ts * zoom, origin.y),
    )
}

#[must_use]
pub const fn premul(c: u8) -> u8 {
    ((c as u16) * 0xc0 / 0xff) as u8
}
