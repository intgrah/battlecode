use std::fs;
use std::path::{Path, PathBuf};

use clap::{Parser, Subcommand};
use serde::Deserialize;

/// Per-team bot resolution result. Either a Python `main.py` or a Rust
/// cdylib `.so`. The runner picks its execution path based on this.
pub enum BotKind {
    Python(String),
    Rust(PathBuf),
}

pub struct Args {
    pub player_a: BotKind,
    pub player_b: BotKind,
    pub replay: String,
    pub map: String,
    pub turn_timeout_ms: u64,
    pub seed: u64,
    pub suppress_indicators: bool,
    pub engine_root: PathBuf,
}

#[derive(Parser)]
#[command(
    name = "cambc-libre",
    version,
    about = "Open-source rebuild of the Cambridge Battlecode engine"
)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand)]
pub enum Command {
    /// Run a local match between two bots.
    Run(RunArgs),
}

#[derive(clap::Args)]
pub struct RunArgs {
    /// Bot A path. Either a Python bot (`main.py` or directory containing
    /// it) or a Rust bot (cdylib `.so` or a Cargo project directory).
    pub bot_a: String,
    /// Bot B path. Same resolution rules as `bot_a`.
    pub bot_b: String,
    /// Map path. Tries `<path>`, `<maps_dir>/<path>`, `<path>.map26`,
    /// `<maps_dir>/<path>.map26`.
    pub map: String,
    /// Output replay path (default from cambc.toml).
    #[arg(long)]
    pub replay: Option<String>,
    /// RNG seed. Affects only `distribute_resources` tiebreak and the
    /// end-game coinflip; bot RNG is separately keyed off entity ids.
    #[arg(long)]
    pub seed: Option<u64>,
    /// Turn time limit in ms. 0 disables enforcement; the engine still
    /// tracks real CPU time for `get_cpu_time_elapsed`. Default 0.
    #[arg(long, default_value_t = 0)]
    pub tle: u64,
    /// Translate Rust bots to Python via `pyrust-translate` before
    /// running. Useful for verifying that a Rust bot and its translated
    /// Python copy produce identical replays.
    #[arg(long)]
    pub translate: bool,
}

#[derive(Debug, Deserialize)]
struct CambcConfig {
    #[serde(default = "default_bots_dir")]
    bots_dir: String,
    #[serde(default = "default_maps_dir")]
    maps_dir: String,
    #[serde(default = "default_replay")]
    replay: String,
    #[serde(default = "default_seed")]
    seed: u64,
}

impl Default for CambcConfig {
    fn default() -> Self {
        Self {
            bots_dir: default_bots_dir(),
            maps_dir: default_maps_dir(),
            replay: default_replay(),
            seed: default_seed(),
        }
    }
}

fn default_bots_dir() -> String {
    "bots".into()
}
fn default_maps_dir() -> String {
    "maps".into()
}
fn default_replay() -> String {
    "replay.replay26".into()
}
fn default_seed() -> u64 {
    1
}

/// Walk up from cwd looking for `cambc.toml`. Returns (config, project_root).
/// If no `cambc.toml` is found, returns defaults rooted at cwd.
fn find_config() -> (CambcConfig, PathBuf) {
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut dir: Option<&Path> = Some(cwd.as_path());
    while let Some(d) = dir {
        let candidate = d.join("cambc.toml");
        if candidate.is_file() {
            if let Ok(text) = fs::read_to_string(&candidate) {
                let cfg: CambcConfig = toml::from_str(&text).unwrap_or_default();
                return (cfg, d.to_path_buf());
            }
        }
        dir = d.parent();
    }
    (CambcConfig::default(), cwd)
}

/// Resolve a bot path. Tries `path` then `<bots_dir>/<path>`. Detects
/// Python (`main.py` / `*.py`) vs Rust (`Cargo.toml` / `*.so`).
/// `translate=true` forces a Rust source directory through
/// `pyrust-translate` and returns the resulting Python bot.
fn resolve_bot(path_str: &str, bots_dir: &Path, translate: bool) -> Result<BotKind, String> {
    let direct = Path::new(path_str);
    let mut candidates: Vec<PathBuf> = vec![direct.to_path_buf()];
    if !direct.is_absolute() {
        candidates.push(bots_dir.join(path_str));
    }
    for p in &candidates {
        if let Some(kind) = classify_path(p, translate)? {
            return Ok(kind);
        }
    }
    Err(format!("bot not found: {path_str}"))
}

fn classify_path(p: &Path, translate: bool) -> Result<Option<BotKind>, String> {
    if p.is_dir() {
        let cargo = p.join("Cargo.toml");
        if cargo.is_file() {
            return Ok(Some(load_rust_bot(p, translate)?));
        }
        let main = p.join("main.py");
        if main.is_file() {
            return Ok(Some(BotKind::Python(canonical(&main)?)));
        }
        return Ok(None);
    }
    if !p.is_file() {
        return Ok(None);
    }
    let ext = p.extension().and_then(|e| e.to_str()).unwrap_or("");
    match ext {
        "so" => Ok(Some(BotKind::Rust(p.canonicalize().map_err(|e| e.to_string())?))),
        "py" => Ok(Some(BotKind::Python(canonical(p)?))),
        _ => Ok(None),
    }
}

/// Build a Rust bot directory and return its `.so`, or translate the
/// source to Python and return the translated `main.py`.
fn load_rust_bot(dir: &Path, translate: bool) -> Result<BotKind, String> {
    if translate {
        return translate_rust_bot(dir);
    }
    let so = build_rust_bot(dir)?;
    Ok(BotKind::Rust(so))
}

fn build_rust_bot(dir: &Path) -> Result<PathBuf, String> {
    eprintln!("[cambc-libre] cargo build {}", dir.display());
    let status = std::process::Command::new("cargo")
        .arg("build")
        .arg("--release")
        .current_dir(dir)
        .status()
        .map_err(|e| format!("cargo build: {e}"))?;
    if !status.success() {
        return Err(format!("cargo build failed in {}", dir.display()));
    }
    // Find the produced .so. The crate-type=cdylib output lives in
    // target/release/lib<crate>.so; find any .so directly under
    // target/release/.
    let release = dir.join("target").join("release");
    for entry in fs::read_dir(&release).map_err(|e| format!("read {}: {e}", release.display()))? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("so") {
            return path.canonicalize().map_err(|e| e.to_string());
        }
    }
    Err(format!("no .so produced in {}", release.display()))
}

fn translate_rust_bot(dir: &Path) -> Result<BotKind, String> {
    let translate_bin = pyrust_translate_bin()?;
    let src = dir.join("src");
    if !src.is_dir() {
        return Err(format!("Rust bot has no src/ dir: {}", dir.display()));
    }
    // Output dir: <project_root>/target/cambc-libre-translated/<bot-name>/
    let bot_name = dir
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("translated");
    let out_root = std::env::current_dir()
        .map_err(|e| e.to_string())?
        .join("target")
        .join("cambc-libre-translated")
        .join(bot_name);
    fs::create_dir_all(&out_root).map_err(|e| format!("mkdir {}: {e}", out_root.display()))?;
    eprintln!(
        "[cambc-libre] pyrust-translate --dir {} -o {}",
        src.display(),
        out_root.display()
    );
    let status = std::process::Command::new(&translate_bin)
        .arg("--dir")
        .arg(&src)
        .arg("-o")
        .arg(&out_root)
        .status()
        .map_err(|e| format!("pyrust-translate: {e}"))?;
    if !status.success() {
        return Err(format!(
            "pyrust-translate failed for {}",
            src.display()
        ));
    }
    // The bot's entry point is src/lib.rs → lib.py. Rename to main.py
    // so the existing Python loader picks up `Player` from main.py.
    // Always overwrite — pyrust-translate just regenerated lib.py and
    // any previous main.py is stale.
    let lib_py = out_root.join("lib.py");
    let main_py = out_root.join("main.py");
    if lib_py.is_file() {
        fs::rename(&lib_py, &main_py).map_err(|e| format!("rename: {e}"))?;
    }
    if !main_py.is_file() {
        return Err(format!("translated bot has no main.py at {}", main_py.display()));
    }
    Ok(BotKind::Python(canonical(&main_py)?))
}

fn pyrust_translate_bin() -> Result<PathBuf, String> {
    if let Some(p) = std::env::var_os("PYRUST_TRANSLATE_BIN") {
        return Ok(PathBuf::from(p));
    }
    // Same workspace as cambc-libre; the translate binary lives in the
    // same target/{debug,release} dir.
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe.parent().ok_or("current_exe has no parent")?;
    let candidate = dir.join("pyrust-translate");
    if candidate.is_file() {
        return Ok(candidate);
    }
    Err(format!(
        "pyrust-translate binary not found next to {}; build with `cargo build -p pyrust-translate` or set PYRUST_TRANSLATE_BIN",
        exe.display()
    ))
}

/// Resolve a map to an absolute `.map26` file.
/// Tries `path`, `<maps_dir>/<path>`, `<path>.map26`, `<maps_dir>/<path>.map26`.
fn resolve_map(path_str: &str, maps_dir: &Path) -> Result<String, String> {
    let direct = Path::new(path_str);
    let mut candidates: Vec<PathBuf> = vec![direct.to_path_buf()];
    if !direct.is_absolute() {
        candidates.push(maps_dir.join(path_str));
    }
    if !path_str.ends_with(".map26") {
        let with_ext = format!("{path_str}.map26");
        candidates.push(PathBuf::from(&with_ext));
        if !direct.is_absolute() {
            candidates.push(maps_dir.join(&with_ext));
        }
    }
    for p in &candidates {
        if p.is_file() {
            return Ok(canonical(p)?);
        }
    }
    Err(format!("map not found: {path_str}"))
}

fn canonical(p: &Path) -> Result<String, String> {
    p.canonicalize()
        .map(|q| q.display().to_string())
        .map_err(|e| format!("{}: {e}", p.display()))
}

/// Parse CLI args, resolve config + paths, and produce engine `Args`.
pub fn parse_args() -> Result<Args, String> {
    let cli = Cli::parse();
    let (cfg, project_root) = find_config();
    let bots_dir = project_root.join(&cfg.bots_dir);
    let maps_dir = project_root.join(&cfg.maps_dir);

    match cli.command {
        Command::Run(a) => {
            let player_a = resolve_bot(&a.bot_a, &bots_dir, a.translate)?;
            let player_b = resolve_bot(&a.bot_b, &bots_dir, a.translate)?;
            let map = resolve_map(&a.map, &maps_dir)?;
            let replay = a.replay.unwrap_or(cfg.replay);
            let seed = a.seed.unwrap_or(cfg.seed);
            let engine_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .expect("engine root")
                .to_path_buf();
            Ok(Args {
                player_a,
                player_b,
                replay,
                map,
                turn_timeout_ms: a.tle,
                seed,
                suppress_indicators: false,
                engine_root,
            })
        }
    }
}
