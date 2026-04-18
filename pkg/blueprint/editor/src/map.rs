use std::path::Path;

use prost::Message;

use crate::proto;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tile {
    Empty,
    Wall,
    OreTitanium,
    OreAxionite,
}

impl Tile {
    const fn from_env(e: proto::Environment) -> Self {
        match e {
            proto::Environment::EnvWall => Self::Wall,
            proto::Environment::EnvOreTitanium => Self::OreTitanium,
            proto::Environment::EnvOreAxionite => Self::OreAxionite,
            proto::Environment::EnvEmpty => Self::Empty,
        }
    }
}

#[derive(Debug, Clone)]
pub struct MapData {
    pub name: String,
    pub w: i32,
    pub h: i32,
    pub core_a: (i32, i32),
    pub core_b: (i32, i32),
    pub tiles: Vec<Tile>,
}

impl MapData {
    pub fn tile(&self, x: i32, y: i32) -> Tile {
        if x < 0 || y < 0 || x >= self.w || y >= self.h {
            return Tile::Wall;
        }
        let idx = (y * self.w + x) as usize;
        self.tiles[idx]
    }
}

pub fn load(path: &Path) -> Result<MapData, String> {
    let data = std::fs::read(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    let m = proto::Map::decode(&*data).map_err(|e| format!("decode map: {e}"))?;
    let w = m.width;
    let h = m.height;
    let mut tiles: Vec<Tile> = Vec::with_capacity((w * h) as usize);
    for row in &m.rows {
        for t in &row.tiles {
            let env = proto::Environment::try_from(*t).unwrap_or(proto::Environment::EnvEmpty);
            tiles.push(Tile::from_env(env));
        }
    }
    let (mut core_a, mut core_b) = (None, None);
    for c in &m.cores {
        let pos = c
            .position
            .as_ref()
            .map_or((0, 0), |p| (p.x, p.y));
        if c.team == (proto::Team::A as i32) {
            core_a = Some(pos);
        } else {
            core_b = Some(pos);
        }
    }
    let core_a = core_a.ok_or_else(|| format!("map {} missing core A", path.display()))?;
    let core_b = core_b.ok_or_else(|| format!("map {} missing core B", path.display()))?;
    let name = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();
    Ok(MapData {
        name,
        w,
        h,
        core_a,
        core_b,
        tiles,
    })
}
