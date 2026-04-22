use cambc_common::map::BG_COLOR;
use eframe::egui;
use egui::{Pos2, Sense};

use crate::app::App;
use crate::pathfinder::{StepStatus, registry};
use crate::render::{Ctx, draw_snapshot};

pub fn render_sidebar(ui: &mut egui::Ui, app: &mut App) {
    ui.heading("bugnav");
    ui.add_space(4.0);

    ui.label("Map");
    let prev_map = app.map_idx;
    egui::ComboBox::from_id_salt("map")
        .width(200.0)
        .selected_text(
            app.map_names
                .get(app.map_idx)
                .map_or("<none>", String::as_str),
        )
        .show_ui(ui, |ui| {
            for (i, name) in app.map_names.iter().enumerate() {
                ui.selectable_value(&mut app.map_idx, i, name);
            }
        });
    if app.map_idx != prev_map {
        app.load_selected_map();
    }

    ui.add_space(8.0);
    ui.label("Algorithm");
    let prev_algo = app.algo_idx;
    egui::ComboBox::from_id_salt("algo")
        .width(200.0)
        .selected_text(registry()[app.algo_idx].name)
        .show_ui(ui, |ui| {
            for (i, spec) in registry().iter().enumerate() {
                ui.selectable_value(&mut app.algo_idx, i, spec.name);
            }
        });
    if app.algo_idx != prev_algo {
        app.reset_finder();
    }

    ui.add_space(8.0);
    ui.separator();
    ui.add_space(4.0);

    ui.horizontal(|ui| {
        if ui.button("Step").clicked() {
            app.step_once();
        }
        let label = if app.playing { "Pause" } else { "Play" };
        if ui.button(label).clicked() {
            app.playing = !app.playing;
        }
        if ui.button("Reset").clicked() {
            app.reset_finder();
        }
    });

    ui.add_space(4.0);
    ui.horizontal(|ui| {
        ui.label("Steps/frame");
        ui.add(egui::Slider::new(&mut app.steps_per_frame, 1..=500).logarithmic(true));
    });

    ui.add_space(8.0);
    ui.separator();
    ui.add_space(4.0);

    if let Some(f) = &app.finder {
        ui.label(format!("Algo: {}", f.name()));
        ui.label(format!("Status: {:?}", app.last_status));
        ui.monospace(f.summary());
    } else {
        ui.label("click a passable tile to set START");
        ui.label("click another tile to set GOAL");
    }

    ui.add_space(8.0);
    ui.separator();
    ui.add_space(4.0);
    ui.label("Start/Goal");
    ui.monospace(format!(
        "start: {}\ngoal:  {}",
        app.start.map_or("-".into(), |(x, y)| format!("({x}, {y})")),
        app.goal.map_or("-".into(), |(x, y)| format!("({x}, {y})")),
    ));
    if ui.button("clear start+goal").clicked() {
        app.start = None;
        app.goal = None;
        app.finder = None;
        app.last_status = StepStatus::Running;
    }
}

#[allow(clippy::too_many_lines)]
pub fn render_map_panel(ui: &mut egui::Ui, app: &mut App) {
    egui::CentralPanel::default().show_inside(ui, |ui| {
        let (response, painter) = ui.allocate_painter(ui.available_size(), Sense::click_and_drag());
        let rect = response.rect;

        let ts = app.atlas.tile_size;
        let zoom = app.zoom;
        let origin = Pos2::new(rect.left() + app.pan.x, rect.top() + app.pan.y);
        painter.rect_filled(rect, 0.0, BG_COLOR);

        // Pan
        if response.dragged_by(egui::PointerButton::Primary) && !ui.input(|i| i.pointer.any_click())
        {
            app.pan += response.drag_delta();
        }
        // Zoom
        let scroll = ui.input(|i| i.smooth_scroll_delta.y);
        if scroll != 0.0 && response.hovered() {
            let factor = (scroll * 0.01).exp();
            if let Some(mouse) = ui.input(|i| i.pointer.hover_pos()) {
                let old_origin = origin;
                let new_zoom = (zoom * factor).clamp(0.1, 8.0);
                let local = mouse - old_origin;
                let scale = new_zoom / zoom;
                let new_origin = mouse - local * scale;
                app.pan = egui::Vec2::new(new_origin.x - rect.left(), new_origin.y - rect.top());
                app.zoom = new_zoom;
            }
        }

        // Recompute origin after possible pan/zoom
        let origin = Pos2::new(rect.left() + app.pan.x, rect.top() + app.pan.y);
        let zoom = app.zoom;

        // Static map background (cached)
        let origin_vec = egui::Vec2::new(origin.x, origin.y);
        #[allow(clippy::float_cmp)]
        if origin_vec != app.cached_map_origin || zoom != app.cached_map_zoom {
            app.cached_map_shapes = cambc_common::map::build_static_map_shapes(
                &app.atlas,
                app.grid.w,
                app.grid.h,
                zoom,
                origin,
                |x, y| app.grid.env_at(x, y),
            );
            app.cached_map_origin = origin_vec;
            app.cached_map_zoom = zoom;
        }
        painter.extend(app.cached_map_shapes.clone());

        // Click: set start, then goal
        if response.clicked() {
            if let Some(mouse) = response.interact_pointer_pos() {
                let gx = ((mouse.x - origin.x) / (ts * zoom)).floor() as i32;
                let gy = ((mouse.y - origin.y) / (ts * zoom)).floor() as i32;
                if app.grid.passable(gx, gy) {
                    if app.start.is_none() {
                        app.start = Some((gx, gy));
                    } else if app.goal.is_none() {
                        app.goal = Some((gx, gy));
                        app.reset_finder();
                    } else {
                        app.start = Some((gx, gy));
                        app.goal = None;
                        app.finder = None;
                        app.last_status = StepStatus::Running;
                    }
                }
            }
        }

        // Overlay: algorithm snapshot
        let ctx = Ctx { ts, zoom, origin };
        draw_snapshot(
            &painter,
            &ctx,
            app.finder.as_ref().map(|f| f.snapshot()),
            app.start,
            app.goal,
        );
    });
}
