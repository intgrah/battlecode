pub mod app;
pub mod entities;
pub mod export;
pub mod opening;
pub mod sim;

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use prost::Message;
use titan_core::SpriteSet;

pub struct Inputs {
    pub map: cambc_proto::Map,
    pub map_path: PathBuf,
    pub opening: opening::Opening,
}

pub fn parse_args(args: Vec<OsString>) -> Result<Inputs, String> {
    let path = args
        .into_iter()
        .nth(1)
        .map(|a| a.to_string_lossy().into_owned())
        .ok_or_else(|| "usage: titan opening <map.map26>".to_string())?;
    let map_path = Path::new(&path)
        .canonicalize()
        .map_err(|e| format!("cannot resolve {path}: {e}"))?;
    let bytes =
        std::fs::read(&map_path).map_err(|e| format!("cannot read {}: {e}", map_path.display()))?;
    let map = cambc_proto::Map::decode(&*bytes).map_err(|e| format!("invalid map: {e}"))?;
    Ok(Inputs {
        map,
        map_path: map_path.clone(),
        opening: opening::Opening::empty(map_path),
    })
}

#[must_use]
pub fn build(atlas: Arc<SpriteSet>, inputs: Inputs) -> app::App {
    app::App::new(atlas, inputs.map, inputs.map_path, inputs.opening)
}
