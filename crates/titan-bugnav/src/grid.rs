use std::path::Path;

use cambc_proto as proto;
use prost::Message;

pub struct Grid {
    pub w: i32,
    pub h: i32,
    pub walls: Vec<bool>,
    pub env: Vec<proto::Environment>,
    pub name: String,
}

impl Grid {
    #[must_use]
    pub fn passable(&self, x: i32, y: i32) -> bool {
        if x < 0 || y < 0 || x >= self.w || y >= self.h {
            return false;
        }
        !self.walls[(y * self.w + x) as usize]
    }

    #[must_use]
    pub fn env_at(&self, x: i32, y: i32) -> proto::Environment {
        if x < 0 || y < 0 || x >= self.w || y >= self.h {
            return proto::Environment::EnvWall;
        }
        self.env[(y * self.w + x) as usize]
    }

    pub fn load(path: &Path) -> Result<Self, String> {
        let data = std::fs::read(path).map_err(|e| format!("read {}: {e}", path.display()))?;
        let m = proto::Map::decode(&*data).map_err(|e| format!("decode map: {e}"))?;
        let w = m.width;
        let h = m.height;
        let mut walls = Vec::with_capacity((w * h) as usize);
        let mut env = Vec::with_capacity((w * h) as usize);
        for row in &m.rows {
            for t in &row.tiles {
                let e = proto::Environment::try_from(*t).unwrap_or(proto::Environment::EnvEmpty);
                walls.push(matches!(e, proto::Environment::EnvWall));
                env.push(e);
            }
        }
        let name = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();
        Ok(Self {
            w,
            h,
            walls,
            env,
            name,
        })
    }
}
