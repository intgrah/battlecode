use std::fs;
use std::path::{Path, PathBuf};

use clap::{CommandFactory, Parser, Subcommand};
use clap_complete::Shell;
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
    /// Print a shell-completion script for the given shell to stdout.
    /// Pipe into the appropriate completions file, e.g.
    /// `cambc-libre completions fish > ~/.config/fish/completions/cambc-libre.fish`.
    Completions {
        /// One of: bash, zsh, fish, powershell, elvish.
        shell: Shell,
    },
    /// Internal: list bots from the configured `bots_dir`, one per line.
    /// Used by shell completions.
    #[command(name = "_list-bots", hide = true)]
    ListBots,
    /// Internal: list maps from the configured `maps_dir`, one per line.
    /// Used by shell completions.
    #[command(name = "_list-maps", hide = true)]
    ListMaps,
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
    /// Translate Rust bots in release mode (clears `debug_assertions`,
    /// stripping `#[cfg(debug_assertions)]` items and turning
    /// `cfg!(debug_assertions)` into `False`). Only meaningful with
    /// `--translate`.
    #[arg(long)]
    pub release: bool,
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
const fn default_seed() -> u64 {
    1
}

/// Walk up from cwd looking for `cambc.toml`. Returns (config, `project_root`).
/// If no `cambc.toml` is found, returns defaults rooted at cwd.
fn find_config() -> (CambcConfig, PathBuf) {
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut dir: Option<&Path> = Some(cwd.as_path());
    while let Some(d) = dir {
        let candidate = d.join("cambc.toml");
        if candidate.is_file()
            && let Ok(text) = fs::read_to_string(&candidate)
        {
            let cfg: CambcConfig = toml::from_str(&text).unwrap_or_default();
            return (cfg, d.to_path_buf());
        }
        dir = d.parent();
    }
    (CambcConfig::default(), cwd)
}

/// Resolve a bot path. Tries `path` then `<bots_dir>/<path>`. Detects
/// Python (`main.py` / `*.py`) vs Rust (`Cargo.toml` / `*.so`).
/// `translate=true` forces a Rust source directory through
/// `pyrust-translate` and returns the resulting Python bot.
fn resolve_bot(
    path_str: &str,
    bots_dir: &Path,
    translate: bool,
    release: bool,
) -> Result<BotKind, String> {
    let direct = Path::new(path_str);
    let mut candidates: Vec<PathBuf> = vec![direct.to_path_buf()];
    if !direct.is_absolute() {
        candidates.push(bots_dir.join(path_str));
    }
    for p in &candidates {
        if let Some(kind) = classify_path(p, translate, release)? {
            return Ok(kind);
        }
    }
    Err(format!("bot not found: {path_str}"))
}

fn classify_path(p: &Path, translate: bool, release: bool) -> Result<Option<BotKind>, String> {
    if p.is_dir() {
        let cargo = p.join("Cargo.toml");
        if cargo.is_file() {
            return Ok(Some(load_rust_bot(p, translate, release)?));
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
        "so" => Ok(Some(BotKind::Rust(
            p.canonicalize().map_err(|e| e.to_string())?,
        ))),
        "py" => Ok(Some(BotKind::Python(canonical(p)?))),
        _ => Ok(None),
    }
}

/// Build a Rust bot directory and return its `.so`, or translate the
/// source to Python and return the translated `main.py`.
fn load_rust_bot(dir: &Path, translate: bool, release: bool) -> Result<BotKind, String> {
    if translate {
        return translate_rust_bot(dir, release);
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
    // The .so is `lib<package_name with - → _>.so`. Read the package name
    // from the bot's Cargo.toml directly; ask cargo metadata for the
    // (possibly workspace-rooted) target directory.
    let package_name = read_package_name(dir)?;
    let target_dir = cargo_target_dir(dir)?;
    let so_name = format!("lib{}.so", package_name.replace('-', "_"));
    let so_path = target_dir.join("release").join(&so_name);
    if !so_path.is_file() {
        return Err(format!("expected {} not produced", so_path.display()));
    }
    so_path.canonicalize().map_err(|e| e.to_string())
}

/// Read `package.name` from `<dir>/Cargo.toml`.
fn read_package_name(dir: &Path) -> Result<String, String> {
    #[derive(Deserialize)]
    struct CargoToml {
        package: Package,
    }
    #[derive(Deserialize)]
    struct Package {
        name: String,
    }
    let manifest = dir.join("Cargo.toml");
    let text =
        fs::read_to_string(&manifest).map_err(|e| format!("read {}: {e}", manifest.display()))?;
    let parsed: CargoToml =
        toml::from_str(&text).map_err(|e| format!("parse {}: {e}", manifest.display()))?;
    Ok(parsed.package.name)
}

/// Resolve the target directory for the Cargo project at `dir`. Honours
/// workspace membership: a bot crate that's part of a parent workspace
/// produces its `.so` under the workspace's `target/`, not its own.
fn cargo_target_dir(dir: &Path) -> Result<PathBuf, String> {
    let output = std::process::Command::new("cargo")
        .args(["metadata", "--no-deps", "--format-version=1"])
        .current_dir(dir)
        .output()
        .map_err(|e| format!("cargo metadata: {e}"))?;
    if !output.status.success() {
        return Err(format!(
            "cargo metadata failed in {}: {}",
            dir.display(),
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let stdout = std::str::from_utf8(&output.stdout)
        .map_err(|e| format!("cargo metadata not utf-8: {e}"))?;
    let key = "\"target_directory\":\"";
    let start = stdout
        .find(key)
        .ok_or_else(|| "cargo metadata missing target_directory".to_string())?
        + key.len();
    let rest = &stdout[start..];
    let end = rest
        .find('"')
        .ok_or_else(|| "cargo metadata target_directory unterminated".to_string())?;
    Ok(PathBuf::from(&rest[..end]))
}

fn translate_rust_bot(dir: &Path, release: bool) -> Result<BotKind, String> {
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
    let release_label = if release { " --release" } else { "" };
    eprintln!(
        "[cambc-libre] pyrust-translate{} --dir {} -o {}",
        release_label,
        src.display(),
        out_root.display()
    );
    // Call the translator in-process via the library API instead of
    // spawning a separate `pyrust-translate` binary. Same effect, but
    // `cargo install cambc-libre` no longer needs a sibling binary.
    let mut cfg = pyrust_translate::CfgEnv::debug();
    if release {
        cfg.apply_cfg_arg("debug_assertions=false")
            .map_err(|e| format!("pyrust-translate cfg: {e}"))?;
    }
    pyrust_translate::translate_dir(&src, &out_root, &cfg)
        .map_err(|e| format!("pyrust-translate failed for {}: {e}", src.display()))?;
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
        return Err(format!(
            "translated bot has no main.py at {}",
            main_py.display()
        ));
    }
    Ok(BotKind::Python(canonical(&main_py)?))
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
            return canonical(p);
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
/// Recursively walk `bots_dir` and print the relative path of each bot.
/// A bot is a directory containing `main.py` (Python) or `Cargo.toml` (Rust).
/// Stops descending once a bot is found at any level.
fn list_bots(bots_dir: &Path) {
    fn walk(root: &Path, dir: &Path, out: &mut Vec<String>) {
        if dir != root && (dir.join("main.py").is_file() || dir.join("Cargo.toml").is_file()) {
            if let Ok(rel) = dir.strip_prefix(root) {
                out.push(rel.to_string_lossy().into_owned());
            }
            return;
        }
        let entries = match fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => return,
        };
        for entry in entries.flatten() {
            let p = entry.path();
            if !p.is_dir() {
                continue;
            }
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if name.starts_with('.') || matches!(name, "target" | "src" | "__pycache__") {
                continue;
            }
            walk(root, &p, out);
        }
    }
    let mut bots: Vec<String> = Vec::new();
    walk(bots_dir, bots_dir, &mut bots);
    bots.sort();
    for b in bots {
        println!("{b}");
    }
}

/// Print the file stem of every `*.map26` directly under `maps_dir`.
fn list_maps(maps_dir: &Path) {
    let entries = match fs::read_dir(maps_dir) {
        Ok(e) => e,
        Err(_) => return,
    };
    let mut maps: Vec<String> = Vec::new();
    for entry in entries.flatten() {
        let p = entry.path();
        if p.extension().and_then(|e| e.to_str()) != Some("map26") {
            continue;
        }
        if let Some(stem) = p.file_stem().and_then(|s| s.to_str()) {
            maps.push(stem.to_string());
        }
    }
    maps.sort();
    for m in maps {
        println!("{m}");
    }
}

/// Fish-specific tail appended after `clap_complete::generate` so that
/// positional args of `run` get dynamic completion from the configured
/// `bots_dir` and `maps_dir`.
const FISH_DYNAMIC_TAIL: &str = r#"
# --- dynamic completion for `run` positionals (cambc-libre) ---
function __cambc_libre_run_position
    set -l cmd (commandline -opc)
    set -l n 0
    set -l skip 0
    for tok in $cmd
        if test $skip -eq 1
            set skip 0
            continue
        end
        switch $tok
            case 'cambc-libre' '*/cambc-libre' 'run'
                continue
            case '--replay' '--seed' '--tle'
                set skip 1
            case '--*' '-*'
                # value-less flag (or unknown) — don't count
                continue
            case '*'
                set n (math $n + 1)
        end
    end
    echo $n
end

complete -c cambc-libre -n "__fish_cambc_libre_using_subcommand run; and test (__cambc_libre_run_position) -le 1" -f -a "(cambc-libre _list-bots)"
complete -c cambc-libre -n "__fish_cambc_libre_using_subcommand run; and test (__cambc_libre_run_position) -eq 2" -f -a "(cambc-libre _list-maps)"
"#;

pub fn parse_args() -> Result<Args, String> {
    let cli = Cli::parse();
    let (cfg, project_root) = find_config();
    let bots_dir = project_root.join(&cfg.bots_dir);
    let maps_dir = project_root.join(&cfg.maps_dir);

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
        Command::ListBots => {
            list_bots(&bots_dir);
            std::process::exit(0);
        }
        Command::ListMaps => {
            list_maps(&maps_dir);
            std::process::exit(0);
        }
        Command::Run(a) => {
            let player_a = resolve_bot(&a.bot_a, &bots_dir, a.translate, a.release)?;
            let player_b = resolve_bot(&a.bot_b, &bots_dir, a.translate, a.release)?;
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
