//! Trait every titan mode implements so the top toolbar can dispatch
//! generic actions (open, save, undo, redo) without knowing the
//! concrete app type.

use std::path::{Path, PathBuf};

use crate::config::CambcConfig;

pub trait ModeApp: eframe::App {
    /// Short identifier, e.g. "replay", "blueprint", "bugnav". Used for
    /// dialog titles and the path tail shown in the toolbar.
    fn name(&self) -> &'static str;

    /// Path of the file currently loaded, if any. Shown in the toolbar.
    fn current_path(&self) -> Option<&Path> {
        None
    }

    /// Extensions (without leading dot) the in-mode file picker should
    /// filter on.
    fn pick_extensions(&self) -> &'static [&'static str];

    /// Where the in-mode file picker should start. Implementations
    /// usually pull this off [`CambcConfig`].
    fn pick_default_dir(&self, config: &CambcConfig) -> PathBuf;

    /// Open `path` *in the same mode*, replacing the loaded file.
    fn open_path(&mut self, path: PathBuf) -> Result<(), String>;

    fn can_save(&self) -> bool {
        false
    }
    /// Persist the current document (renamed from `save` to avoid
    /// clashing with `eframe::App::save(&mut self, &mut dyn Storage)`).
    fn save_file(&mut self) {}

    fn can_undo(&self) -> bool {
        false
    }
    fn undo(&mut self) {}

    fn can_redo(&self) -> bool {
        false
    }
    fn redo(&mut self) {}
}
