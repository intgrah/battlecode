use eframe::egui;

/// Adds a `.clickable()` chain method to `egui::Response` that flips the
/// hover cursor to a pointing hand. Use on every interactive widget so
/// the cursor signals "this is clickable" consistently across modes.
pub trait ResponseExt {
    /// Set `CursorIcon::PointingHand` while hovered. Returns `self`
    /// unchanged so callers can chain `.clicked()` after.
    fn clickable(self) -> Self;
}

impl ResponseExt for egui::Response {
    fn clickable(self) -> Self {
        if self.hovered() {
            self.ctx.set_cursor_icon(egui::CursorIcon::PointingHand);
        }
        self
    }
}
