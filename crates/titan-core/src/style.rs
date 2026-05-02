use eframe::egui;
use egui::{Color32, FontData, FontDefinitions, FontFamily, FontId, TextStyle, Vec2};

/// Semantic colour slots — one source of truth for accents. All callers
/// route through here instead of hardcoding `Color32::from_rgb(...)`.
pub const COLOR_KEY: Color32 = Color32::from_rgb(0xc8, 0xc8, 0xa0); // key/label tint
pub const COLOR_INFO: Color32 = Color32::from_rgb(0x88, 0xb8, 0xff); // info accents
pub const COLOR_WARN: Color32 = Color32::from_rgb(0xe0, 0x80, 0x40); // warnings
pub const COLOR_ERROR: Color32 = Color32::from_rgb(0xe0, 0x60, 0x60); // errors / failures

/// Shared `Frame` for side / top / bottom panels — consistent margin
/// across every titan mode.
#[must_use]
pub fn panel_frame(style: &egui::Style) -> egui::Frame {
    egui::Frame::side_top_panel(style).inner_margin(8.0)
}

/// In-panel section title (smaller than `ui.heading`, used for
/// sub-sections inside a sidebar so 18pt headings don't dominate).
pub fn section_title(ui: &mut egui::Ui, text: &str) {
    ui.label(egui::RichText::new(text).strong());
}

pub fn apply_dark_text(ctx: &egui::Context) {
    let mut style = (*ctx.global_style()).clone();
    style.visuals.override_text_color = Some(Color32::from_rgb(0xe0, 0xe0, 0xe0));
    style.visuals.widgets.noninteractive.fg_stroke.color = Color32::from_rgb(0xe0, 0xe0, 0xe0);
    style.visuals.widgets.inactive.fg_stroke.color = Color32::from_rgb(0xd0, 0xd0, 0xd0);
    ctx.set_global_style(style);
    ctx.tessellation_options_mut(|opts| {
        opts.feathering = true;
        opts.feathering_size_in_pixels = 1.5;
    });
}

pub fn install_mono_font(ctx: &egui::Context, font: &'static [u8]) {
    let mut fonts = FontDefinitions::default();
    fonts
        .font_data
        .insert("mono".into(), FontData::from_static(font).into());
    fonts
        .families
        .entry(FontFamily::Proportional)
        .or_default()
        .insert(0, "mono".into());
    fonts
        .families
        .entry(FontFamily::Monospace)
        .or_default()
        .insert(0, "mono".into());
    ctx.set_fonts(fonts);
}

/// Single coherent theme applied once at startup. All titan modes
/// inherit this; per-mode `App::new` does not touch `Context` style.
///
/// This sets shared chrome — colours, spacing, text sizes — so the
/// three modes look like the same app.
pub fn apply_titan_theme(ctx: &egui::Context, font: &'static [u8]) {
    install_mono_font(ctx, font);

    let mut style = (*ctx.global_style()).clone();

    // Text colours.
    style.visuals.override_text_color = Some(Color32::from_rgb(0xe4, 0xe4, 0xe4));
    style.visuals.widgets.noninteractive.fg_stroke.color = Color32::from_rgb(0xe4, 0xe4, 0xe4);
    style.visuals.widgets.inactive.fg_stroke.color = Color32::from_rgb(0xc8, 0xc8, 0xc8);

    // Panel + window background. Coordinated with `titan_core::map::BG_COLOR`
    // so the map area blends with the chrome.
    let panel_bg = Color32::from_rgb(0x14, 0x16, 0x1a);
    let window_bg = Color32::from_rgb(0x18, 0x1a, 0x1f);
    style.visuals.panel_fill = panel_bg;
    style.visuals.window_fill = window_bg;
    style.visuals.extreme_bg_color = Color32::from_rgb(0x0c, 0x0e, 0x12);

    // Widget surfaces — buttons, frames, dropdowns. Subtle.
    style.visuals.widgets.noninteractive.bg_fill = Color32::from_rgb(0x20, 0x23, 0x29);
    style.visuals.widgets.noninteractive.weak_bg_fill = Color32::from_rgb(0x1a, 0x1d, 0x22);
    style.visuals.widgets.inactive.bg_fill = Color32::from_rgb(0x26, 0x2a, 0x32);
    style.visuals.widgets.inactive.weak_bg_fill = Color32::from_rgb(0x1f, 0x22, 0x28);
    style.visuals.widgets.hovered.bg_fill = Color32::from_rgb(0x33, 0x39, 0x44);
    style.visuals.widgets.hovered.weak_bg_fill = Color32::from_rgb(0x2a, 0x2f, 0x39);
    style.visuals.widgets.active.bg_fill = Color32::from_rgb(0x44, 0x4c, 0x5a);
    style.visuals.widgets.active.weak_bg_fill = Color32::from_rgb(0x36, 0x3c, 0x48);

    // Selection — scrubber handle, list selection, focused tile.
    style.visuals.selection.bg_fill = Color32::from_rgb(0x4a, 0x6e, 0xa8);
    style.visuals.selection.stroke.color = Color32::from_rgb(0x9c, 0xc0, 0xff);

    // Spacing.
    style.spacing.item_spacing = Vec2::new(6.0, 4.0);
    style.spacing.button_padding = Vec2::new(8.0, 4.0);
    style.spacing.menu_margin = egui::Margin::same(6);
    style.spacing.indent = 12.0;

    // Text sizes — give headings real hierarchy.
    style
        .text_styles
        .insert(TextStyle::Heading, FontId::proportional(18.0));
    style
        .text_styles
        .insert(TextStyle::Body, FontId::proportional(13.0));
    style
        .text_styles
        .insert(TextStyle::Button, FontId::proportional(13.0));
    style
        .text_styles
        .insert(TextStyle::Small, FontId::proportional(11.0));
    style
        .text_styles
        .insert(TextStyle::Monospace, FontId::monospace(12.0));

    ctx.set_global_style(style);
    ctx.tessellation_options_mut(|opts| {
        opts.feathering = true;
        opts.feathering_size_in_pixels = 1.5;
    });
}
