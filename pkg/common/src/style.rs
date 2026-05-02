use eframe::egui;
use egui::{Color32, FontData, FontDefinitions, FontFamily};

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
