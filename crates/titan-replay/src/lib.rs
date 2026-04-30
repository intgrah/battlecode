pub use cambc_proto as proto;

pub mod app;
pub mod entity;
pub mod flow;
pub mod map;
pub mod state;
pub mod ui;
pub mod vis;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use prost::Message;
use titan_core::SpriteSet;

pub struct Inputs {
    pub replay: proto::Replay,
    pub replay_path: PathBuf,
}

pub fn parse_args(args: Vec<OsString>) -> Result<Inputs, String> {
    let path = args
        .into_iter()
        .nth(1)
        .map(|a| a.to_string_lossy().into_owned())
        .ok_or_else(|| "usage: titan replay <replay.replay26>".to_string())?;

    let replay_path = Path::new(&path)
        .canonicalize()
        .map_err(|e| format!("cannot resolve path {path}: {e}"))?;
    let data = std::fs::read(&replay_path)
        .map_err(|e| format!("cannot read {}: {e}", replay_path.display()))?;
    let replay = proto::Replay::decode(&*data).map_err(|e| format!("invalid replay: {e}"))?;

    Ok(Inputs {
        replay,
        replay_path,
    })
}

#[must_use]
pub fn build(atlas: Arc<SpriteSet>, inputs: Inputs) -> app::App {
    app::App::new(atlas, &inputs.replay, inputs.replay_path)
}
