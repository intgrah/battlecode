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
mod sprites;
mod state;
mod ui;

use std::{
    env, fs, io,
    path::Path,
    process,
    time::{Duration, SystemTime},
};

use crossterm::{
    ExecutableCommand,
    event::{self, DisableMouseCapture, EnableMouseCapture, Event},
    terminal::{self, EnterAlternateScreen, LeaveAlternateScreen},
};
use prost::Message;
use ratatui::prelude::*;

fn main() -> io::Result<()> {
    let path = env::args().nth(1).unwrap_or_else(|| {
        eprintln!("Usage: v <replay.replay26>");
        process::exit(1);
    });

    let replay_path = Path::new(&path);
    let data = fs::read(replay_path)?;
    let replay =
        proto::Replay::decode(&*data).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

    let exe_path = env::current_exe().unwrap_or_default();
    let exe_dir = exe_path.parent().unwrap_or_else(|| Path::new("."));
    let candidates = [
        exe_dir.join("../../assets"),
        exe_dir.join("../assets"),
        Path::new("assets").to_path_buf(),
    ];
    let assets_dir = candidates
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| Path::new("assets").to_path_buf());

    let atlas = sprites::SpriteAtlas::load(&assets_dir);
    let mut app = ui::App::new(replay, atlas);
    let mut last_modified = fs::metadata(replay_path)
        .and_then(|m| m.modified())
        .unwrap_or(SystemTime::UNIX_EPOCH);

    io::stdout()
        .execute(EnterAlternateScreen)?
        .execute(EnableMouseCapture)?;
    terminal::enable_raw_mode()?;
    let mut term = Terminal::new(CrosstermBackend::new(io::stdout()))?;

    'main: loop {
        if let Ok(meta) = fs::metadata(replay_path)
            && let Ok(modified) = meta.modified()
            && modified != last_modified
            && let Ok(new_data) = fs::read(replay_path)
            && let Ok(new_replay) = proto::Replay::decode(&*new_data)
        {
            app.reload(new_replay);
            last_modified = modified;
        }

        term.draw(|f| app.render(f))?;
        app.render_map_if_needed();

        let timeout = if app.playing {
            Duration::from_millis(app.tick_ms())
        } else {
            Duration::from_millis(100)
        };

        if event::poll(timeout)? {
            loop {
                match event::read()? {
                    Event::Key(key) if app.handle_key(key) => break 'main,
                    Event::Mouse(mouse) => app.handle_mouse(mouse),
                    _ => {}
                }
                if !event::poll(Duration::ZERO)? {
                    break;
                }
            }
        } else if app.playing {
            app.step_forward(1);
        }
    }

    kitty::delete_image(1)?;
    terminal::disable_raw_mode()?;
    io::stdout()
        .execute(DisableMouseCapture)?
        .execute(LeaveAlternateScreen)?;
    Ok(())
}
