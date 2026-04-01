use std::collections::HashMap;

use eframe::egui;
use egui::Rect;

use crate::app::App;
use crate::proto;
use crate::state::{Entity, EntityKind, GameState, TurnState};
use crate::vis::{self, VisField, VisState};

const fn entity_scale_percent(kind: &EntityKind) -> f32 {
    match kind {
        EntityKind::Road => 0.5,
        EntityKind::Conveyor { .. }
        | EntityKind::ArmouredConveyor { .. }
        | EntityKind::Splitter { .. }
        | EntityKind::Barrier => 1.0,
        EntityKind::Harvester { .. } => 5.0,
        EntityKind::Bridge { .. }
        | EntityKind::Gunner { .. }
        | EntityKind::Breach { .. }
        | EntityKind::Launcher { .. } => 10.0,
        EntityKind::BuilderBot { .. } | EntityKind::Sentinel { .. } => 20.0,
        EntityKind::Foundry { .. } => 100.0,
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } | EntityKind::Marker { .. } => 0.0,
    }
}

const fn entity_kind_label(kind: &EntityKind) -> &'static str {
    match kind {
        EntityKind::BuilderBot { .. } => "Builder",
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => "Core",
        EntityKind::Conveyor { .. } => "Conveyor",
        EntityKind::ArmouredConveyor { .. } => "Arm. Conv",
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
    }
}

const fn kind_key(kind: &EntityKind) -> u8 {
    match kind {
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } => 0,
        EntityKind::BuilderBot { .. } => 1,
        EntityKind::Road => 2,
        EntityKind::Conveyor { .. } => 3,
        EntityKind::ArmouredConveyor { .. } => 4,
        EntityKind::Splitter { .. } => 5,
        EntityKind::Bridge { .. } => 6,
        EntityKind::Harvester { .. } => 7,
        EntityKind::Foundry { .. } => 8,
        EntityKind::Barrier => 9,
        EntityKind::Marker { .. } => 10,
        EntityKind::Gunner { .. } => 11,
        EntityKind::Sentinel { .. } => 12,
        EntityKind::Breach { .. } => 13,
        EntityKind::Launcher { .. } => 14,
    }
}

const fn entity_base_cost(kind: &EntityKind) -> Option<(i32, i32)> {
    match kind {
        EntityKind::BuilderBot { .. } | EntityKind::Sentinel { .. } => Some((30, 0)),
        EntityKind::Conveyor { .. } | EntityKind::Barrier => Some((3, 0)),
        EntityKind::Splitter { .. } => Some((6, 0)),
        EntityKind::Bridge { .. } | EntityKind::Harvester { .. } | EntityKind::Launcher { .. } => {
            Some((20, 0))
        }
        EntityKind::ArmouredConveyor { .. } => Some((5, 5)),
        EntityKind::Road => Some((1, 0)),
        EntityKind::Foundry { .. } => Some((40, 0)),
        EntityKind::Gunner { .. } => Some((10, 0)),
        EntityKind::Breach { .. } => Some((15, 10)),
        EntityKind::Core { .. } | EntityKind::CoreEdge { .. } | EntityKind::Marker { .. } => None,
    }
}

struct TeamStats {
    counts: HashMap<u8, u32>,
    total_scale: f32,
    scale_by_kind: HashMap<u8, f32>,
}

fn compute_team_stats(state: &TurnState, team: proto::Team) -> TeamStats {
    let mut counts: HashMap<u8, u32> = HashMap::new();
    let mut total_scale = 0.0_f32;
    let mut scale_by_kind: HashMap<u8, f32> = HashMap::new();

    for e in state.entities.values() {
        if e.team != team {
            continue;
        }
        let key = kind_key(&e.kind);
        *counts.entry(key).or_default() += 1;
        let sc = entity_scale_percent(&e.kind);
        total_scale += sc;
        *scale_by_kind.entry(key).or_default() += sc;
    }

    TeamStats {
        counts,
        total_scale,
        scale_by_kind,
    }
}

fn nice_tick_step(max_val: f32) -> f32 {
    let rough = max_val / 3.0;
    let mag = 10.0_f32.powf(rough.log10().floor());
    let norm = rough / mag;
    let step = if norm < 1.5 {
        1.0
    } else if norm < 3.5 {
        2.0
    } else if norm < 7.5 {
        5.0
    } else {
        10.0
    };
    step * mag
}

#[allow(clippy::too_many_lines)]
fn draw_resource_graph(ui: &mut egui::Ui, game: &GameState, turn: usize, team_idx: usize) {
    let desired = egui::vec2(ui.available_width(), 90.0);
    let (response, painter) = ui.allocate_painter(desired, egui::Sense::hover());
    let full_rect = response.rect;

    painter.rect_filled(full_rect, 2.0, ui.visuals().extreme_bg_color);

    if turn == 0 {
        return;
    }

    let mut max_ti = 500_f32;
    let mut max_ax = 1_f32;
    for t in 0..=turn {
        let p = &game.turns[t].players[team_idx];
        max_ti = max_ti.max(p.titanium as f32);
        max_ax = max_ax.max(p.axionite as f32);
    }
    let max_val = max_ti.max(max_ax);

    let plot = Rect::from_min_max(
        egui::pos2(full_rect.left() + 36.0, full_rect.top() + 2.0),
        egui::pos2(full_rect.right() - 2.0, full_rect.bottom() - 14.0),
    );

    let grid_color = egui::Color32::from_rgb(0x40, 0x40, 0x40);
    let label_color = egui::Color32::from_rgb(0x90, 0x90, 0x90);
    let font = egui::FontId::monospace(9.0);

    let y_step = nice_tick_step(max_val);
    let y_ticks = (max_val / y_step) as i32;
    for i in 1..=y_ticks {
        let tick_val = y_step * i as f32;
        let y = (tick_val / max_val).mul_add(-plot.height(), plot.bottom());
        painter.line_segment(
            [egui::pos2(plot.left(), y), egui::pos2(plot.right(), y)],
            egui::Stroke::new(0.5, grid_color),
        );
        let label = if tick_val >= 1000.0 {
            format!("{}k", (tick_val / 1000.0) as i32)
        } else {
            format!("{}", tick_val as i32)
        };
        painter.text(
            egui::pos2(plot.left() - 3.0, y),
            egui::Align2::RIGHT_CENTER,
            label,
            font.clone(),
            label_color,
        );
    }

    let x_step = nice_tick_step(turn as f32);
    let x_ticks = (turn as f32 / x_step) as i32;
    for i in 1..=x_ticks {
        let tick_turn = x_step * i as f32;
        let x = (tick_turn / turn as f32).mul_add(plot.width(), plot.left());
        painter.line_segment(
            [egui::pos2(x, plot.top()), egui::pos2(x, plot.bottom())],
            egui::Stroke::new(0.5, grid_color),
        );
        painter.text(
            egui::pos2(x, plot.bottom() + 2.0),
            egui::Align2::CENTER_TOP,
            format!("{}", tick_turn as i32),
            font.clone(),
            label_color,
        );
    }

    let ti_color = egui::Color32::from_rgb(0xc0, 0xc0, 0xc0);
    let ax_color = egui::Color32::from_rgb(0x60, 0xd0, 0x60);

    for resource in 0..2 {
        let color = if resource == 0 { ti_color } else { ax_color };
        let first_val = if resource == 0 {
            game.turns[0].players[team_idx].titanium as f32
        } else {
            game.turns[0].players[team_idx].axionite as f32
        };
        let mut cx = plot.left();
        let mut cy = (first_val / max_val)
            .mul_add(-plot.height(), plot.bottom())
            .round();

        for t in 1..=turn {
            let p = &game.turns[t].players[team_idx];
            let val = if resource == 0 {
                p.titanium as f32
            } else {
                p.axionite as f32
            };
            let x = (t as f32 / turn as f32).mul_add(plot.width(), plot.left());
            let y = (val / max_val)
                .mul_add(-plot.height(), plot.bottom())
                .round();
            painter.line_segment(
                [egui::pos2(cx, cy), egui::pos2(x, y)],
                egui::Stroke::new(2.0, color),
            );
            cx = x;
            cy = y;
        }
    }
}

#[allow(clippy::too_many_lines)]
pub fn render_left_sidebar(ui: &mut egui::Ui, app: &App) {
    let state = &app.game.turns[app.turn];

    egui::Panel::left("stats")
        .default_size(220.0)
        .frame(egui::Frame::side_top_panel(ui.style()).inner_margin(8.0))
        .show_inside(ui, |ui| {
            egui::ScrollArea::vertical().show(ui, |ui| {
                if let Some(winner) = app.game.winner {
                    let winner_label = match winner {
                        proto::Team::A => "Team A",
                        proto::Team::B => "Team B",
                    };
                    let final_state = app.game.turns.last().unwrap();
                    let loser_core_destroyed = !final_state
                        .entities
                        .values()
                        .any(|e| e.team != winner && matches!(e.kind, EntityKind::Core { .. }));
                    let reason = if loser_core_destroyed {
                        "Core destroyed"
                    } else {
                        let fa = &final_state.players[0];
                        let fb = &final_state.players[1];
                        if fa.ax_collected != fb.ax_collected {
                            "Tiebreak: Ax delivered"
                        } else if fa.ti_collected != fb.ti_collected {
                            "Tiebreak: Ti delivered"
                        } else {
                            let harvesters = |team: proto::Team| {
                                final_state
                                    .entities
                                    .values()
                                    .filter(|e| {
                                        e.team == team
                                            && matches!(e.kind, EntityKind::Harvester { .. })
                                    })
                                    .count()
                            };
                            if harvesters(proto::Team::A) != harvesters(proto::Team::B) {
                                "Tiebreak: Harvesters"
                            } else if fa.axionite != fb.axionite {
                                "Tiebreak: Ax stored"
                            } else if fa.titanium != fb.titanium {
                                "Tiebreak: Ti stored"
                            } else {
                                "Tiebreak: Coinflip"
                            }
                        }
                    };
                    ui.heading(format!("{winner_label} wins"));
                    ui.label(reason);
                    ui.separator();
                    ui.add_space(4.0);
                }

                let a = &state.players[0];
                let b = &state.players[1];

                ui.heading("Resources");
                ui.separator();

                egui::Grid::new("resources").num_columns(3).show(ui, |ui| {
                    ui.label("");
                    ui.strong("Team A");
                    ui.strong("Team B");
                    ui.end_row();

                    ui.label("Ti");
                    ui.monospace(format!("{}", a.titanium));
                    ui.monospace(format!("{}", b.titanium));
                    ui.end_row();

                    ui.label("Ax");
                    ui.monospace(format!("{}", a.axionite));
                    ui.monospace(format!("{}", b.axionite));
                    ui.end_row();

                    ui.label("Ti mined");
                    ui.monospace(format!("{}", a.ti_collected));
                    ui.monospace(format!("{}", b.ti_collected));
                    ui.end_row();

                    ui.label("Ax mined");
                    ui.monospace(format!("{}", a.ax_collected));
                    ui.monospace(format!("{}", b.ax_collected));
                    ui.end_row();
                });

                ui.add_space(8.0);
                ui.label("Team A resources");
                draw_resource_graph(ui, &app.game, app.turn, 0);
                ui.add_space(4.0);
                ui.label("Team B resources");
                draw_resource_graph(ui, &app.game, app.turn, 1);

                ui.add_space(8.0);
                ui.heading("Entity Counts");
                ui.separator();

                let stats_a = compute_team_stats(state, proto::Team::A);
                let stats_b = compute_team_stats(state, proto::Team::B);

                let mut all_keys: Vec<u8> = stats_a
                    .counts
                    .keys()
                    .chain(stats_b.counts.keys())
                    .copied()
                    .collect();
                all_keys.sort_unstable();
                all_keys.dedup();

                let dummy = EntityKind::Road;
                let kind_for_key = |key: u8| -> &'static str {
                    for e in state.entities.values() {
                        if kind_key(&e.kind) == key {
                            return entity_kind_label(&e.kind);
                        }
                    }
                    entity_kind_label(&dummy)
                };

                egui::Grid::new("entity_counts")
                    .num_columns(3)
                    .show(ui, |ui| {
                        ui.label("");
                        ui.strong("A");
                        ui.strong("B");
                        ui.end_row();

                        for &key in &all_keys {
                            let ca = stats_a.counts.get(&key).copied().unwrap_or(0);
                            let cb = stats_b.counts.get(&key).copied().unwrap_or(0);
                            ui.label(kind_for_key(key));
                            ui.monospace(format!("{ca}"));
                            ui.monospace(format!("{cb}"));
                            ui.end_row();
                        }
                    });

                ui.add_space(8.0);
                ui.heading("Scaling");
                ui.separator();

                ui.monospace(format!(
                    "A: {:.0}%  B: {:.0}%",
                    100.0 + stats_a.total_scale,
                    100.0 + stats_b.total_scale,
                ));

                ui.add_space(4.0);
                egui::Grid::new("scaling").num_columns(3).show(ui, |ui| {
                    ui.label("");
                    ui.strong("A");
                    ui.strong("B");
                    ui.end_row();

                    for &key in &all_keys {
                        let sa = stats_a.scale_by_kind.get(&key).copied().unwrap_or(0.0);
                        let sb = stats_b.scale_by_kind.get(&key).copied().unwrap_or(0.0);
                        if sa == 0.0 && sb == 0.0 {
                            continue;
                        }
                        ui.label(kind_for_key(key));
                        ui.monospace(format!("{sa:.0}%"));
                        ui.monospace(format!("{sb:.0}%"));
                        ui.end_row();
                    }
                });

                ui.add_space(8.0);
                ui.heading("Current Costs");
                ui.separator();

                let scale_a = (100.0 + stats_a.total_scale) / 100.0;
                let scale_b = (100.0 + stats_b.total_scale) / 100.0;

                let cost_kinds: &[(EntityKind, &str)] = &[
                    (
                        EntityKind::BuilderBot {
                            action_cd: 0,
                            move_cd: 0,
                        },
                        "Builder",
                    ),
                    (EntityKind::Road, "Road"),
                    (
                        EntityKind::Conveyor {
                            dir: proto::Direction::DirNorth,
                            stored: proto::ResourceType::ResourceNone,
                        },
                        "Conveyor",
                    ),
                    (
                        EntityKind::Splitter {
                            dir: proto::Direction::DirNorth,
                            stored: proto::ResourceType::ResourceNone,
                        },
                        "Splitter",
                    ),
                    (
                        EntityKind::Bridge {
                            target: (0, 0),
                            stored: proto::ResourceType::ResourceNone,
                        },
                        "Bridge",
                    ),
                    (
                        EntityKind::ArmouredConveyor {
                            dir: proto::Direction::DirNorth,
                            stored: proto::ResourceType::ResourceNone,
                        },
                        "Arm. Conv",
                    ),
                    (EntityKind::Barrier, "Barrier"),
                    (
                        EntityKind::Harvester {
                            cooldown: 0,
                            resource_type: proto::ResourceType::ResourceNone,
                        },
                        "Harvester",
                    ),
                    (
                        EntityKind::Foundry {
                            stored: proto::ResourceType::ResourceNone,
                        },
                        "Foundry",
                    ),
                    (
                        EntityKind::Gunner {
                            dir: proto::Direction::DirNorth,
                            ammo_type: proto::ResourceType::ResourceNone,
                            ammo: 0,
                        },
                        "Gunner",
                    ),
                    (
                        EntityKind::Sentinel {
                            dir: proto::Direction::DirNorth,
                            ammo_type: proto::ResourceType::ResourceNone,
                            ammo: 0,
                        },
                        "Sentinel",
                    ),
                    (
                        EntityKind::Breach {
                            dir: proto::Direction::DirNorth,
                            ammo_type: proto::ResourceType::ResourceNone,
                            ammo: 0,
                        },
                        "Breach",
                    ),
                    (
                        EntityKind::Launcher {
                            ammo_type: proto::ResourceType::ResourceNone,
                            ammo: 0,
                        },
                        "Launcher",
                    ),
                ];

                egui::Grid::new("costs").num_columns(3).show(ui, |ui| {
                    ui.label("");
                    ui.strong("A");
                    ui.strong("B");
                    ui.end_row();

                    for (kind, label) in cost_kinds {
                        if let Some((ti, ax)) = entity_base_cost(kind) {
                            let ti_a = (scale_a * ti as f32).floor() as i32;
                            let ax_a = (scale_a * ax as f32).floor() as i32;
                            let ti_b = (scale_b * ti as f32).floor() as i32;
                            let ax_b = (scale_b * ax as f32).floor() as i32;
                            ui.label(*label);
                            if ax == 0 {
                                ui.monospace(format!("{ti_a}"));
                                ui.monospace(format!("{ti_b}"));
                            } else {
                                ui.monospace(format!("{ti_a}+{ax_a}"));
                                ui.monospace(format!("{ti_b}+{ax_b}"));
                            }
                            ui.end_row();
                        }
                    }
                });
            });
        });
}

pub fn render_right_sidebar(ui: &mut egui::Ui, app: &mut App) {
    let state = &app.game.turns[app.turn];

    egui::Panel::right("info")
        .default_size(250.0)
        .frame(egui::Frame::side_top_panel(ui.style()).inner_margin(8.0))
        .show_inside(ui, |ui| {
            egui::ScrollArea::vertical().show(ui, |ui| {
                ui.checkbox(&mut app.show_indicators, "Show indicators (i)");
                ui.checkbox(&mut app.show_flow, "Show flow");
                ui.checkbox(&mut app.show_ranges, "Show ranges");

                let vis_fields = collect_vis_fields(state, app.selected_entity);
                if !vis_fields.is_empty() {
                    ui.add_space(8.0);
                    ui.heading("Bot State");
                    ui.separator();

                    let mut field_names: Vec<&String> = vis_fields.keys().collect();
                    field_names.sort();

                    for name in &field_names {
                        match vis_fields.get(*name) {
                            Some(VisField::Scalar { data }) => {
                                ui.monospace(format!("{name}: {data}"));
                            }
                            Some(
                                VisField::Grid { .. }
                                | VisField::Tiles { .. }
                                | VisField::VectorField { .. },
                            ) => {
                                let mut enabled = app.vis_overlays.contains(*name);
                                if ui.checkbox(&mut enabled, name.as_str()).changed() {
                                    if enabled {
                                        app.vis_overlays.insert((*name).clone());
                                    } else {
                                        app.vis_overlays.remove(*name);
                                    }
                                }
                            }
                            None => {}
                        }
                    }
                }

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
                ui.monospace(log_text);
            });
        });
}

fn collect_vis_fields(state: &TurnState, selected: Option<i32>) -> VisState {
    let id = selected.unwrap_or(-1);
    state
        .vis_data
        .get(&id)
        .map_or_else(VisState::new, |jsons| vis::parse_vis(jsons))
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
            bar_painter.rect_filled(fill_rect, 4.0, egui::Color32::from_rgb(0x40, 0xa0, 0xc0));

            if (bar_response.clicked() || bar_response.dragged())
                && let Some(pos) = bar_response.interact_pointer_pos()
            {
                let f = ((pos.x - bar_rect.left()) / bar_rect.width()).clamp(0.0, 1.0);
                app.turn = (f * total as f32) as usize;
            }

            if bar_response.hovered() {
                let scroll = ui.input(|i| {
                    let mut s = 0.0_f32;
                    for event in &i.raw.events {
                        if let egui::Event::MouseWheel { delta, .. } = event {
                            s += delta.y;
                        }
                    }
                    s
                });
                if scroll > 0.0 {
                    app.step_forward(1);
                } else if scroll < 0.0 {
                    app.step_backward(1);
                }
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

                ui.label(egui::RichText::new(format!("{}x", app.speed_label())).size(14.0));

                ui.add_enabled_ui(app.speed < 8, |ui| {
                    if icon_button(ui, "\u{F050}", icon_size).clicked() {
                        app.speed = (app.speed + 1).min(8);
                    }
                });

                ui.add_space(12.0);
                ui.label(egui::RichText::new(format!("{}/{}", app.turn, total)).size(14.0));
            });
        });
}

fn format_entity_info(e: &Entity, cpu_time_us: &HashMap<i32, u32>) -> String {
    use std::fmt::Write;
    let team = match e.team {
        proto::Team::A => "A",
        proto::Team::B => "B",
    };
    let kind_name = entity_kind_label(&e.kind);
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
    format!("({},{}) {}", pos.0, pos.1, env_name)
}
