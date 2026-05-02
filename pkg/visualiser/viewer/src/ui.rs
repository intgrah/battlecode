use std::collections::HashMap;

use eframe::egui;
use egui::Rect;

use crate::app::App;
use crate::entity;
use crate::proto;
use crate::state::{Entity, EntityKind, GameState, TurnState};
use crate::vis::{LogNode, ScalarValue, Tagged};

struct TeamStats {
    counts: HashMap<u8, u32>,
    total_scale_millis: u32,
    scale_millis_by_kind: HashMap<u8, u32>,
}

fn compute_team_stats(state: &TurnState, team: proto::Team) -> TeamStats {
    let mut counts: HashMap<u8, u32> = HashMap::new();
    let mut total_scale_millis = 0_u32;
    let mut scale_millis_by_kind: HashMap<u8, u32> = HashMap::new();

    for e in state.entities.values() {
        if e.team != team {
            continue;
        }
        let key = entity::sort_key(&e.kind);
        *counts.entry(key).or_default() += 1;
        let sc = entity::scale_millis(&e.kind);
        total_scale_millis += sc;
        *scale_millis_by_kind.entry(key).or_default() += sc;
    }

    TeamStats {
        counts,
        total_scale_millis,
        scale_millis_by_kind,
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
fn draw_turn_time_graph(ui: &mut egui::Ui, game: &GameState, turn: usize, entity_id: i32) {
    if turn == 0 {
        return;
    }

    // Collect CPU time for this specific entity across all turns.
    let mut max_us = 1_f32;
    let mut points: Vec<(usize, f32)> = Vec::new();
    for t in 0..=turn {
        if let Some(&us) = game.turns[t].cpu_time_us.get(&entity_id) {
            let us_f = us as f32;
            max_us = max_us.max(us_f);
            points.push((t, us_f));
        }
    }

    if points.is_empty() {
        return;
    }

    let desired = egui::vec2(ui.available_width(), 90.0);
    let (response, painter) = ui.allocate_painter(desired, egui::Sense::hover());
    let full_rect = response.rect;

    painter.rect_filled(full_rect, 2.0, ui.visuals().extreme_bg_color);

    let plot = Rect::from_min_max(
        egui::pos2(full_rect.left() + 36.0, full_rect.top() + 2.0),
        egui::pos2(full_rect.right() - 2.0, full_rect.bottom() - 14.0),
    );

    let grid_color = egui::Color32::from_rgb(0x40, 0x40, 0x40);
    let label_color = egui::Color32::from_rgb(0x90, 0x90, 0x90);
    let font = egui::FontId::monospace(9.0);

    // Y-axis grid (microseconds).
    let y_step = nice_tick_step(max_us);
    let y_ticks = (max_us / y_step) as i32;
    for i in 1..=y_ticks {
        let tick_val = y_step * i as f32;
        let y = (tick_val / max_us).mul_add(-plot.height(), plot.bottom());
        painter.line_segment(
            [egui::pos2(plot.left(), y), egui::pos2(plot.right(), y)],
            egui::Stroke::new(0.5, grid_color),
        );
        let label = if tick_val >= 1_000_000.0 {
            format!("{:.1}s", tick_val / 1_000_000.0)
        } else if tick_val >= 1000.0 {
            format!("{}ms", (tick_val / 1000.0) as i32)
        } else {
            format!("{}µs", tick_val as i32)
        };
        painter.text(
            egui::pos2(plot.left() - 3.0, y),
            egui::Align2::RIGHT_CENTER,
            label,
            font.clone(),
            label_color,
        );
    }

    // X-axis grid (turns).
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

    let line_color = egui::Color32::from_rgb(0xe0, 0xb0, 0x40);

    for window in points.windows(2) {
        let (t0, v0) = window[0];
        let (t1, v1) = window[1];
        if t1 != t0 + 1 {
            continue;
        }
        let x0 = (t0 as f32 / turn as f32).mul_add(plot.width(), plot.left());
        let y0 = (v0 / max_us).mul_add(-plot.height(), plot.bottom()).round();
        let x1 = (t1 as f32 / turn as f32).mul_add(plot.width(), plot.left());
        let y1 = (v1 / max_us).mul_add(-plot.height(), plot.bottom()).round();
        painter.line_segment(
            [egui::pos2(x0, y0), egui::pos2(x1, y1)],
            egui::Stroke::new(2.0, line_color),
        );
    }
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

                egui::Grid::new("resources")
                    .num_columns(3)
                    .min_col_width(60.0)
                    .show(ui, |ui| {
                        ui.label("");
                        ui.strong("Team A");
                        ui.strong("Team B");
                        ui.end_row();

                        ui.label("Ti");
                        ui.monospace(format!("{:>6}", a.titanium));
                        ui.monospace(format!("{:>6}", b.titanium));
                        ui.end_row();

                        ui.label("Ax");
                        ui.monospace(format!("{:>6}", a.axionite));
                        ui.monospace(format!("{:>6}", b.axionite));
                        ui.end_row();

                        ui.label("Ti mined");
                        ui.monospace(format!("{:>6}", a.ti_collected));
                        ui.monospace(format!("{:>6}", b.ti_collected));
                        ui.end_row();

                        ui.label("Ax mined");
                        ui.monospace(format!("{:>6}", a.ax_collected));
                        ui.monospace(format!("{:>6}", b.ax_collected));
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

                let kind_for_key = |key: u8| -> &'static str {
                    for e in state.entities.values() {
                        if entity::sort_key(&e.kind) == key {
                            return entity::label(&e.kind);
                        }
                    }
                    entity::label(&EntityKind::Road)
                };

                egui::Grid::new("entity_counts")
                    .num_columns(3)
                    .min_col_width(30.0)
                    .show(ui, |ui| {
                        ui.label("");
                        ui.strong("A");
                        ui.strong("B");
                        ui.end_row();

                        for &key in &all_keys {
                            let ca = stats_a.counts.get(&key).copied().unwrap_or(0);
                            let cb = stats_b.counts.get(&key).copied().unwrap_or(0);
                            ui.label(kind_for_key(key));
                            ui.monospace(format!("{ca:>3}"));
                            ui.monospace(format!("{cb:>3}"));
                            ui.end_row();
                        }
                    });

                ui.add_space(8.0);
                ui.heading("Scaling");
                ui.separator();

                let fmt_scale_total = |millis: u32| -> String {
                    let whole = 100 + millis / 10;
                    let frac = millis % 10;
                    format!("{whole:>4}.{frac}%")
                };
                let fmt_scale_contrib = |millis: u32| -> String {
                    let whole = millis / 10;
                    let frac = millis % 10;
                    format!("{whole:>4}.{frac}%")
                };

                ui.monospace(format!(
                    "A: {}  B: {}",
                    fmt_scale_total(stats_a.total_scale_millis),
                    fmt_scale_total(stats_b.total_scale_millis),
                ));

                ui.add_space(4.0);
                egui::Grid::new("scaling")
                    .num_columns(3)
                    .min_col_width(50.0)
                    .show(ui, |ui| {
                        ui.label("");
                        ui.strong("A");
                        ui.strong("B");
                        ui.end_row();

                        for &key in &all_keys {
                            let sa = stats_a.scale_millis_by_kind.get(&key).copied().unwrap_or(0);
                            let sb = stats_b.scale_millis_by_kind.get(&key).copied().unwrap_or(0);
                            if sa == 0 && sb == 0 {
                                continue;
                            }
                            ui.label(kind_for_key(key));
                            ui.monospace(fmt_scale_contrib(sa));
                            ui.monospace(fmt_scale_contrib(sb));
                            ui.end_row();
                        }
                    });

                ui.add_space(8.0);
                ui.heading("Current Costs");
                ui.separator();

                let scale_a_millis = stats_a.total_scale_millis;
                let scale_b_millis = stats_b.total_scale_millis;

                egui::Grid::new("costs")
                    .num_columns(3)
                    .min_col_width(55.0)
                    .show(ui, |ui| {
                        ui.label("");
                        ui.strong("A");
                        ui.strong("B");
                        ui.end_row();

                        let scaled = |base: (i32, i32), millis: u32| -> (i32, i32) {
                            let s = 1000 + millis as i32;
                            (base.0 * s / 1000, base.1 * s / 1000)
                        };
                        let fmt_cost = |(ti, ax): (i32, i32)| -> String {
                            if ax == 0 {
                                format!("{ti:>4}")
                            } else {
                                format!("{ti:>3}+{ax}")
                            }
                        };
                        for &(label, cost) in entity::BUILDABLE_COSTS {
                            ui.label(label);
                            ui.monospace(fmt_cost(scaled(cost, scale_a_millis)));
                            ui.monospace(fmt_cost(scaled(cost, scale_b_millis)));
                            ui.end_row();
                        }
                    });
            });
        });
}

/// Top-bar panel: rendering toggles, tile/entity inspector, actions
/// taken by the entity at the cursor. Resizable downwards. Lives at
/// the top so it doesn't compete for vertical room with the state-dump
/// and log columns on the right.
pub fn render_top_panel(ui: &mut egui::Ui, app: &mut App) {
    let state = &app.game.turns[app.turn];

    egui::Panel::top("config_inspector")
        .default_size(280.0)
        .resizable(true)
        .frame(egui::Frame::side_top_panel(ui.style()).inner_margin(8.0))
        .show_inside(ui, |ui| {
            // Layout: 6 horizontal columns laid out left-to-right.
            //   col 0: Config (rendering toggles)
            //   col 1: Tile env
            //   cols 2,3: Entity 1 — text, CPU graph
            //   cols 4,5: Entity 2 — text, CPU graph
            // Two entity slots cover the max occupancy (one building +
            // one builder/turret per tile). Empty slots stay blank in
            // place — no reflow when the cursor moves.
            let selected = app.cursor;
            ui.columns(6, |cols| {
                let (left, rest) = cols.split_at_mut(1);
                let (envc, ents) = rest.split_at_mut(1);

                // Config
                left[0].label(egui::RichText::new("Config").strong());
                left[0].separator();
                left[0].checkbox(&mut app.show_indicators, "Indicators (i)");
                left[0].checkbox(&mut app.show_flow, "Empirical flow (f)");
                left[0].checkbox(&mut app.show_ranges, "Ranges");
                left[0].checkbox(&mut app.show_connected_textures, "Connected textures");
                left[0].checkbox(&mut app.use_plain_roads, "Plain roads");
                left[0].checkbox(&mut app.highlight_builders, "Highlight builders");

                // Env column with the position header at the top.
                envc[0].label(
                    egui::RichText::new(format!("({},{})", selected.0, selected.1))
                        .monospace()
                        .size(18.0)
                        .strong(),
                );
                envc[0].monospace(format_tile_info(&app.game, selected));

                // Entities at the selected tile, sorted by sort_key
                // (so order is stable: building-ish first, builder
                // last per the existing convention).
                let mut at: Vec<&Entity> = state
                    .entities
                    .values()
                    .filter(|e| e.pos == selected)
                    .collect();
                at.sort_by_key(|e| entity::sort_key(&e.kind));

                let [text0, graph0, text1, graph1] = ents else {
                    unreachable!()
                };
                let slots: [(&mut egui::Ui, &mut egui::Ui); 2] = [(text0, graph0), (text1, graph1)];
                for (i, (text_col, graph_col)) in slots.into_iter().enumerate() {
                    if let Some(e) = at.get(i) {
                        text_col.monospace(format_entity_info(e, &state.cpu_time_us));
                        draw_turn_time_graph(graph_col, &app.game, app.turn, e.id);
                    }
                }
            });
        });
}

/// Right-hand column for the structured state dump (categorical tree
/// of vis fields). Independent panel so resizing it doesn't shrink the
/// log column. Hover-clears `hovered_vis_overlay` here since this is
/// where the hover gets set.
pub fn render_state_dump_panel(ui: &mut egui::Ui, app: &mut App) {
    let state = &app.game.turns[app.turn];

    // Hover overlay is transient: cleared every frame, set if any
    // hover-eligible row is currently being hovered. Sticky selection
    // survives across frames.
    app.hovered_vis_overlay = None;

    egui::Panel::right("state_dump")
        .default_size(250.0)
        .resizable(true)
        .frame(egui::Frame::side_top_panel(ui.style()).inner_margin(8.0))
        .show_inside(ui, |ui| {
            egui::ScrollArea::vertical().show(ui, |ui| {
                ui.heading("Bot State");
                ui.separator();
                if let Some(eid) = app.selected_entity
                    && let Some(tree) = state.log_trees.get(&eid)
                    && let Some(dump_node) = find_scope(&tree.root, "dump")
                {
                    let resolved = state.vis_data.get(&eid);
                    render_dump_node(
                        ui,
                        dump_node,
                        "dump",
                        &mut app.hover_tile,
                        &mut app.selected_vis_overlays,
                        &mut app.hovered_vis_overlay,
                        resolved,
                    );
                } else {
                    ui.weak("Select a builder to see its state dump.");
                }
            });
        });
}

/// Right-hand column for the structured log tree. Independent panel —
/// expanding the log doesn't shrink the state dump.
pub fn render_log_panel(ui: &mut egui::Ui, app: &mut App) {
    let state = &app.game.turns[app.turn];

    egui::Panel::right("log")
        .default_size(450.0)
        .resizable(true)
        .frame(egui::Frame::side_top_panel(ui.style()).inner_margin(8.0))
        .show_inside(ui, |ui| {
            egui::ScrollArea::vertical().show(ui, |ui| {
                ui.heading("Log");
                ui.separator();

                let at_cursor: Vec<&Entity> = state
                    .entities
                    .values()
                    .filter(|e| e.pos == (app.cursor.0, app.cursor.1))
                    .collect();
                let entity_ids: Vec<i32> = at_cursor.iter().map(|e| e.id).collect();

                for &eid in &entity_ids {
                    if let Some(tree) = state.log_trees.get(&eid) {
                        ui.label(egui::RichText::new(format!("entity {eid}")).strong());
                        let path = format!("logtree-{eid}");
                        render_log_node(ui, &tree.root, &path, &mut app.hover_tile);
                        if let Some(us) = tree.prev_flush_us {
                            ui.monospace(format!("prev_flush_us = {us}"));
                        }
                        ui.separator();
                    }
                }

                // Anything that didn't parse as a log tree shows up in
                // the raw outputs panel.
                let raw_text: String = state
                    .outputs
                    .iter()
                    .filter(|(oid, _)| entity_ids.contains(oid))
                    .map(|(_, s)| s.as_str())
                    .collect::<Vec<_>>()
                    .join("\n");
                if !raw_text.is_empty() {
                    ui.label("raw stdout:");
                    ui.monospace(raw_text);
                }
            });
        });
}

fn render_log_node(
    ui: &mut egui::Ui,
    node: &LogNode,
    path: &str,
    hover_tile: &mut Option<(i32, i32)>,
) {
    match node {
        LogNode::Scope { name, us, children } => {
            if name == "dump" {
                return;
            }
            let mut job = egui::text::LayoutJob::default();
            job.append(
                name,
                0.0,
                egui::TextFormat {
                    color: egui::Color32::from_rgb(160, 200, 240),
                    ..Default::default()
                },
            );
            if let Some(us) = us {
                job.append(
                    &format!(" ({us}μs)"),
                    0.0,
                    egui::TextFormat {
                        color: egui::Color32::GRAY,
                        ..Default::default()
                    },
                );
            }
            let resp = egui::CollapsingHeader::new(job)
                .id_salt(path)
                .default_open(true)
                .show(ui, |ui| {
                    for (i, c) in children.iter().enumerate() {
                        let child_path = format!("{path}/{i}");
                        render_log_node(ui, c, &child_path, hover_tile);
                    }
                });
            if resp.header_response.hovered() {
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
            }
        }
        LogNode::Msg { tmpl, args } => {
            ui.horizontal_wrapped(|ui| {
                let mut rest = tmpl.as_str();
                while let Some(open) = rest.find('{') {
                    if open > 0 {
                        ui.monospace(&rest[..open]);
                    }
                    let tail = &rest[open + 1..];
                    if let Some(close) = tail.find('}') {
                        let key = &tail[..close];
                        if let Some((_, v)) = args.iter().find(|(k, _)| k == key) {
                            render_tagged_inline(ui, v, hover_tile);
                        } else {
                            ui.monospace(format!("{{{key}}}"));
                        }
                        rest = &tail[close + 1..];
                    } else {
                        ui.monospace(rest);
                        rest = "";
                        break;
                    }
                }
                if !rest.is_empty() {
                    ui.monospace(rest);
                }
            });
        }
        LogNode::Vis { .. } => {}
    }
}

fn render_tagged_inline(ui: &mut egui::Ui, t: &Tagged, hover_tile: &mut Option<(i32, i32)>) {
    match t {
        Tagged::Scalar(s) => render_scalar_inline(ui, s, hover_tile),
        Tagged::Tiles(d) => {
            let label = if d.len() <= 4 {
                let parts: Vec<String> = d.iter().map(|(x, y)| format!("({x},{y})")).collect();
                format!("tiles[{}]", parts.join(", "))
            } else {
                format!("tiles[{} positions]", d.len())
            };
            ui.monospace(label);
        }
        Tagged::Grid { data, .. } => {
            let n = match data {
                crate::vis::GridData::Bool(v) => v.len(),
                crate::vis::GridData::U8(v) => v.len(),
                crate::vis::GridData::I16(v) => v.len(),
                crate::vis::GridData::U16(v) => v.len(),
                crate::vis::GridData::F32(v) => v.len(),
            };
            ui.monospace(format!("grid[{n}]"));
        }
        Tagged::Tile(pos) => match pos {
            Some((x, y)) => {
                let text =
                    egui::RichText::new(format!("({x},{y})")).color(egui::Color32::LIGHT_BLUE);
                let resp = ui.selectable_label(false, text);
                if resp.hovered() {
                    *hover_tile = Some((*x, *y));
                    ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                }
            }
            None => {
                ui.monospace("None");
            }
        },
        Tagged::Dot { pos, colour } => match pos {
            Some((x, y)) => {
                let text = egui::RichText::new(format!("({x},{y})"))
                    .color(egui::Color32::from_rgb(colour.r, colour.g, colour.b));
                let resp = ui.selectable_label(false, text);
                if resp.hovered() {
                    *hover_tile = Some((*x, *y));
                    ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                }
            }
            None => {
                ui.monospace("None");
            }
        },
        Tagged::Path { points, .. } => {
            ui.monospace(format!("path[{} points]", points.len()));
        }
        Tagged::VectorField(a) => {
            ui.monospace(format!("vectorfield[{}]", a.arrows.len()));
        }
        Tagged::Same => {
            ui.monospace("(same as prev turn)");
        }
    }
}

fn render_scalar_inline(ui: &mut egui::Ui, s: &ScalarValue, hover_tile: &mut Option<(i32, i32)>) {
    match s {
        ScalarValue::Pos(x, y) => {
            let text = egui::RichText::new(format!("({x},{y})")).color(egui::Color32::LIGHT_BLUE);
            let resp = ui.selectable_label(false, text);
            if resp.hovered() {
                *hover_tile = Some((*x, *y));
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
            }
        }
        ScalarValue::Null => {
            ui.monospace("None");
        }
        ScalarValue::List(items) if items.is_empty() => {
            ui.monospace("[]");
        }
        ScalarValue::List(items) => {
            ui.monospace("[");
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    ui.monospace(",");
                }
                render_scalar_inline(ui, item, hover_tile);
            }
            ui.monospace("]");
        }
        other => {
            ui.monospace(format!("{other}"));
        }
    }
}

/// One column of the Inspector. Renders env first, then any building
/// at `pos`, then any builder. Three slots max — those are the only

/// Return the first child scope of `node` named `name`, or None.
fn find_scope<'a>(node: &'a LogNode, name: &str) -> Option<&'a LogNode> {
    if let LogNode::Scope {
        name: n, children, ..
    } = node
    {
        if n == name {
            return Some(node);
        }
        for c in children {
            if let Some(found) = find_scope(c, name) {
                return Some(found);
            }
        }
    }
    None
}

/// Render a `dump` subtree as collapsible category headers with typed
/// rows. Called only with `node` being a Scope. `resolved` is the per-
/// builder `VisState` (Same markers already substituted by the parser);
/// the renderer prefers values from there over the inline tree value.
fn render_dump_node(
    ui: &mut egui::Ui,
    node: &LogNode,
    path: &str,
    hover_tile: &mut Option<(i32, i32)>,
    selected: &mut std::collections::HashSet<String>,
    hovered: &mut Option<String>,
    resolved: Option<&crate::vis::VisState>,
) {
    let LogNode::Scope { children, .. } = node else {
        return;
    };
    for (i, child) in children.iter().enumerate() {
        let child_path = format!("{path}/{i}");
        match child {
            LogNode::Scope {
                name,
                children: subs,
                ..
            } => {
                let header = egui::RichText::new(name)
                    .strong()
                    .color(egui::Color32::from_rgb(160, 200, 240));
                let resp = egui::CollapsingHeader::new(header)
                    .id_salt(&child_path)
                    .default_open(true)
                    .show(ui, |ui| {
                        for (j, sub) in subs.iter().enumerate() {
                            let sub_path = format!("{child_path}/{j}");
                            render_dump_entry(
                                ui, sub, &sub_path, hover_tile, selected, hovered, resolved,
                            );
                        }
                    });
                if resp.header_response.hovered() {
                    ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                }
            }
            _ => render_dump_entry(
                ui,
                child,
                &child_path,
                hover_tile,
                selected,
                hovered,
                resolved,
            ),
        }
    }
}

fn render_dump_entry(
    ui: &mut egui::Ui,
    node: &LogNode,
    path: &str,
    hover_tile: &mut Option<(i32, i32)>,
    selected: &mut std::collections::HashSet<String>,
    hovered: &mut Option<String>,
    resolved: Option<&crate::vis::VisState>,
) {
    match node {
        LogNode::Vis { name, value } => {
            let live = resolved.and_then(|r| r.get(name));
            render_vis_row(
                ui,
                name,
                value,
                live.map(|f| f.as_ref()),
                hover_tile,
                selected,
                hovered,
            );
        }
        LogNode::Scope { .. } => {
            render_dump_node(ui, node, path, hover_tile, selected, hovered, resolved);
        }
        LogNode::Msg { .. } => {}
    }
}

/// Declarative classification of a vis row into one of three kinds:
///
/// - `Skip`: emit nothing.
/// - `KeyValue`: `name: <body>` line, non-interactive.
/// - `Selectable`: `name (x,y)` (or just `name`) selectable label that
///   drives the map overlay; an optional preview position is shown on
///   hover.
enum RowKind<'a> {
    Skip,
    KeyValue(KeyValueBody<'a>),
    Selectable { preview: Option<(i32, i32)> },
}

enum KeyValueBody<'a> {
    Scalar(&'a ScalarValue),
    NoneLiteral,
}

fn classify_row<'a>(inline: &'a Tagged, live: Option<&'a crate::vis::VisField>) -> RowKind<'a> {
    use crate::vis::VisField;
    match inline {
        Tagged::Scalar(ScalarValue::Pos(x, y)) => RowKind::Selectable {
            preview: Some((*x, *y)),
        },
        Tagged::Scalar(s) => RowKind::KeyValue(KeyValueBody::Scalar(s)),
        Tagged::Tile(None) | Tagged::Dot { pos: None, .. } => {
            RowKind::KeyValue(KeyValueBody::NoneLiteral)
        }
        Tagged::Tile(Some((x, y)))
        | Tagged::Dot {
            pos: Some((x, y)), ..
        } => RowKind::Selectable {
            preview: Some((*x, *y)),
        },
        Tagged::Tiles(_) | Tagged::Grid { .. } | Tagged::VectorField(_) | Tagged::Path { .. } => {
            RowKind::Selectable { preview: None }
        }
        Tagged::Same => match live {
            Some(VisField::Scalar {
                data: ScalarValue::Pos(x, y),
            }) => RowKind::Selectable {
                preview: Some((*x, *y)),
            },
            Some(VisField::Scalar { data }) => RowKind::KeyValue(KeyValueBody::Scalar(data)),
            Some(VisField::Tile { pos: None } | VisField::Dot { pos: None, .. }) => {
                RowKind::KeyValue(KeyValueBody::NoneLiteral)
            }
            Some(
                VisField::Tile { pos: Some((x, y)) }
                | VisField::Dot {
                    pos: Some((x, y)), ..
                },
            ) => RowKind::Selectable {
                preview: Some((*x, *y)),
            },
            Some(_) => RowKind::Selectable { preview: None },
            None => RowKind::Skip,
        },
    }
}

/// Render a single vis row. Classification drives the layout:
/// scalar values become `name: value` lines; positional values
/// (`Pos`/`Tile`/`Dot`) become selectable labels that drive map
/// overlays and preview the position on hover; other map-renderable
/// kinds (grid / tiles / vectorfield / path) become selectable name
/// labels with no preview position.
fn render_vis_row(
    ui: &mut egui::Ui,
    name: &str,
    inline: &Tagged,
    live: Option<&crate::vis::VisField>,
    hover_tile: &mut Option<(i32, i32)>,
    selected: &mut std::collections::HashSet<String>,
    hovered: &mut Option<String>,
) {
    match classify_row(inline, live) {
        RowKind::Skip => {}
        RowKind::KeyValue(body) => render_key_value_row(ui, name, body, hover_tile),
        RowKind::Selectable { preview } => {
            render_selectable_row(ui, name, preview, hover_tile, selected, hovered);
        }
    }
}

fn render_key_value_row(
    ui: &mut egui::Ui,
    name: &str,
    body: KeyValueBody<'_>,
    hover_tile: &mut Option<(i32, i32)>,
) {
    ui.horizontal(|ui| {
        ui.monospace(
            egui::RichText::new(format!("{name}:")).color(egui::Color32::from_rgb(200, 200, 160)),
        );
        match body {
            KeyValueBody::Scalar(s) => render_scalar_inline(ui, s, hover_tile),
            KeyValueBody::NoneLiteral => {
                ui.monospace("None");
            }
        }
    });
}

fn render_selectable_row(
    ui: &mut egui::Ui,
    name: &str,
    preview: Option<(i32, i32)>,
    hover_tile: &mut Option<(i32, i32)>,
    selected: &mut std::collections::HashSet<String>,
    hovered: &mut Option<String>,
) {
    let is_selected = selected.contains(name);
    let label = match preview {
        Some((x, y)) => format!("{name} ({x},{y})"),
        None => name.to_string(),
    };
    let mut text = egui::RichText::new(label).monospace();
    if is_selected {
        text = text.color(egui::Color32::from_rgb(200, 240, 100)).strong();
    }
    let resp = ui.selectable_label(is_selected, text);
    if resp.hovered() {
        *hovered = Some(name.to_string());
        if let Some(pos) = preview {
            *hover_tile = Some(pos);
        }
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }
    if resp.clicked() {
        if is_selected {
            selected.remove(name);
        } else {
            selected.insert(name.to_string());
        }
    }
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
                let (scroll, shift) = ui.input(|i| {
                    let mut s = 0.0_f32;
                    for event in &i.raw.events {
                        if let egui::Event::MouseWheel { delta, .. } = event {
                            s += delta.y;
                        }
                    }
                    (s, i.modifiers.shift)
                });
                let step = if shift { 10 } else { 1 };
                if scroll > 0.0 {
                    app.step_forward(step);
                } else if scroll < 0.0 {
                    app.step_backward(step);
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
                    app.toggle_playing();
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

                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button("Open").clicked()
                        && let Some(path) = rfd::FileDialog::new()
                            .add_filter("Replay", &["replay26"])
                            .pick_file()
                    {
                        app.load_replay(path);
                    }
                });
            });
        });
}

fn format_entity_info(e: &Entity, cpu_time_us: &HashMap<i32, u32>) -> String {
    use std::fmt::Write;
    let team = match e.team {
        proto::Team::A => "A",
        proto::Team::B => "B",
    };
    let kind_name = entity::label(&e.kind);
    let mut s = format!(
        "{kind_name}\nTeam {team}\nHP: {}/{}\nID: {}",
        e.hp, e.max_hp, e.id
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
        proto::Environment::EnvOreTitanium => "Ti",
        proto::Environment::EnvOreAxionite => "Ax",
    };
    env_name.to_string()
}
