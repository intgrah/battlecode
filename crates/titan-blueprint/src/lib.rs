pub use cambc_proto as proto;

pub mod app;
pub mod blueprint;
pub mod bp_io;
pub mod cost;
pub mod map;
pub mod map_view;
pub mod sequencing;
pub mod state;
pub mod symmetry;
pub mod ui;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use titan_core::SpriteSet;

pub struct Inputs {
    pub map: map::MapData,
    pub map_path: PathBuf,
}

pub fn parse_args(args: Vec<OsString>) -> Result<Inputs, String> {
    let path = args
        .into_iter()
        .nth(1)
        .map(|a| a.to_string_lossy().into_owned())
        .ok_or_else(|| "usage: titan blueprint <map.map26>".to_string())?;
    let map_path = Path::new(&path)
        .canonicalize()
        .map_err(|e| format!("cannot resolve {path}: {e}"))?;
    let map = map::load(&map_path)?;
    Ok(Inputs { map, map_path })
}

#[must_use]
pub fn build(atlas: Arc<SpriteSet>, inputs: Inputs) -> app::App {
    app::App::new(atlas, inputs.map, Some(inputs.map_path))
}
