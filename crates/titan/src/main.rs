use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process;
use std::sync::Arc;

use eframe::egui;
use titan_core::{
    BuildCtx, CambcConfig, FilePicker, ModeApp, PickResult, ResponseExt, SpriteConfig, SpriteSet,
};

const FONT: &[u8] = include_bytes!("../assets/cambc/font.ttf");

const SPRITES: SpriteConfig<'_> = SpriteConfig {
    strip_sprites: &[],
    aspect_sprites: &[
        "bridge_gold",
        "bridge_silver",
        "bridge_beam_gold",
        "bridge_beam_silver",
    ],
    rotatable_sprites: &[
        "conveyor_gold",
        "conveyor_silver",
        "armoured_conveyor_gold",
        "armoured_conveyor_silver",
    ],
};

fn find_assets_dir() -> PathBuf {
    let exe = std::env::current_exe().unwrap_or_default();
    let exe_dir = exe.parent().unwrap_or_else(|| Path::new(".")).to_path_buf();
    let candidates = [
        exe_dir.join("../../../crates/titan/assets"),
        exe_dir.join("../../assets"),
        exe_dir.join("../assets"),
        Path::new("pkg/crates/titan/assets").to_path_buf(),
        Path::new("assets").to_path_buf(),
    ];
    candidates
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| Path::new("assets").to_path_buf())
}

fn usage() -> ! {
    eprintln!("usage: titan <mode> [args...]");
    eprintln!();
    eprintln!("modes:");
    eprintln!("    replay [<replay.replay26>]   replay viewer (defaults to cambc.toml)");
    eprintln!("    blueprint <map.map26>        blueprint editor");
    eprintln!("    bugnav [map]                 bug-nav viewer");
    process::exit(1);
}

enum Inputs {
    Replay(titan_replay::Inputs),
    Blueprint(titan_blueprint::Inputs),
    Bugnav(titan_bugnav::Inputs),
}

impl Inputs {
    fn build(self, atlas: Arc<SpriteSet>) -> Box<dyn ModeApp> {
        match self {
            Self::Replay(i) => Box::new(titan_replay::build(atlas, i)),
            Self::Blueprint(i) => Box::new(titan_blueprint::build(atlas, i)),
            Self::Bugnav(i) => Box::new(titan_bugnav::build(atlas, i)),
        }
    }
}

fn parse_cli(mode: &str, args: Vec<OsString>, config: &CambcConfig) -> Result<Inputs, String> {
    match mode {
        "replay" => {
            let mut a = args;
            if a.len() <= 1 {
                a.push(config.replay_path().into_os_string());
            }
            titan_replay::parse_args(a).map(Inputs::Replay)
        }
        "blueprint" => titan_blueprint::parse_args(args).map(Inputs::Blueprint),
        "bugnav" => titan_bugnav::parse_args(args).map(Inputs::Bugnav),
        _ => Err(format!("unknown mode: {mode}")),
    }
}

fn parse_replay_path(path: PathBuf) -> Result<Inputs, String> {
    titan_replay::parse_args(vec![OsString::new(), path.into()]).map(Inputs::Replay)
}

fn parse_blueprint_path(path: PathBuf) -> Result<Inputs, String> {
    titan_blueprint::parse_args(vec![OsString::new(), path.into()]).map(Inputs::Blueprint)
}

fn parse_bugnav_default() -> Result<Inputs, String> {
    titan_bugnav::parse_args(vec![OsString::new()]).map(Inputs::Bugnav)
}

/// What the picker should do once the user picks a path: switch to a
/// new mode, or load a file in the current one.
enum PickAction {
    SwitchMode(fn(PathBuf) -> Result<Inputs, String>),
    OpenInCurrent,
}

struct PendingPick {
    picker: FilePicker,
    action: PickAction,
}

struct TitanApp {
    inner: Box<dyn ModeApp>,
    sprites: Arc<SpriteSet>,
    config: CambcConfig,
    pending: Option<PendingPick>,
    error: Option<String>,
}

impl TitanApp {
    fn new(inner: Box<dyn ModeApp>, sprites: Arc<SpriteSet>, config: CambcConfig) -> Self {
        Self {
            inner,
            sprites,
            config,
            pending: None,
            error: None,
        }
    }

    fn open_in_current(&mut self) {
        let extensions: Vec<&str> = self.inner.pick_extensions().to_vec();
        let dir = self.inner.pick_default_dir(&self.config);
        let title = format!("Open {}", self.inner.name());
        self.pending = Some(PendingPick {
            picker: FilePicker::new(title, dir, &extensions),
            action: PickAction::OpenInCurrent,
        });
    }

    fn switch_mode(
        &mut self,
        title: &str,
        start_dir: PathBuf,
        exts: &[&str],
        parser: fn(PathBuf) -> Result<Inputs, String>,
    ) {
        self.pending = Some(PendingPick {
            picker: FilePicker::new(title, start_dir, exts),
            action: PickAction::SwitchMode(parser),
        });
    }

    fn handle_global_keys(&mut self, ctx: &egui::Context) {
        let (ctrl, shift, key_o, key_s, key_z) = ctx.input(|i| {
            (
                i.modifiers.ctrl,
                i.modifiers.shift,
                i.key_pressed(egui::Key::O),
                i.key_pressed(egui::Key::S),
                i.key_pressed(egui::Key::Z),
            )
        });
        if ctrl && key_o {
            self.open_in_current();
        }
        if ctrl && key_s && self.inner.can_save() {
            self.inner.save_file();
        }
        if ctrl && key_z {
            if shift {
                if self.inner.can_redo() {
                    self.inner.redo();
                }
            } else if self.inner.can_undo() {
                self.inner.undo();
            }
        }
    }

    fn toolbar(&mut self, ui: &mut egui::Ui) {
        let mut switch_inputs: Option<Inputs> = None;
        egui::Panel::top("titan-toolbar")
            .frame(egui::Frame::menu(ui.style()).inner_margin(egui::Margin {
                left: 6,
                right: 6,
                top: 2,
                bottom: 2,
            }))
            .show_inside(ui, |ui| {
                egui::MenuBar::new().ui(ui, |ui| {
                    ui.menu_button("File", |ui| {
                        if ui.button("Open…       Ctrl+O").clickable().clicked() {
                            self.open_in_current();
                            ui.close();
                        }
                        ui.separator();
                        let save_label = "Save        Ctrl+S";
                        ui.add_enabled_ui(self.inner.can_save(), |ui| {
                            if ui.button(save_label).clickable().clicked() {
                                self.inner.save_file();
                                ui.close();
                            }
                        });
                    });

                    ui.menu_button("Edit", |ui| {
                        ui.add_enabled_ui(self.inner.can_undo(), |ui| {
                            if ui.button("Undo        Ctrl+Z").clickable().clicked() {
                                self.inner.undo();
                                ui.close();
                            }
                        });
                        ui.add_enabled_ui(self.inner.can_redo(), |ui| {
                            if ui.button("Redo  Ctrl+Shift+Z").clickable().clicked() {
                                self.inner.redo();
                                ui.close();
                            }
                        });
                    });

                    ui.menu_button("Mode", |ui| {
                        if ui.button("Replay…").clickable().clicked() {
                            self.switch_mode(
                                "Open replay",
                                self.config.project_root.clone(),
                                &["replay26"],
                                parse_replay_path,
                            );
                            ui.close();
                        }
                        if ui.button("Blueprint…").clickable().clicked() {
                            self.switch_mode(
                                "Open blueprint map",
                                self.config.maps_path(),
                                &["map26"],
                                parse_blueprint_path,
                            );
                            ui.close();
                        }
                        if ui.button("Bug-nav").clickable().clicked() {
                            match parse_bugnav_default() {
                                Ok(i) => switch_inputs = Some(i),
                                Err(e) => self.error = Some(e),
                            }
                            ui.close();
                        }
                    });

                    ui.separator();
                    if let Some(path) = self.inner.current_path() {
                        ui.weak(path.display().to_string());
                    }
                    if let Some(err) = &self.error {
                        ui.separator();
                        ui.colored_label(titan_core::style::COLOR_ERROR, err);
                    }
                });
            });
        if let Some(inputs) = switch_inputs {
            self.inner = inputs.build(Arc::clone(&self.sprites));
            self.error = None;
        }
    }

    fn drive_picker(&mut self, ctx: &egui::Context) {
        let Some(pending) = self.pending.as_mut() else {
            return;
        };
        match pending.picker.show(ctx) {
            PickResult::Pending => {}
            PickResult::Cancelled => {
                self.pending = None;
            }
            PickResult::Picked(path) => {
                let action = std::mem::replace(&mut pending.action, PickAction::OpenInCurrent);
                self.pending = None;
                match action {
                    PickAction::SwitchMode(parser) => match parser(path) {
                        Ok(inputs) => {
                            self.inner = inputs.build(Arc::clone(&self.sprites));
                            self.error = None;
                        }
                        Err(e) => self.error = Some(e),
                    },
                    PickAction::OpenInCurrent => {
                        if let Err(e) = self.inner.open_path(path) {
                            self.error = Some(e);
                        }
                    }
                }
            }
        }
    }
}

impl eframe::App for TitanApp {
    fn ui(&mut self, ui: &mut egui::Ui, frame: &mut eframe::Frame) {
        self.handle_global_keys(&ui.ctx().clone());
        self.toolbar(ui);
        self.drive_picker(&ui.ctx().clone());
        self.inner.ui(ui, frame);
    }
}

fn main() -> eframe::Result {
    let mut args: Vec<OsString> = std::env::args_os().collect();
    let mode = args
        .get(1)
        .map_or_else(|| usage(), |s| s.to_string_lossy().into_owned());

    args.remove(0);

    let config = titan_core::find_config();

    let inputs = parse_cli(&mode, args, &config).unwrap_or_else(|e| {
        eprintln!("{e}");
        process::exit(1);
    });

    let assets_dir = find_assets_dir();

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 800.0])
            .with_maximized(true)
            .with_title("titan"),
        ..Default::default()
    };

    eframe::run_native(
        "titan",
        options,
        Box::new(move |cc| {
            titan_core::style::apply_titan_theme(&cc.egui_ctx, FONT);
            let bc = BuildCtx::from_creation(cc);
            let render_state = bc.render_state.expect("wgpu render state");
            let sprites = Arc::new(SpriteSet::load(render_state, &assets_dir, SPRITES));
            let inner = inputs.build(Arc::clone(&sprites));
            Ok(Box::new(TitanApp::new(inner, sprites, config)))
        }),
    )
}
