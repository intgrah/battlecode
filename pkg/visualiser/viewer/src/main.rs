pub use cambc_proto as proto;

mod app;
mod entity;
mod flow;
mod map;
mod state;
mod ui;
mod vis;

use std::{env, fs, path::Path, process};

use eframe::egui;
use prost::Message;

fn main() -> eframe::Result {
    let path = env::args().nth(1).unwrap_or_else(|| {
        eprintln!("Usage: v <replay.replay26>");
        process::exit(1);
    });

    let replay_path = Path::new(&path).canonicalize().unwrap_or_else(|e| {
        eprintln!("Cannot resolve path {path}: {e}");
        process::exit(1);
    });
    let data = fs::read(&replay_path).unwrap_or_else(|e| {
        eprintln!("Cannot read {}: {e}", replay_path.display());
        process::exit(1);
    });
    let replay = proto::Replay::decode(&*data).unwrap_or_else(|e| {
        eprintln!("Invalid replay: {e}");
        process::exit(1);
    });

    let exe_path = env::current_exe().unwrap_or_default();
    let exe_dir = exe_path.parent().unwrap_or_else(|| Path::new("."));
    let candidates = [
        exe_dir.join("../../../visualiser/viewer/assets"),
        exe_dir.join("../../assets"),
        exe_dir.join("../assets"),
        Path::new("pkg/visualiser/viewer/assets").to_path_buf(),
        Path::new("assets").to_path_buf(),
    ];
    let assets_dir = candidates
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| Path::new("assets").to_path_buf());

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 800.0])
            .with_maximized(true)
            .with_title("Battlecode Replay"),
        ..Default::default()
    };
    eframe::run_native(
        "v",
        options,
        Box::new(move |cc| {
            Ok(Box::new(app::App::new(
                cc,
                &replay,
                &assets_dir,
                replay_path,
            )))
        }),
    )
}
