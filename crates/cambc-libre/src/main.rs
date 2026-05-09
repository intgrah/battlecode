#[cfg(all(feature = "tle", not(target_os = "linux")))]
compile_error!("the 'tle' feature requires Linux (depends on libc clock_gettime)");

use std::path::Path;

use pyo3::prelude::*;

use cambc_libre::cli::BotKind;
use cambc_libre::runner::MatchSummary;
use cambc_libre_engine::common::Team;

/// Python install prefix at build time — baked in via build.rs probing
/// `PYO3_PYTHON`. Used to set PYTHONHOME before `Py_Initialize` so the
/// embedded interpreter finds its standard library.
const BAKED_PYTHON_HOME: Option<&str> = option_env!("CAMBC_PYTHON_HOME");

fn main() -> PyResult<()> {
    // Set PYTHONHOME before pyo3's auto-initialize fires (which happens
    // on the first `Python::with_gil`). User-set PYTHONHOME wins.
    if std::env::var_os("PYTHONHOME").is_none()
        && let Some(home) = BAKED_PYTHON_HOME
    {
        // SAFETY: single-threaded — main() hasn't started Python or
        // spawned any threads.
        unsafe {
            std::env::set_var("PYTHONHOME", home);
        }
    }
    let args = match cambc_libre::cli::parse_args() {
        Ok(args) => args,
        Err(err) => {
            eprintln!("error: {err}");
            std::process::exit(2);
        }
    };
    let name_a = bot_label(&args.player_a);
    let name_b = bot_label(&args.player_b);
    let map_name = Path::new(&args.map)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(&args.map)
        .to_string();
    let replay_path = args.replay.clone();
    let seed = args.seed;
    let tle = args.turn_timeout_ms;

    println!("Running match: {name_a} vs {name_b}");
    println!(
        "  Map: {map_name}  Seed: {seed}  Replay: {replay_path}  TLE: {}",
        if tle == 0 {
            "off".to_string()
        } else {
            format!("{tle}ms")
        }
    );

    let summary = match cambc_libre::runner::run(args) {
        Ok(s) => s,
        Err(e) => {
            Python::with_gil(|py| {
                e.print(py);
            });
            return Err(e);
        }
    };
    if Path::new(&replay_path).exists() {
        println!("Replay written to {replay_path}");
    }
    print_summary(&summary, &name_a, &name_b);
    Ok(())
}

/// Resolve a human-readable bot label. For Python: parent dir of `main.py`
/// or the file stem. For Rust: the cdylib's crate name (file stem with the
/// leading `lib` stripped), which by convention matches the bot directory.
fn bot_label(kind: &BotKind) -> String {
    let path: &Path = match kind {
        BotKind::Python(p) => Path::new(p),
        BotKind::Rust(p) => p.as_path(),
    };
    if path.file_name().and_then(|s| s.to_str()) == Some("main.py") {
        path.parent()
            .and_then(|d| d.file_name())
            .and_then(|s| s.to_str())
            .unwrap_or("?")
            .to_string()
    } else if path.extension().and_then(|s| s.to_str()) == Some("so") {
        let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("?");
        let name = stem.strip_prefix("lib").unwrap_or(stem);
        format!("{name} (rust)")
    } else {
        path.file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("?")
            .to_string()
    }
}

fn print_summary(s: &MatchSummary, name_a: &str, name_b: &str) {
    let winner_label = match s.winner {
        Some(Team::A) => name_a.to_string(),
        Some(Team::B) => name_b.to_string(),
        None => "Draw".to_string(),
    };
    println!();
    let resign = s
        .resign_message
        .as_ref()
        .map(|m| format!(" — {m}"))
        .unwrap_or_default();
    println!(
        "  Winner: {winner_label}  ({}, turn {}){resign}",
        s.win_condition, s.turns_played
    );
    println!();

    let col_w = name_a.len().max(name_b.len()).max(8) + 6;
    let lbl_w = 10;
    println!(
        "  {:>lbl$}  {:>col$}  {:>col$}",
        "",
        name_a,
        name_b,
        lbl = lbl_w,
        col = col_w
    );
    println!(
        "  {:>lbl$}  {:>col$}  {:>col$}",
        "Titanium",
        format!(
            "{} ({})",
            s.player_a_titanium, s.player_a_titanium_collected
        ),
        format!(
            "{} ({})",
            s.player_b_titanium, s.player_b_titanium_collected
        ),
        lbl = lbl_w,
        col = col_w
    );
    println!(
        "  {:>lbl$}  {:>col$}  {:>col$}",
        "Axionite",
        format!(
            "{} ({})",
            s.player_a_axionite, s.player_a_axionite_collected
        ),
        format!(
            "{} ({})",
            s.player_b_axionite, s.player_b_axionite_collected
        ),
        lbl = lbl_w,
        col = col_w
    );
    println!(
        "  {:>lbl$}  {:>col$}  {:>col$}",
        "Units",
        s.units_a,
        s.units_b,
        lbl = lbl_w,
        col = col_w
    );
    println!(
        "  {:>lbl$}  {:>col$}  {:>col$}",
        "Buildings",
        s.buildings_a,
        s.buildings_b,
        lbl = lbl_w,
        col = col_w
    );
    println!();
}
