//! In-app file picker. Renders an egui modal listing files in a
//! directory, filtered by extension, with up/into-dir navigation. Avoids
//! the multi-second `xdg-desktop-portal` round-trip that `rfd` triggers
//! on Linux.

use std::path::{Path, PathBuf};

use eframe::egui;

use crate::ResponseExt;

#[derive(Clone, Copy, PartialEq, Eq)]
enum EntryKind {
    Dir,
    File,
}

struct Entry {
    name: String,
    path: PathBuf,
    kind: EntryKind,
}

pub struct FilePicker {
    title: String,
    current_dir: PathBuf,
    /// Lowercase extensions without the leading dot.
    extensions: Vec<String>,
    entries: Vec<Entry>,
    cancelled: bool,
}

pub enum PickResult {
    Pending,
    Cancelled,
    Picked(PathBuf),
}

impl FilePicker {
    /// Create a picker rooted at `start_dir`, filtering for files with
    /// any of the given extensions (case-insensitive, no leading dot).
    #[must_use]
    pub fn new(title: impl Into<String>, start_dir: PathBuf, extensions: &[&str]) -> Self {
        let extensions: Vec<String> = extensions.iter().map(|e| e.to_lowercase()).collect();
        let mut p = Self {
            title: title.into(),
            current_dir: canonicalize_or(start_dir),
            extensions,
            entries: Vec::new(),
            cancelled: false,
        };
        p.refresh();
        p
    }

    fn refresh(&mut self) {
        self.entries.clear();
        let Ok(rd) = std::fs::read_dir(&self.current_dir) else {
            return;
        };
        for entry in rd.flatten() {
            let path = entry.path();
            let name = entry.file_name().to_string_lossy().into_owned();
            let kind = if path.is_dir() {
                EntryKind::Dir
            } else if self.matches_filter(&path) {
                EntryKind::File
            } else {
                continue;
            };
            self.entries.push(Entry { name, path, kind });
        }
        self.entries.sort_by(|a, b| {
            (a.kind == EntryKind::File, &a.name).cmp(&(b.kind == EntryKind::File, &b.name))
        });
    }

    fn matches_filter(&self, path: &Path) -> bool {
        if self.extensions.is_empty() {
            return true;
        }
        path.extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| self.extensions.iter().any(|x| x == &e.to_lowercase()))
    }

    fn navigate(&mut self, target: PathBuf) {
        self.current_dir = canonicalize_or(target);
        self.refresh();
    }

    /// Renders the picker as a true `egui::Modal` (with input-blocking
    /// backdrop and ESC-to-dismiss). Returns `Picked(path)` once the
    /// user clicks a file, `Cancelled` if they hit Cancel / ESC /
    /// backdrop, or `Pending` while it's still open.
    pub fn show(&mut self, ctx: &egui::Context) -> PickResult {
        let mut chosen: Option<PathBuf> = None;
        let mut nav: Option<PathBuf> = None;
        let mut cancel_clicked = false;

        let response =
            egui::Modal::new(egui::Id::new(("titan-file-picker", &self.title))).show(ctx, |ui| {
                ui.set_min_size(egui::vec2(520.0, 420.0));
                ui.heading(&self.title);
                ui.separator();
                ui.horizontal(|ui| {
                    if ui.button("⬆ Up").clickable().clicked()
                        && let Some(parent) = self.current_dir.parent()
                    {
                        nav = Some(parent.to_path_buf());
                    }
                    ui.monospace(self.current_dir.display().to_string());
                });
                ui.separator();

                egui::ScrollArea::vertical()
                    .auto_shrink([false; 2])
                    .max_height(320.0)
                    .show(ui, |ui| {
                        for entry in &self.entries {
                            let label = match entry.kind {
                                EntryKind::Dir => format!("📁 {}", entry.name),
                                EntryKind::File => format!("   {}", entry.name),
                            };
                            let resp = ui.selectable_label(false, label).clickable();
                            if resp.clicked() {
                                match entry.kind {
                                    EntryKind::Dir => nav = Some(entry.path.clone()),
                                    EntryKind::File => chosen = Some(entry.path.clone()),
                                }
                            }
                        }
                    });

                ui.separator();
                ui.horizontal(|ui| {
                    if ui.button("Cancel").clickable().clicked() {
                        cancel_clicked = true;
                    }
                });
            });

        if let Some(target) = nav {
            self.navigate(target);
        }
        if let Some(path) = chosen {
            return PickResult::Picked(path);
        }
        if cancel_clicked || response.should_close() {
            self.cancelled = true;
            return PickResult::Cancelled;
        }
        PickResult::Pending
    }
}

fn canonicalize_or(p: PathBuf) -> PathBuf {
    p.canonicalize().unwrap_or(p)
}
