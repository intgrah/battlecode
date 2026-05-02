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

/// Minimum zoom level shared across map views. Reducing further makes
/// the map a smudge in the corner.
pub const MIN_ZOOM: f32 = 0.5;

/// Clamp `pan` so the map (sized `map_w × map_h` tiles at `zoom`) keeps
/// at least `min_visible_px` of overlap with `rect` on each axis.
/// Prevents the user from flinging the map entirely offscreen.
#[must_use]
pub fn clamp_pan(
    pan: Vec2,
    rect: Rect,
    map_w: i32,
    map_h: i32,
    ts: f32,
    zoom: f32,
    min_visible_px: f32,
) -> Vec2 {
    let map_px_w = map_w as f32 * ts * zoom;
    let map_px_h = map_h as f32 * ts * zoom;
    // pan.x is the offset of the map's left edge from rect.left().
    // Map covers screen-X range [pan.x, pan.x + map_px_w]; intersect
    // with [0, rect.width()] must leave at least `min_visible_px` on
    // each axis.
    let max_pan_x = rect.width() - min_visible_px;
    let min_pan_x = min_visible_px - map_px_w;
    let max_pan_y = rect.height() - min_visible_px;
    let min_pan_y = min_visible_px - map_px_h;
    Vec2::new(
        pan.x
            .clamp(min_pan_x.min(max_pan_x), max_pan_x.max(min_pan_x)),
        pan.y
            .clamp(min_pan_y.min(max_pan_y), max_pan_y.max(min_pan_y)),
    )
}
