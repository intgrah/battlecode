use std::collections::HashMap;

use crate::blueprint::{BlueprintEntry, Direction, Entity, ALL_DIRECTIONS, CARDINALS};

#[derive(Debug, Clone)]
pub enum Op {
    Place {
        before: Option<BlueprintEntry>,
        after: BlueprintEntry,
    },
    Erase {
        before: BlueprintEntry,
    },
    Rotate {
        before: BlueprintEntry,
        after: BlueprintEntry,
    },
}

pub struct EditorState {
    pub entries: HashMap<(i32, i32), BlueprintEntry>,
    undo_stack: Vec<Op>,
    redo_stack: Vec<Op>,
    pub dirty: bool,
}

impl EditorState {
    pub fn new() -> Self {
        Self {
            entries: HashMap::new(),
            undo_stack: Vec::new(),
            redo_stack: Vec::new(),
            dirty: false,
        }
    }

    pub fn load(&mut self, entries: impl IntoIterator<Item = BlueprintEntry>) {
        self.entries.clear();
        self.undo_stack.clear();
        self.redo_stack.clear();
        for e in entries {
            self.entries.insert(e.pos, e);
        }
        self.dirty = false;
    }

    pub fn place(&mut self, entry: BlueprintEntry) {
        let before = self.entries.get(&entry.pos).copied();
        self.entries.insert(entry.pos, entry);
        self.undo_stack.push(Op::Place { before, after: entry });
        self.redo_stack.clear();
        self.dirty = true;
    }

    pub fn erase(&mut self, pos: (i32, i32)) {
        let Some(before) = self.entries.remove(&pos) else {
            return;
        };
        self.undo_stack.push(Op::Erase { before });
        self.redo_stack.clear();
        self.dirty = true;
    }

    pub fn rotate(&mut self, pos: (i32, i32), step: i32) {
        let Some(entry) = self.entries.get(&pos).copied() else {
            return;
        };
        if !entry.kind.is_directional() {
            return;
        }
        let dirs: &[Direction] = if entry.kind.is_cardinal_only() {
            &CARDINALS
        } else {
            &ALL_DIRECTIONS
        };
        let cur = entry.direction.unwrap_or(dirs[0]);
        let i = dirs
            .iter()
            .position(|d| *d == cur)
            .unwrap_or(0) as i32;
        let n = dirs.len() as i32;
        let new = dirs[((i + step).rem_euclid(n)) as usize];
        let mut updated = entry;
        updated.direction = Some(new);
        self.entries.insert(pos, updated);
        self.undo_stack.push(Op::Rotate {
            before: entry,
            after: updated,
        });
        self.redo_stack.clear();
        self.dirty = true;
    }

    pub fn undo(&mut self) {
        let Some(op) = self.undo_stack.pop() else {
            return;
        };
        self.apply_inverse(&op);
        self.redo_stack.push(op);
        self.dirty = true;
    }

    pub fn redo(&mut self) {
        let Some(op) = self.redo_stack.pop() else {
            return;
        };
        self.apply_forward(&op);
        self.undo_stack.push(op);
        self.dirty = true;
    }

    fn apply_inverse(&mut self, op: &Op) {
        match op {
            Op::Place { before, after } => {
                if let Some(b) = before {
                    self.entries.insert(after.pos, *b);
                } else {
                    self.entries.remove(&after.pos);
                }
            }
            Op::Erase { before } | Op::Rotate { before, .. } => {
                self.entries.insert(before.pos, *before);
            }
        }
    }

    fn apply_forward(&mut self, op: &Op) {
        match op {
            Op::Place { after, .. } | Op::Rotate { after, .. } => {
                self.entries.insert(after.pos, *after);
            }
            Op::Erase { before } => {
                self.entries.remove(&before.pos);
            }
        }
    }
}

pub struct Editor {
    pub map_name: String,
    pub core_a: (i32, i32),
    pub core_b: (i32, i32),
    pub sym: crate::symmetry::Symmetry,
    pub state: EditorState,
    pub tool: Entity,
    pub bridge_source: Option<(i32, i32)>,
    pub status: String,
    pub last_direction: HashMap<Entity, Direction>,
    pub n_builders: i32,
    pub current_phase: i32,
}

impl Editor {
    pub fn new(map: &crate::map::MapData, sym: crate::symmetry::Symmetry) -> Self {
        let mut last_direction = HashMap::new();
        for k in [
            Entity::Conveyor,
            Entity::ArmouredConveyor,
            Entity::Splitter,
            Entity::Gunner,
            Entity::Sentinel,
            Entity::Breach,
        ] {
            last_direction.insert(k, Direction::East);
        }
        Self {
            map_name: map.name.clone(),
            core_a: map.core_a,
            core_b: map.core_b,
            sym,
            state: EditorState::new(),
            tool: Entity::Conveyor,
            bridge_source: None,
            status: String::new(),
            last_direction,
            n_builders: 6,
            current_phase: 0,
        }
    }

    pub fn place(&mut self, map: &crate::map::MapData, pos: (i32, i32), entity: Entity) {
        if entity == Entity::Bridge && self.bridge_source.is_some() {
            let src = self.bridge_source.unwrap();
            let (dx, dy) = (pos.0 - src.0, pos.1 - src.1);
            let d2 = dx * dx + dy * dy;
            const LIMIT: i32 = 9;
            if d2 == 0 || d2 > LIMIT {
                self.status = format!("bridge needs 0 < r² <= {LIMIT}, got {d2}");
                self.bridge_source = None;
                return;
            }
            self.state.place(BlueprintEntry {
                pos: src,
                kind: Entity::Bridge,
                direction: None,
                bridge_target: Some(pos),
                phase: self.current_phase,
            });
            self.bridge_source = None;
            self.status = format!("bridge {src:?}->{pos:?}");
            return;
        }

        let tile = map.tile(pos.0, pos.1);
        if tile == crate::map::Tile::Wall {
            self.status = format!("can't place on wall @ {pos:?}");
            return;
        }
        for core in [self.core_a, self.core_b] {
            if (pos.0 - core.0).abs() <= 1 && (pos.1 - core.1).abs() <= 1 {
                self.status = format!("can't place on core @ {pos:?}");
                return;
            }
        }
        if entity == Entity::Harvester
            && !matches!(tile, crate::map::Tile::OreTitanium | crate::map::Tile::OreAxionite)
        {
            self.status = "harvester needs ore".into();
            return;
        }

        if entity == Entity::Bridge {
            self.bridge_source = Some(pos);
            self.status = format!("bridge src {pos:?}, click target");
            return;
        }

        let direction = if entity.is_directional() {
            Some(
                self.last_direction
                    .get(&entity)
                    .copied()
                    .unwrap_or(Direction::East),
            )
        } else {
            None
        };

        self.state.place(BlueprintEntry {
            pos,
            kind: entity,
            direction,
            bridge_target: None,
            phase: self.current_phase,
        });
        self.status = format!("placed {} @ {pos:?}", entity.name());
    }

    pub fn place_conveyor_dir(
        &mut self,
        map: &crate::map::MapData,
        pos: (i32, i32),
        kind: Entity,
        direction: Direction,
    ) {
        let tile = map.tile(pos.0, pos.1);
        if tile == crate::map::Tile::Wall {
            return;
        }
        for core in [self.core_a, self.core_b] {
            if (pos.0 - core.0).abs() <= 1 && (pos.1 - core.1).abs() <= 1 {
                return;
            }
        }
        self.state.place(BlueprintEntry {
            pos,
            kind,
            direction: Some(direction),
            bridge_target: None,
            phase: self.current_phase,
        });
        self.last_direction.insert(kind, direction);
    }

    pub fn erase(&mut self, pos: (i32, i32)) {
        if self.state.entries.contains_key(&pos) {
            self.state.erase(pos);
            self.status = format!("erased {pos:?}");
        }
    }

    pub fn rotate_at(&mut self, pos: (i32, i32), step: i32) {
        self.state.rotate(pos, step);
        if let Some(e) = self.state.entries.get(&pos)
            && let Some(d) = e.direction {
                self.last_direction.insert(e.kind, d);
            }
    }

    pub fn save(&mut self) {
        let entries: HashMap<(i32, i32), BlueprintEntry> = self.state.entries.clone();
        let bad = crate::sequencing::unrouted(&entries, self.core_a);
        if !bad.is_empty() {
            self.status = format!("save blocked: {} unrouted", bad.len());
            return;
        }
        let all: Vec<BlueprintEntry> = self.state.entries.values().copied().collect();
        match crate::bp_io::write_bp(&self.map_name, &all) {
            Ok(path) => {
                self.state.dirty = false;
                self.status = format!("saved {}", path.display());
            }
            Err(e) => {
                self.status = format!("save failed: {e}");
            }
        }
    }
}
