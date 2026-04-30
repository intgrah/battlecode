use eframe::{egui, egui_wgpu};

/// Subset of `eframe::CreationContext` that an `App` actually needs.
/// Lets apps be constructed mid-lifecycle (e.g. when switching modes
/// inside the unified titan binary), not only at startup.
pub struct BuildCtx<'a> {
    pub egui_ctx: &'a egui::Context,
    pub render_state: Option<&'a egui_wgpu::RenderState>,
}

impl<'a> BuildCtx<'a> {
    #[must_use]
    pub const fn from_creation(cc: &'a eframe::CreationContext<'a>) -> Self {
        Self {
            egui_ctx: &cc.egui_ctx,
            render_state: cc.wgpu_render_state.as_ref(),
        }
    }

    #[must_use]
    pub fn from_frame(ctx: &'a egui::Context, frame: &'a eframe::Frame) -> Self {
        Self {
            egui_ctx: ctx,
            render_state: frame.wgpu_render_state(),
        }
    }
}
