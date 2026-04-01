use eframe::egui;
use egui::Rect;

use crate::app::App;
use crate::proto;
use crate::state::{Entity, EntityKind, GameState};

pub fn render_help(ctx: &egui::Context, show: &mut bool) {
    egui::Window::new("Help")
        .open(show)
        .resizable(false)
        .show(ctx, |ui| {
            ui.monospace(
                "\
Space       Play/Pause
Right       Step +1
Left        Step -1
S-Right     Step +10
S-Left      Step -10
g / Home    Turn 0
G / End     Last turn
+ / -       Speed up/down
1-9         Jump to 10-90%

hjkl        Move cursor
Enter       Select entity
Tab         Cycle entities
f           Follow entity
Esc/q       Deselect/Quit

Click       Select tile/entity
M-Drag      Pan map
Scroll      Zoom

i           Indicators
n           Network
v           Vision
?           This help",
            );
        });
}

pub fn render_sidebar(ui: &mut egui::Ui, app: &App) {
    let state = &app.game.turns[app.turn];

    egui::Panel::right("info")
        .exact_size(250.0)
        .resizable(false)
        .show_inside(ui, |ui| {
            ui.heading("Status");
            ui.separator();

            let a = &state.players[0];
            let b = &state.players[1];
            ui.monospace(format!(
                "Turn: {}/{}\n\n\
             Team A: {} Ti  {} Ax\n\
             Mined:  {} Ti  {} Ax\n\n\
             Team B: {} Ti  {} Ax\n\
             Mined:  {} Ti  {} Ax",
                app.turn,
                app.game.turn_count(),
                a.titanium,
                a.axionite,
                a.ti_collected,
                a.ax_collected,
                b.titanium,
                b.axionite,
                b.ti_collected,
                b.ax_collected,
            ));

            ui.add_space(8.0);
            ui.heading("Inspector");
            ui.separator();

            ui.monospace(format_tile_info(&app.game, app.cursor));

            let at_cursor: Vec<&Entity> = state
                .entities
                .values()
                .filter(|e| e.pos == (app.cursor.0, app.cursor.1))
                .collect();

            for e in &at_cursor {
                ui.add_space(4.0);
                ui.separator();
                ui.monospace(format_entity_info(e, &state.cpu_time_us));
            }

            ui.add_space(8.0);
            ui.heading("Log");
            ui.separator();

            let log_ids: Vec<i32> = at_cursor.iter().map(|e| e.id).collect();
            let log_text: String = state
                .outputs
                .iter()
                .filter(|(oid, _)| log_ids.contains(oid))
                .map(|(_, s)| s.as_str())
                .collect::<Vec<_>>()
                .join("\n");
            egui::ScrollArea::vertical()
                .max_height(ui.available_height())
                .show(ui, |ui| {
                    ui.monospace(log_text);
                });
        });
}

fn icon_button(ui: &mut egui::Ui, icon: &str, size: f32) -> egui::Response {
    let text = egui::RichText::new(icon).size(size);
    let btn = egui::Button::new(text).frame(false);
    let response = ui.add(btn);
    if response.hovered() {
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }
    response
}

pub fn render_scrubber(ui: &mut egui::Ui, app: &mut App) {
    egui::Panel::bottom("scrubber")
        .exact_size(64.0)
        .resizable(false)
        .show_inside(ui, |ui| {
            let total = app.game.turn_count().max(1);

            ui.add_space(2.0);
            let desired = egui::vec2(ui.available_width(), 20.0);
            let (bar_response, bar_painter) =
                ui.allocate_painter(desired, egui::Sense::click_and_drag());
            let bar_rect = bar_response.rect;

            if bar_response.hovered() {
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
            }

            bar_painter.rect_filled(bar_rect, 4.0, ui.visuals().extreme_bg_color);
            let frac = app.turn as f32 / total as f32;
            let fill_rect = Rect::from_min_max(
                bar_rect.left_top(),
                egui::pos2(
                    bar_rect.width().mul_add(frac, bar_rect.left()),
                    bar_rect.bottom(),
                ),
            );
            bar_painter.rect_filled(
                fill_rect,
                4.0,
                egui::Color32::from_rgb(0x40, 0xa0, 0xc0),
            );

            if (bar_response.clicked() || bar_response.dragged())
                && let Some(pos) = bar_response.interact_pointer_pos()
            {
                let f = ((pos.x - bar_rect.left()) / bar_rect.width()).clamp(0.0, 1.0);
                app.turn = (f * total as f32) as usize;
            }

            ui.add_space(4.0);
            ui.horizontal(|ui| {
                let icon_size = 18.0;

                if icon_button(ui, "\u{F048}", icon_size).clicked() {
                    app.step_backward(1);
                }

                let play_icon = if app.playing { "\u{F04C}" } else { "\u{F04B}" };
                if icon_button(ui, play_icon, icon_size).clicked() {
                    app.playing = !app.playing;
                }

                if icon_button(ui, "\u{F051}", icon_size).clicked() {
                    app.step_forward(1);
                }

                ui.add_space(12.0);

                ui.add_enabled_ui(app.speed > 0, |ui| {
                    if icon_button(ui, "\u{F049}", icon_size).clicked() {
                        app.speed = (app.speed - 1).max(0);
                    }
                });

                ui.label(
                    egui::RichText::new(format!("{}x", app.speed_label())).size(14.0),
                );

                ui.add_enabled_ui(app.speed < 8, |ui| {
                    if icon_button(ui, "\u{F050}", icon_size).clicked() {
                        app.speed = (app.speed + 1).min(8);
                    }
                });

                ui.add_space(12.0);
                ui.label(
                    egui::RichText::new(format!("{}/{}", app.turn, total)).size(14.0),
                );
            });
        });
}

fn format_entity_info(e: &Entity, cpu_time_us: &std::collections::HashMap<i32, u32>) -> String {
    use std::fmt::Write;
    let team = match e.team {
        proto::Team::A => "A",
        proto::Team::B => "B",
    };
    let kind_name = match &e.kind {
        EntityKind::BuilderBot { .. } => "Builder Bot",
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => "Core",
        EntityKind::Conveyor { .. } => "Conveyor",
        EntityKind::ArmouredConveyor { .. } => "Armoured Conv",
        EntityKind::Splitter { .. } => "Splitter",
        EntityKind::Bridge { .. } => "Bridge",
        EntityKind::Harvester { .. } => "Harvester",
        EntityKind::Foundry { .. } => "Foundry",
        EntityKind::Road => "Road",
        EntityKind::Barrier => "Barrier",
        EntityKind::Marker { .. } => "Marker",
        EntityKind::Gunner { .. } => "Gunner",
        EntityKind::Sentinel { .. } => "Sentinel",
        EntityKind::Breach { .. } => "Breach",
        EntityKind::Launcher { .. } => "Launcher",
    };
    let mut s = format!(
        "({},{}) {}\nTeam {}\nHP: {}/{}\nID: {}",
        e.pos.0, e.pos.1, kind_name, team, e.hp, e.max_hp, e.id
    );
    match &e.kind {
        EntityKind::BuilderBot { action_cd, move_cd } => {
            let _ = write!(s, "\nAct CD: {action_cd}\nMov CD: {move_cd}");
        }
        EntityKind::Bridge { target, stored } => {
            let _ = write!(
                s,
                "\nTarget: ({},{})\nStored: {stored:?}",
                target.0, target.1
            );
        }
        EntityKind::Conveyor { dir, stored }
        | EntityKind::ArmouredConveyor { dir, stored }
        | EntityKind::Splitter { dir, stored } => {
            let _ = write!(s, "\nDir: {dir:?}\nStored: {stored:?}");
        }
        EntityKind::Harvester {
            cooldown,
            resource_type,
        } => {
            let _ = write!(s, "\nCD: {cooldown}\nRes: {resource_type:?}");
        }
        EntityKind::Marker { value } => {
            let _ = write!(s, "\n{value:#010x}\n{value:#034b}\n{value}");
        }
        EntityKind::Gunner {
            dir,
            ammo_type,
            ammo,
        }
        | EntityKind::Sentinel {
            dir,
            ammo_type,
            ammo,
        }
        | EntityKind::Breach {
            dir,
            ammo_type,
            ammo,
        } => {
            let _ = write!(s, "\nDir: {dir:?}\nAmmo: {ammo} {ammo_type:?}");
        }
        _ => {}
    }
    if let Some(&us) = cpu_time_us.get(&e.id) {
        let _ = write!(s, "\nCPU: {us}\u{00b5}s");
    }
    s
}

fn format_tile_info(game: &GameState, pos: (i32, i32)) -> String {
    let env = game
        .env
        .get(pos.1 as usize)
        .and_then(|r| r.get(pos.0 as usize))
        .copied()
        .unwrap_or(proto::Environment::EnvEmpty);
    let env_name = match env {
        proto::Environment::EnvEmpty => "Empty",
        proto::Environment::EnvWall => "Wall",
        proto::Environment::EnvOreTitanium => "Ore (Ti)",
        proto::Environment::EnvOreAxionite => "Ore (Ax)",
    };
    format!(
        "({},{}) {}\n\nNo entity selected\n(Enter/click to select)",
        pos.0, pos.1, env_name
    )
}
