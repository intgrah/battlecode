pub use cambc_proto as proto;

pub mod app;
pub mod blueprint;
pub mod bp_io;
pub mod codegen;
pub mod cost;
pub mod flow;
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
        .ok_or_else(|| "usage: titan blueprint <map.map26 | blueprint.bp>".to_string())?;
    resolve_input(&path)
}

/// Accept either a `.map26` (load directly) or a `.bp` (read its `map:`
/// header, resolve the map under the maps dir, then load).
fn resolve_input(path: &str) -> Result<Inputs, String> {
    let p = Path::new(path);
    let ext = p.extension().and_then(|s| s.to_str()).unwrap_or("");
    if ext == "bp" {
        let bp_abs = p
            .canonicalize()
            .map_err(|e| format!("cannot resolve {path}: {e}"))?;
        let loaded = bp_io::load_bp_path(&bp_abs)
            .ok_or_else(|| format!("cannot parse blueprint {}", bp_abs.display()))?;
        let map_path = locate_map(&loaded.map_name)
            .ok_or_else(|| format!("cannot locate map for `{}`", loaded.map_name))?;
        let map = map::load(&map_path)?;
        return Ok(Inputs { map, map_path });
    }
    let map_path = p
        .canonicalize()
        .map_err(|e| format!("cannot resolve {path}: {e}"))?;
    let map = map::load(&map_path)?;
    Ok(Inputs { map, map_path })
}

fn locate_map(map_name: &str) -> Option<PathBuf> {
    let manifest = env!("CARGO_MANIFEST_DIR");
    let candidate = Path::new(manifest)
        .join("..")
        .join("..")
        .join("maps")
        .join(format!("{map_name}.map26"));
    candidate.canonicalize().ok()
}

#[must_use]
pub fn build(atlas: Arc<SpriteSet>, inputs: Inputs) -> app::App {
    app::App::new(atlas, inputs.map, Some(inputs.map_path))
}
