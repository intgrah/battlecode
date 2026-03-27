#[allow(
    clippy::derive_partial_eq_without_eq,
    clippy::doc_markdown,
    clippy::enum_variant_names,
    clippy::missing_const_for_fn,
    clippy::trivially_copy_pass_by_ref
)]
mod proto {
    include!(concat!(env!("OUT_DIR"), "/battlecode.rs"));
}

mod kitty;
mod renderer;
mod replay;
mod sprites;
mod state;
mod ui;

use std::{env, fs, io, path::Path, process, time::Duration};

use crossterm::{
    ExecutableCommand,
    event::{self, Event},
    terminal::{self, EnterAlternateScreen, LeaveAlternateScreen},
};
use prost::Message;
use ratatui::prelude::*;

fn main() -> io::Result<()> {
    let path = env::args().nth(1).unwrap_or_else(|| {
        eprintln!("Usage: v <replay.replay26>");
        process::exit(1);
    });

    let data = fs::read(&path)?;
    let replay =
        proto::Replay::decode(&*data).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

    let exe_path = env::current_exe().unwrap_or_default();
    let assets_dir = exe_path
        .parent()
        .unwrap_or(Path::new("."))
        .join("../assets");
    let assets_dir = if assets_dir.exists() {
        assets_dir
    } else {
        Path::new("assets").to_path_buf()
    };

    let atlas = sprites::SpriteAtlas::load(&assets_dir);
    let mut app = ui::App::new(replay, atlas);

    io::stdout().execute(EnterAlternateScreen)?;
    terminal::enable_raw_mode()?;
    let mut term = Terminal::new(CrosstermBackend::new(io::stdout()))?;

    loop {
        term.draw(|f| app.render(f))?;
        app.render_map_if_needed();

        let timeout = if app.playing {
            Duration::from_millis(app.tick_ms())
        } else {
            Duration::from_millis(100)
        };

        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()?
                && app.handle_key(key)
            {
                break;
            }
        } else if app.playing {
            app.step_forward(1);
        }
    }

    kitty::delete_image(1)?;
    terminal::disable_raw_mode()?;
    io::stdout().execute(LeaveAlternateScreen)?;
    Ok(())
}
