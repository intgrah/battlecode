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
    /// Path the opening was loaded from, if any. `None` when the CLI
    /// was given just a `.map26` (fresh opening).
    pub opening_path: Option<PathBuf>,
}

/// Parse a single positional path. Accepts `.map26` (fresh opening
/// for that map) or `.opening` (load existing book, follow its
/// `map_path` to load the map).
pub fn parse_args(args: Vec<OsString>) -> Result<Inputs, String> {
    let path = args
        .into_iter()
        .nth(1)
        .map(|a| a.to_string_lossy().into_owned())
        .ok_or_else(|| "usage: titan opening <map.map26 | book.opening>".to_string())?;
    let resolved = Path::new(&path)
        .canonicalize()
        .map_err(|e| format!("cannot resolve {path}: {e}"))?;
    let ext = resolved
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or_default();
    if ext == "opening" {
        let bytes = std::fs::read(&resolved)
            .map_err(|e| format!("cannot read {}: {e}", resolved.display()))?;
        let opening: opening::Opening =
            serde_json::from_slice(&bytes).map_err(|e| format!("invalid opening file: {e}"))?;
        let map_bytes = std::fs::read(&opening.map_path)
            .map_err(|e| format!("cannot read map {}: {e}", opening.map_path.display()))?;
        let map = cambc_proto::Map::decode(&*map_bytes).map_err(|e| format!("invalid map: {e}"))?;
        let map_path = opening.map_path.clone();
        Ok(Inputs {
            map,
            map_path,
            opening,
            opening_path: Some(resolved),
        })
    } else {
        let bytes = std::fs::read(&resolved)
            .map_err(|e| format!("cannot read {}: {e}", resolved.display()))?;
        let map = cambc_proto::Map::decode(&*bytes).map_err(|e| format!("invalid map: {e}"))?;
        Ok(Inputs {
            map,
            map_path: resolved.clone(),
            opening: opening::Opening::empty(resolved),
            opening_path: None,
        })
    }
}

#[must_use]
pub fn build(atlas: Arc<SpriteSet>, inputs: Inputs) -> app::App {
    let mut app = app::App::new(atlas, inputs.map, inputs.map_path, inputs.opening);
    app.opening_path = inputs.opening_path;
    app
}
