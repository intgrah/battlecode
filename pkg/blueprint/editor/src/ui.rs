use std::collections::HashMap;

use eframe::egui;

use crate::app::{App, ViewMode};
use crate::blueprint::{BlueprintEntry, Entity, ALL_ENTITIES};

pub fn sorted_entries(entries: &HashMap<(i32, i32), BlueprintEntry>) -> Vec<BlueprintEntry> {
    let mut v: Vec<BlueprintEntry> = entries.values().copied().collect();
    v.sort_by_key(|e| (e.phase, e.pos.1, e.pos.0));
    v
}

pub fn render_sidebar(ui: &mut egui::Ui, app: &mut App) {
    ui.heading(&app.editor.map_name);
    ui.label(format!("{}x{}  sym={}", app.map.w, app.map.h, app.editor.sym.as_str()));
    ui.separator();

    ui.label("tool");
    egui::Grid::new("tool_grid").num_columns(3).show(ui, |ui| {
        for (i, e) in ALL_ENTITIES.iter().enumerate() {
            let selected = app.editor.tool == *e;
            let btn = ui.selectable_label(selected, e.name());
            if btn.clicked() {
                app.editor.tool = *e;
                app.editor.bridge_source = None;
                app.editor.status = format!("tool = {}", e.name());
            }
            if (i + 1) % 3 == 0 {
                ui.end_row();
            }
        }
    });
    ui.separator();

    let entries: Vec<crate::blueprint::BlueprintEntry> =
        sorted_entries(&app.editor.state.entries);
    let ((lo_ti, lo_ax), (hi_ti, hi_ax)) =
        crate::cost::cost_range(&entries, app.editor.n_builders);
    let init_s = crate::cost::initial_scale(app.editor.n_builders);
    let end_s = crate::cost::final_scale(&entries, app.editor.n_builders);

    ui.label(format!("entries: {}", entries.len()));
    ui.horizontal(|ui| {
        ui.label(format!("builders: {}", app.editor.n_builders));
        if ui.small_button("-").clicked() && app.editor.n_builders > 0 {
            app.editor.n_builders -= 1;
        }
        if ui.small_button("+").clicked() {
            app.editor.n_builders += 1;
        }
    });
    ui.label(format!("scale: {init_s:.2}x → {end_s:.2}x"));
    ui.label(format!("Ti: {lo_ti}–{hi_ti}"));
    ui.label(format!("Ax: {lo_ax}–{hi_ax}"));
    ui.separator();

    ui.checkbox(
        &mut app.show_conveyor_junctions,
        "Experimental conveyor junctions",
    );
    ui.separator();

    let max_phase = app
        .editor
        .state
        .entries
        .values()
        .map(|e| e.phase)
        .max()
        .unwrap_or(0);
    ui.horizontal(|ui| {
        ui.label("place phase:");
        if ui.small_button("-").clicked() && app.editor.current_phase > 0 {
            app.editor.current_phase -= 1;
        }
        ui.label(format!("{}", app.editor.current_phase));
        if ui.small_button("+").clicked() {
            app.editor.current_phase += 1;
        }
    });
    ui.horizontal(|ui| {
        ui.label("view:");
        ui.selectable_value(&mut app.view_mode, ViewMode::All, "all");
        ui.selectable_value(&mut app.view_mode, ViewMode::UpTo, "≤");
        ui.selectable_value(&mut app.view_mode, ViewMode::Only, "only");
    });
    if app.view_mode != ViewMode::All {
        ui.horizontal(|ui| {
            ui.label("view phase:");
            if ui.small_button("-").clicked() && app.view_phase > 0 {
                app.view_phase -= 1;
            }
            ui.label(format!("{} / {}", app.view_phase, max_phase));
            if ui.small_button("+").clicked() {
                app.view_phase += 1;
            }
        });
    }
    ui.separator();

    ui.label("keys");
    ui.small("LMB place | RMB rotate | MMB erase");
    ui.small("shift/space+drag pan | wheel zoom");
    ui.small("ctrl-s save | ctrl-z undo | ctrl-shift-z redo");
    ui.small("+/- builders | q quit");
    ui.separator();

    let dirty = if app.editor.state.dirty { "*" } else { "" };
    ui.label(format!("{dirty}{}", app.editor.status));
}

pub fn handle_keys(ctx: &egui::Context, app: &mut App) -> bool {
    let mut quit = false;
    let ctrl = ctx.input(|i| i.modifiers.ctrl);
    let shift = ctx.input(|i| i.modifiers.shift);

    ctx.input(|i| {
        for ev in &i.events {
            if let egui::Event::Key {
                key, pressed: true, ..
            } = ev
            {
                match key {
                    egui::Key::S if ctrl => app.editor.save(),
                    egui::Key::Z if ctrl && shift => app.editor.state.redo(),
                    egui::Key::Z if ctrl => app.editor.state.undo(),
                    egui::Key::Q => quit = true,
                    egui::Key::Minus => {
                        if app.editor.n_builders > 0 {
                            app.editor.n_builders -= 1;
                        }
                    }
                    egui::Key::Plus | egui::Key::Equals => {
                        app.editor.n_builders += 1;
                    }
                    _ => {
                        if let Some(e) = key_to_entity(*key) {
                            app.editor.tool = e;
                            app.editor.bridge_source = None;
                            app.editor.status = format!("tool = {}", e.name());
                        }
                    }
                }
            }
        }
    });

    quit
}

const fn key_to_entity(k: egui::Key) -> Option<Entity> {
    Some(match k {
        egui::Key::C => Entity::Conveyor,
        egui::Key::A => Entity::ArmouredConveyor,
        egui::Key::S => Entity::Splitter,
        egui::Key::B => Entity::Bridge,
        egui::Key::H => Entity::Harvester,
        egui::Key::F => Entity::Foundry,
        egui::Key::G => Entity::Gunner,
        egui::Key::N => Entity::Sentinel,
        egui::Key::K => Entity::Breach,
        egui::Key::L => Entity::Launcher,
        egui::Key::W => Entity::Barrier,
        egui::Key::R => Entity::Road,
        _ => return None,
    })
}
