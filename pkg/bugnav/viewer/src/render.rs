use cambc_common::tile::{tile_center, tile_rect};
use eframe::egui;
use egui::{Color32, Painter, Pos2, Stroke, StrokeKind};

use crate::pathfinder::Snapshot;

const VISITED_COLOR: Color32 = Color32::from_rgba_premultiplied(0x30, 0x30, 0x30, 0x60);
const FRONTIER_COLOR: Color32 = Color32::from_rgba_premultiplied(0x80, 0x80, 0x00, 0xa0);
const PATH_COLOR: Color32 = Color32::from_rgba_premultiplied(0x00, 0xc0, 0xff, 0xff);
const OPTIMAL_COLOR: Color32 = Color32::from_rgba_premultiplied(0x80, 0x80, 0x80, 0xa0);
const CURRENT_COLOR: Color32 = Color32::from_rgb(0x00, 0xe0, 0xff);
const START_COLOR: Color32 = Color32::from_rgb(0x30, 0xe0, 0x30);
const GOAL_COLOR: Color32 = Color32::from_rgb(0xe0, 0x30, 0x30);

pub struct Ctx {
    pub ts: f32,
    pub zoom: f32,
    pub origin: Pos2,
}

pub fn draw_snapshot(
    painter: &Painter,
    ctx: &Ctx,
    snap: Option<&Snapshot>,
    optimal: Option<&[(i32, i32)]>,
    start: Option<(i32, i32)>,
    goal: Option<(i32, i32)>,
) {
    // Draw optimal path underneath so the algorithm's path overlays it.
    if let Some(opt) = optimal
        && opt.len() >= 2
    {
        let pts: Vec<Pos2> = opt
            .iter()
            .map(|&(x, y)| tile_center(x, y, ctx.ts, ctx.origin, ctx.zoom))
            .collect();
        painter.add(egui::Shape::line(
            pts,
            Stroke::new(1.5 * ctx.zoom.clamp(0.5, 2.0), OPTIMAL_COLOR),
        ));
    }

    if let Some(s) = snap {
        for &(x, y) in &s.visited {
            let r = tile_rect(x, y, ctx.ts, ctx.origin, ctx.zoom);
            painter.rect_filled(r, 0.0, VISITED_COLOR);
        }
        for &(x, y) in &s.frontier {
            let r = tile_rect(x, y, ctx.ts, ctx.origin, ctx.zoom);
            painter.rect_filled(r, 0.0, FRONTIER_COLOR);
        }
        if s.path.len() >= 2 {
            let pts: Vec<Pos2> = s
                .path
                .iter()
                .map(|&(x, y)| tile_center(x, y, ctx.ts, ctx.origin, ctx.zoom))
                .collect();
            painter.add(egui::Shape::line(
                pts,
                Stroke::new(2.0 * ctx.zoom.clamp(0.5, 2.0), PATH_COLOR),
            ));
        }
    }
    if let Some((sx, sy)) = start {
        draw_marker(painter, ctx, sx, sy, START_COLOR);
    }
    if let Some((gx, gy)) = goal {
        draw_marker(painter, ctx, gx, gy, GOAL_COLOR);
    }
    if let Some(s) = snap {
        let c = tile_center(s.current.0, s.current.1, ctx.ts, ctx.origin, ctx.zoom);
        painter.circle_filled(c, ctx.ts * ctx.zoom * 0.25, CURRENT_COLOR);
        painter.circle_stroke(
            c,
            ctx.ts * ctx.zoom * 0.25,
            Stroke::new(1.5 * ctx.zoom.clamp(0.5, 2.0), Color32::BLACK),
        );
    }
}

fn draw_marker(painter: &Painter, ctx: &Ctx, x: i32, y: i32, color: Color32) {
    let r = tile_rect(x, y, ctx.ts, ctx.origin, ctx.zoom);
    painter.rect_stroke(
        r.shrink(2.0 * ctx.zoom.clamp(0.5, 1.0)),
        0.0,
        Stroke::new(2.5 * ctx.zoom.clamp(0.5, 2.0), color),
        StrokeKind::Middle,
    );
}
