use std::collections::{BTreeMap, HashMap};

use eframe::egui;
use titan_core::ResponseExt;

use crate::app::{App, Mode};
use crate::blueprint::{ALL_ENTITIES, BlueprintEntry, Entity};

pub fn sorted_entries(entries: &HashMap<(i32, i32), BlueprintEntry>) -> Vec<BlueprintEntry> {
    let mut v: Vec<BlueprintEntry> = entries.values().copied().collect();
    v.sort_by_key(|e| (e.phase, e.pos.1, e.pos.0));
    v
}

fn set_mode(app: &mut App, m: Mode) {
    app.mode = m;
    app.editor.bridge_source = None;
    app.editor.status = match m {
        Mode::View => "view".into(),
        Mode::Place(e) => format!("place {}", e.name()),
        Mode::PhaseView => format!("phase view @ {}", app.editor.current_phase + 1),
    };
}

pub fn render_sidebar(ui: &mut egui::Ui, app: &mut App) {
    ui.heading(&app.editor.map_name);
    ui.label(format!(
        "{}x{}  sym={}",
        app.map.w,
        app.map.h,
        app.editor.sym.as_str()
    ));
    ui.separator();

    egui::Frame::group(ui.style()).show(ui, |ui| {
        titan_core::style::section_title(ui, "mode");
        ui.horizontal(|ui| {
            if ui
                .selectable_label(matches!(app.mode, Mode::View), "view")
                .clickable()
                .clicked()
            {
                set_mode(app, Mode::View);
            }
            if ui
                .selectable_label(matches!(app.mode, Mode::PhaseView), "phase view")
                .clickable()
                .clicked()
            {
                set_mode(app, Mode::PhaseView);
            }
        });

        ui.add_space(4.0);
        titan_core::style::section_title(ui, "place");
        egui::Grid::new("place_grid").num_columns(3).show(ui, |ui| {
            for (i, e) in ALL_ENTITIES.iter().enumerate() {
                let selected = matches!(app.mode, Mode::Place(k) if k == *e);
                if ui
                    .selectable_label(selected, e.name())
                    .clickable()
                    .clicked()
                {
                    set_mode(app, Mode::Place(*e));
                }
                if (i + 1) % 3 == 0 {
                    ui.end_row();
                }
            }
        });
    });
    ui.separator();

    let entries: Vec<BlueprintEntry> = sorted_entries(&app.editor.state.entries);
    let ((lo_ti, lo_ax), (hi_ti, hi_ax)) = crate::cost::cost_range(&entries, app.editor.n_builders);
    let init_s = crate::cost::initial_scale(app.editor.n_builders);
    let end_s = crate::cost::final_scale(&entries, app.editor.n_builders);

    ui.label(format!("entries: {}", entries.len()));
    ui.horizontal(|ui| {
        ui.label(format!("builders: {}", app.editor.n_builders));
        if ui.small_button("-").clickable().clicked() && app.editor.n_builders > 0 {
            app.editor.n_builders -= 1;
        }
        if ui.small_button("+").clickable().clicked() {
            app.editor.n_builders += 1;
        }
    });
    ui.label(format!("scale: {init_s:.2}x → {end_s:.2}x"));
    ui.label(format!("Ti: {lo_ti}–{hi_ti}"));
    ui.label(format!("Ax: {lo_ax}–{hi_ax}"));
    ui.separator();

    ui.checkbox(&mut app.show_connected_textures, "Connected textures")
        .clickable();
    ui.separator();

    // Current phase stepper (used by Place to tag new entries and by
    // PhaseView as the "active" phase).
    ui.horizontal(|ui| {
        ui.label("current phase:");
        if ui.small_button("-").clickable().clicked() && app.editor.current_phase > 0 {
            app.editor.current_phase -= 1;
        }
        ui.label(format!("{}", app.editor.current_phase + 1));
        if ui.small_button("+").clickable().clicked() {
            app.editor.current_phase += 1;
        }
    });

    // Phase list with insert-after / delete.
    let mut counts: BTreeMap<i32, usize> = BTreeMap::new();
    for e in app.editor.state.entries.values() {
        *counts.entry(e.phase).or_default() += 1;
    }
    let mut to_insert_after: Option<i32> = None;
    let mut to_delete: Option<i32> = None;
    let mut to_select: Option<i32> = None;
    ui.label("phases");
    for (&p, &n) in &counts {
        let is_current = p == app.editor.current_phase;
        ui.horizontal(|ui| {
            if ui
                .selectable_label(is_current, format!("{}: {n}", p + 1))
                .clickable()
                .clicked()
            {
                to_select = Some(p);
            }
            if ui.small_button("+after").clickable().clicked() {
                to_insert_after = Some(p);
            }
            if ui.small_button("del").clickable().clicked() {
                to_delete = Some(p);
            }
        });
    }
    if let Some(p) = to_select {
        app.editor.current_phase = p;
    }
    if let Some(p) = to_insert_after {
        app.editor.state.insert_phase_after(p);
        if app.editor.current_phase > p {
            app.editor.current_phase += 1;
        }
    }
    if let Some(p) = to_delete {
        app.editor.state.delete_phase(p);
    }
    ui.separator();

    titan_core::style::section_title(ui, "controls");
    ui.small("LMB drag: pan  |  wheel: zoom");
    ui.small("RMB: place / retag (drag works)");
    ui.small("Shift+RMB: erase (drag works)");
    ui.small("MMB: rotate at cursor");
    ui.separator();
    titan_core::style::section_title(ui, "keys");
    ui.small("esc: view | p: phase view");
    ui.small("1-9: phase view @ N");
    ui.small("letters c/a/s/b/h/f/g/n/k/l/w/r: place");
    ui.small("ctrl-s save | ctrl-z undo | ctrl-shift-z redo");
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
            let egui::Event::Key {
                key, pressed: true, ..
            } = ev
            else {
                continue;
            };
            match key {
                egui::Key::S if ctrl => app.editor.save(),
                egui::Key::Z if ctrl && shift => app.editor.state.redo(),
                egui::Key::Z if ctrl => app.editor.state.undo(),
                egui::Key::Escape => set_mode(app, Mode::View),
                egui::Key::P => set_mode(app, Mode::PhaseView),
                egui::Key::Q if ctrl => quit = true,
                egui::Key::Minus => {
                    if app.editor.n_builders > 0 {
                        app.editor.n_builders -= 1;
                    }
                }
                egui::Key::Plus | egui::Key::Equals => {
                    app.editor.n_builders += 1;
                }
                _ => {
                    if let Some(n) = key_to_phase_1based(*key) {
                        app.editor.current_phase = n - 1;
                        set_mode(app, Mode::PhaseView);
                    } else if let Some(e) = key_to_entity(*key) {
                        set_mode(app, Mode::Place(e));
                    }
                }
            }
        }
    });

    quit
}

const fn key_to_phase_1based(k: egui::Key) -> Option<i32> {
    Some(match k {
        egui::Key::Num1 => 1,
        egui::Key::Num2 => 2,
        egui::Key::Num3 => 3,
        egui::Key::Num4 => 4,
        egui::Key::Num5 => 5,
        egui::Key::Num6 => 6,
        egui::Key::Num7 => 7,
        egui::Key::Num8 => 8,
        egui::Key::Num9 => 9,
        _ => return None,
    })
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
