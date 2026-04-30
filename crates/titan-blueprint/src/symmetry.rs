use crate::blueprint::BlueprintEntry;
use crate::map::MapData;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Symmetry {
    Rot,
    Hor,
    Ver,
}

impl Symmetry {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Rot => "ROT",
            Self::Hor => "HOR",
            Self::Ver => "VER",
        }
    }
}

pub const fn mirror_pos(pos: (i32, i32), w: i32, h: i32, sym: Symmetry) -> (i32, i32) {
    let (x, y) = pos;
    match sym {
        Symmetry::Hor => (x, h - 1 - y),
        Symmetry::Ver => (w - 1 - x, y),
        Symmetry::Rot => (w - 1 - x, h - 1 - y),
    }
}

pub const fn mirror_delta(dx: i32, dy: i32, sym: Symmetry) -> (i32, i32) {
    match sym {
        Symmetry::Hor => (dx, -dy),
        Symmetry::Ver => (-dx, dy),
        Symmetry::Rot => (-dx, -dy),
    }
}

pub fn mirror_entry(entry: &BlueprintEntry, w: i32, h: i32, sym: Symmetry) -> BlueprintEntry {
    let mut out = *entry;
    out.pos = mirror_pos(entry.pos, w, h, sym);
    if let Some(d) = entry.direction {
        let (dx, dy) = d.delta();
        let (ndx, ndy) = mirror_delta(dx, dy, sym);
        out.direction = crate::blueprint::Direction::from_delta(ndx, ndy).or(entry.direction);
    }
    if let Some(bt) = entry.bridge_target {
        out.bridge_target = Some(mirror_pos(bt, w, h, sym));
    }
    out
}

fn tiles_match(m: &MapData, sym: Symmetry) -> bool {
    for y in 0..m.h {
        for x in 0..m.w {
            let (mx, my) = mirror_pos((x, y), m.w, m.h, sym);
            if m.tile(x, y) != m.tile(mx, my) {
                return false;
            }
        }
    }
    true
}

pub fn detect(m: &MapData) -> Result<Symmetry, String> {
    for sym in [Symmetry::Rot, Symmetry::Hor, Symmetry::Ver] {
        if mirror_pos(m.core_a, m.w, m.h, sym) != m.core_b {
            continue;
        }
        if tiles_match(m, sym) {
            return Ok(sym);
        }
    }
    Err(format!("no symmetry detected for {}", m.name))
}
