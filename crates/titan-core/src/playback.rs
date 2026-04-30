//! Shared bottom-strip playback controls — progress bar, transport
//! buttons, speed +/-, position counter.
//!
//! Both the replay viewer and the bug-nav viewer use this so the chrome
//! is identical. Apps implement [`Playback`] on their `App` struct.

use eframe::egui;
use egui::Rect;

use crate::ResponseExt;
use crate::style::panel_frame;

pub const SPEED_MIN: i32 = 0;
pub const SPEED_MAX: i32 = 8;

/// Convert a discrete speed level (0..=8) to its multiplier (1..=256).
#[must_use]
pub const fn speed_multiplier(level: i32) -> u32 {
    let clamped = if level < SPEED_MIN {
        SPEED_MIN
    } else if level > SPEED_MAX {
        SPEED_MAX
    } else {
        level
    };
    1u32 << clamped as u32
}

#[must_use]
pub fn speed_label(level: i32) -> String {
    format!("{}x", speed_multiplier(level))
}

/// Apps drive the shared scrubber by implementing this. All methods
/// take `&mut self` because some implementations may rebuild internal
/// state on seek / reset.
pub trait Playback {
    fn position(&self) -> usize;
    fn total(&self) -> usize;
    fn playing(&self) -> bool;
    fn toggle_play(&mut self);
    fn step_forward(&mut self, n: usize);
    fn step_back(&mut self, n: usize);
    fn seek(&mut self, position: usize);

    fn speed(&self) -> i32;
    fn set_speed(&mut self, speed: i32);

    /// `false` for unidirectional state machines (e.g. pathfinders);
    /// the back button is hidden and the bar is read-only.
    fn supports_step_back(&self) -> bool {
        true
    }

    /// `false` if seeking the bar to an arbitrary position is unsupported
    /// (e.g. pathfinder algorithms). Bar is still drawn for progress
    /// display but click-and-drag does nothing.
    fn supports_seek(&self) -> bool {
        true
    }
}

/// Renders the bottom playback panel for the given app. `right_extra`
/// is invoked inside the controls row, right-aligned, for app-specific
/// trailing buttons (e.g. the replay viewer's "Open" file picker).
pub fn render_playback_panel(
    ui: &mut egui::Ui,
    app: &mut dyn Playback,
    right_extra: impl FnOnce(&mut egui::Ui),
) {
    egui::Panel::bottom("playback")
        .exact_size(64.0)
        .resizable(false)
        .frame(panel_frame(ui.style()))
        .show_inside(ui, |ui| {
            render_progress_bar(ui, app);
            ui.add_space(4.0);
            render_transport(ui, app, right_extra);
        });
}

fn render_progress_bar(ui: &mut egui::Ui, app: &mut dyn Playback) {
    ui.add_space(2.0);
    let total = app.total().max(1);
    let position = app.position().min(total);
    let frac = position as f32 / total as f32;

    let desired = egui::vec2(ui.available_width(), 20.0);
    let sense = if app.supports_seek() {
        egui::Sense::click_and_drag()
    } else {
        egui::Sense::hover()
    };
    let (response, painter) = ui.allocate_painter(desired, sense);
    let rect = response.rect;

    if app.supports_seek() && response.hovered() {
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }

    painter.rect_filled(rect, 4.0, ui.visuals().extreme_bg_color);
    let fill_rect = Rect::from_min_max(
        rect.left_top(),
        egui::pos2(rect.width().mul_add(frac, rect.left()), rect.bottom()),
    );
    painter.rect_filled(fill_rect, 4.0, ui.visuals().selection.bg_fill);

    if app.supports_seek()
        && (response.clicked() || response.dragged())
        && let Some(pos) = response.interact_pointer_pos()
    {
        let f = ((pos.x - rect.left()) / rect.width()).clamp(0.0, 1.0);
        app.seek((f * app.total() as f32) as usize);
    }

    if response.hovered() {
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
        } else if scroll < 0.0 && app.supports_step_back() {
            app.step_back(step);
        }
    }
}

fn render_transport(
    ui: &mut egui::Ui,
    app: &mut dyn Playback,
    right_extra: impl FnOnce(&mut egui::Ui),
) {
    ui.horizontal(|ui| {
        let icon_size = 18.0;

        if app.supports_step_back() && icon_button(ui, "\u{F048}", icon_size).clicked() {
            app.step_back(1);
        }

        let play_icon = if app.playing() {
            "\u{F04C}"
        } else {
            "\u{F04B}"
        };
        if icon_button(ui, play_icon, icon_size).clicked() {
            app.toggle_play();
        }

        if icon_button(ui, "\u{F051}", icon_size).clicked() {
            app.step_forward(1);
        }

        ui.add_space(12.0);

        let speed = app.speed();
        ui.add_enabled_ui(speed > SPEED_MIN, |ui| {
            if icon_button(ui, "\u{F049}", icon_size).clicked() {
                app.set_speed((speed - 1).max(SPEED_MIN));
            }
        });

        ui.label(egui::RichText::new(speed_label(speed)).strong());

        ui.add_enabled_ui(speed < SPEED_MAX, |ui| {
            if icon_button(ui, "\u{F050}", icon_size).clicked() {
                app.set_speed((speed + 1).min(SPEED_MAX));
            }
        });

        ui.add_space(12.0);
        ui.label(
            egui::RichText::new(format!("{}/{}", app.position(), app.total().max(1))).strong(),
        );

        ui.with_layout(
            egui::Layout::right_to_left(egui::Align::Center),
            right_extra,
        );
    });
}

fn icon_button(ui: &mut egui::Ui, icon: &str, size: f32) -> egui::Response {
    let text = egui::RichText::new(icon).size(size);
    let btn = egui::Button::new(text).frame(false);
    ui.add(btn).clickable()
}
