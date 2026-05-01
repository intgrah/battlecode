use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process;
use std::sync::Arc;

use clap::{CommandFactory, Parser, Subcommand};
use clap_complete::Shell;
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
        exe_dir.join("../../crates/titan/assets"),
        exe_dir.join("../../assets"),
        exe_dir.join("../assets"),
        Path::new("crates/titan/assets").to_path_buf(),
        Path::new("assets").to_path_buf(),
    ];
    candidates
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| Path::new("assets").to_path_buf())
}

#[derive(Parser)]
#[command(
    name = "titan",
    version,
    about = "Cambridge Battlecode visualisation, planning, and pathfinding tools"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Replay viewer. Path defaults to `cambc.toml`'s `replay` field.
    Replay { replay: Option<PathBuf> },
    /// Blueprint editor.
    Blueprint { map: PathBuf },
    /// Bug-navigation viewer. Map path defaults to the first map in
    /// `cambc.toml`'s `maps_dir`.
    Bugnav { map: Option<PathBuf> },
    /// Opening-book editor. Accepts a map path (`.map26`) for a
    /// fresh book or an existing `.opening` file to edit.
    Opening { path: PathBuf },
    /// Print a shell-completion script. Pipe into the appropriate
    /// completions file, e.g.
    /// `titan completions fish > ~/.config/fish/completions/titan.fish`.
    Completions {
        /// One of: bash, zsh, fish, powershell, elvish.
        shell: Shell,
    },
    /// Internal: list maps from `cambc.toml`'s `maps_dir`. Used by
    /// shell completions.
    #[command(name = "_list-maps", hide = true)]
    ListMaps,
    /// Internal: list `*.replay26` files in the project root. Used by
    /// shell completions.
    #[command(name = "_list-replays", hide = true)]
    ListReplays,
    /// Internal: list `*.opening` files in the project root. Used by
    /// shell completions for the `opening` subcommand.
    #[command(name = "_list-openings", hide = true)]
    ListOpenings,
}

enum Inputs {
    Replay(titan_replay::Inputs),
    Blueprint(titan_blueprint::Inputs),
    Bugnav(titan_bugnav::Inputs),
    Opening(titan_opening::Inputs),
}

impl Inputs {
    fn build(self, atlas: Arc<SpriteSet>) -> Box<dyn ModeApp> {
        match self {
            Self::Replay(i) => Box::new(titan_replay::build(atlas, i)),
            Self::Blueprint(i) => Box::new(titan_blueprint::build(atlas, i)),
            Self::Bugnav(i) => Box::new(titan_bugnav::build(atlas, i)),
            Self::Opening(i) => Box::new(titan_opening::build(atlas, i)),
        }
    }
}

fn parse_command(command: Command, config: &CambcConfig) -> Result<Inputs, String> {
    match command {
        Command::Replay { replay } => {
            let path = match replay {
                Some(p) => resolve_replay(&p, config)?,
                None => config.replay_path(),
            };
            titan_replay::parse_args(vec![OsString::new(), path.into_os_string()])
                .map(Inputs::Replay)
        }
        Command::Blueprint { map } => {
            let resolved = resolve_map(&map, config)?;
            titan_blueprint::parse_args(vec![OsString::new(), resolved.into_os_string()])
                .map(Inputs::Blueprint)
        }
        Command::Bugnav { map } => {
            let mut args = vec![OsString::new()];
            if let Some(p) = map {
                args.push(resolve_map(&p, config)?.into_os_string());
            }
            titan_bugnav::parse_args(args).map(Inputs::Bugnav)
        }
        Command::Opening { path } => {
            // Accept an existing `.opening` (load it) or a `.map26`
            // (start a fresh book on that map). For `.opening` we
            // pass through; for everything else we resolve via the
            // map-name shortcut so `titan opening foo` works the
            // same way as `titan blueprint foo`.
            let resolved =
                if path.extension().and_then(|s| s.to_str()) == Some("opening") && path.is_file() {
                    path.canonicalize()
                        .map_err(|e| format!("{}: {e}", path.display()))?
                } else {
                    resolve_map(&path, config)?
                };
            titan_opening::parse_args(vec![OsString::new(), resolved.into_os_string()])
                .map(Inputs::Opening)
        }
        Command::Completions { .. }
        | Command::ListMaps
        | Command::ListReplays
        | Command::ListOpenings => {
            unreachable!("non-app commands handled in main")
        }
    }
}

/// Resolve a map argument to an absolute `.map26` file. Mirrors
/// `cambc-libre`'s logic: tries `path`, `<maps_dir>/<path>`,
/// `<path>.map26`, `<maps_dir>/<path>.map26`.
fn resolve_map(path: &Path, config: &CambcConfig) -> Result<PathBuf, String> {
    let mut candidates: Vec<PathBuf> = vec![path.to_path_buf()];
    if !path.is_absolute() {
        candidates.push(config.maps_path().join(path));
    }
    let bare = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
    if !bare.ends_with(".map26") {
        let with_ext = format!("{}.map26", path.display());
        candidates.push(PathBuf::from(&with_ext));
        if !path.is_absolute() {
            candidates.push(config.maps_path().join(format!("{bare}.map26")));
        }
    }
    for p in &candidates {
        if p.is_file() {
            return p
                .canonicalize()
                .map_err(|e| format!("{}: {e}", p.display()));
        }
    }
    Err(format!("map not found: {}", path.display()))
}

/// Resolve a replay argument. Tries `path`, `<project_root>/<path>`,
/// `<path>.replay26`, `<project_root>/<path>.replay26`.
fn resolve_replay(path: &Path, config: &CambcConfig) -> Result<PathBuf, String> {
    let mut candidates: Vec<PathBuf> = vec![path.to_path_buf()];
    if !path.is_absolute() {
        candidates.push(config.project_root.join(path));
    }
    let bare = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
    if !bare.ends_with(".replay26") {
        candidates.push(PathBuf::from(format!("{}.replay26", path.display())));
        if !path.is_absolute() {
            candidates.push(config.project_root.join(format!("{bare}.replay26")));
        }
    }
    for p in &candidates {
        if p.is_file() {
            return p
                .canonicalize()
                .map_err(|e| format!("{}: {e}", p.display()));
        }
    }
    Err(format!("replay not found: {}", path.display()))
}

/// Print the *stem* of every `.map26` directly under `maps_dir`. Used
/// by shell completions so the user can complete bare names.
fn list_maps(config: &CambcConfig) {
    let dir = config.maps_path();
    let Ok(entries) = std::fs::read_dir(&dir) else {
        return;
    };
    let mut names: Vec<String> = entries
        .flatten()
        .filter_map(|e| {
            let p = e.path();
            if p.extension().and_then(|s| s.to_str()) == Some("map26") {
                p.file_stem().map(|n| n.to_string_lossy().into_owned())
            } else {
                None
            }
        })
        .collect();
    names.sort();
    for n in names {
        println!("{n}");
    }
}

/// Print every `*.opening` file path under the project root,
/// recursively. Openings have no fixed home — they typically live
/// next to the map they reference, which can be in any subdirectory
/// — so the completion suggests full paths rather than bare stems.
fn list_openings(config: &CambcConfig) {
    let mut paths: Vec<String> = Vec::new();
    walk_for_extension(&config.project_root, "opening", &mut paths);
    paths.sort();
    for p in paths {
        println!("{p}");
    }
}

fn walk_for_extension(dir: &Path, ext: &str, out: &mut Vec<String>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for e in entries.flatten() {
        let p = e.path();
        if p.is_dir() {
            // Skip target / .git / node_modules — common big dirs
            // that won't have user-authored openings.
            let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("");
            if matches!(name, "target" | ".git" | "node_modules" | ".venv") {
                continue;
            }
            walk_for_extension(&p, ext, out);
        } else if p.extension().and_then(|s| s.to_str()) == Some(ext) {
            if let Some(s) = p.to_str() {
                out.push(s.to_string());
            }
        }
    }
}

/// Print the stem of every `*.replay26` in the project root.
fn list_replays(config: &CambcConfig) {
    let Ok(entries) = std::fs::read_dir(&config.project_root) else {
        return;
    };
    let mut names: Vec<String> = entries
        .flatten()
        .filter_map(|e| {
            let p = e.path();
            if p.extension().and_then(|s| s.to_str()) == Some("replay26") {
                p.file_stem().map(|n| n.to_string_lossy().into_owned())
            } else {
                None
            }
        })
        .collect();
    names.sort();
    for n in names {
        println!("{n}");
    }
}

/// Fish-specific tail appended after `clap_complete::generate` so that
/// `replay`'s positional gets dynamic completion from project `*.replay26`
/// files, and `blueprint`/`bugnav`/`opening`'s positional gets the
/// `maps_dir` map list.
const FISH_DYNAMIC_TAIL: &str = r#"
function __titan_pos
    set -l cmd (commandline -opc)
    set -l n 0
    for tok in $cmd
        switch $tok
            case 'titan' '*/titan' 'replay' 'blueprint' 'bugnav' 'opening'
                continue
            case '--*' '-*'
                continue
            case '*'
                set n (math $n + 1)
        end
    end
    echo $n
end

complete -c titan -n "__fish_titan_using_subcommand replay; and test (__titan_pos) -le 1" -f -a "(titan _list-replays)"
complete -c titan -n "__fish_titan_using_subcommand blueprint; and test (__titan_pos) -le 1" -f -a "(titan _list-maps)"
complete -c titan -n "__fish_titan_using_subcommand bugnav; and test (__titan_pos) -le 1" -f -a "(titan _list-maps)"
complete -c titan -n "__fish_titan_using_subcommand opening; and test (__titan_pos) -le 1" -f -a "(titan _list-openings)"
complete -c titan -n "__fish_titan_using_subcommand opening; and test (__titan_pos) -le 1" -f -a "(titan _list-maps)"
"#;

fn parse_replay_path(path: PathBuf) -> Result<Inputs, String> {
    titan_replay::parse_args(vec![OsString::new(), path.into()]).map(Inputs::Replay)
}

fn parse_blueprint_path(path: PathBuf) -> Result<Inputs, String> {
    titan_blueprint::parse_args(vec![OsString::new(), path.into()]).map(Inputs::Blueprint)
}

fn parse_opening_path(path: PathBuf) -> Result<Inputs, String> {
    titan_opening::parse_args(vec![OsString::new(), path.into()]).map(Inputs::Opening)
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
                        if ui.button("Opening…").clickable().clicked() {
                            self.switch_mode(
                                "Open map for opening",
                                self.config.maps_path(),
                                &["map26"],
                                parse_opening_path,
                            );
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
    let cli = Cli::parse();
    let config = titan_core::find_config();

    match cli.command {
        Command::Completions { shell } => {
            let mut cmd = Cli::command();
            let bin_name = cmd.get_name().to_string();
            clap_complete::generate(shell, &mut cmd, bin_name, &mut std::io::stdout());
            if shell == Shell::Fish {
                print!("{FISH_DYNAMIC_TAIL}");
            }
            std::process::exit(0);
        }
        Command::ListMaps => {
            list_maps(&config);
            std::process::exit(0);
        }
        Command::ListReplays => {
            list_replays(&config);
            std::process::exit(0);
        }
        Command::ListOpenings => {
            list_openings(&config);
            std::process::exit(0);
        }
        _ => {}
    }

    let inputs = parse_command(cli.command, &config).unwrap_or_else(|e| {
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
