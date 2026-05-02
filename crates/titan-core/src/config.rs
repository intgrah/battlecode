//! Reads `cambc.toml` to find the project's default replay path and
//! maps directory. Walks up from cwd until it finds the file (or gives
//! up and returns defaults rooted at cwd).

use std::path::{Path, PathBuf};

use serde::Deserialize;

const CONFIG_FILENAME: &str = "cambc.toml";

#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
struct Raw {
    bots_dir: String,
    maps_dir: String,
    replay: String,
    seed: i64,
}

impl Default for Raw {
    fn default() -> Self {
        Self {
            bots_dir: "bots".into(),
            maps_dir: "maps".into(),
            replay: "replay.replay26".into(),
            seed: 1,
        }
    }
}

#[derive(Debug, Clone)]
pub struct CambcConfig {
    pub project_root: PathBuf,
    pub bots_dir: String,
    pub maps_dir: String,
    pub replay: String,
    pub seed: i64,
}

impl CambcConfig {
    #[must_use]
    pub fn replay_path(&self) -> PathBuf {
        self.project_root.join(&self.replay)
    }

    #[must_use]
    pub fn maps_path(&self) -> PathBuf {
        self.project_root.join(&self.maps_dir)
    }
}

/// Walks up from cwd looking for `cambc.toml`. Returns the parsed
/// config plus the directory containing the file (the "project root").
/// If no file is found, returns defaults rooted at cwd.
#[must_use]
pub fn find_config() -> CambcConfig {
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut dir: &Path = &cwd;
    loop {
        let candidate = dir.join(CONFIG_FILENAME);
        if candidate.is_file()
            && let Ok(text) = std::fs::read_to_string(&candidate)
            && let Ok(raw) = toml::from_str::<Raw>(&text)
        {
            return CambcConfig {
                project_root: dir.to_path_buf(),
                bots_dir: raw.bots_dir,
                maps_dir: raw.maps_dir,
                replay: raw.replay,
                seed: raw.seed,
            };
        }
        match dir.parent() {
            Some(parent) => dir = parent,
            None => break,
        }
    }
    let raw = Raw::default();
    CambcConfig {
        project_root: cwd,
        bots_dir: raw.bots_dir,
        maps_dir: raw.maps_dir,
        replay: raw.replay,
        seed: raw.seed,
    }
}
