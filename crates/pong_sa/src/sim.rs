use std::cmp::Ordering;
use std::collections::{BTreeMap, BinaryHeap};

use rand::SeedableRng;
use rand::rngs::StdRng;
use rustc_hash::{FxHashMap, FxHashSet};

use crate::constants::{
    ACTION_RADIUS_SQ, ARMOURED_CONVEYOR_BASE_COST, BARRIER_BASE_COST, BRIDGE_BASE_COST,
    BRIDGE_TARGET_RADIUS_SQ, BUILDER_BOT_BASE_COST, CONVEYOR_BASE_COST, FOUNDRY_BASE_COST,
    HARVESTER_BASE_COST, PASSIVE_TITANIUM_AMOUNT, PASSIVE_TITANIUM_INTERVAL, ROAD_BASE_COST,
    SPLITTER_BASE_COST, STARTING_AXIONITE, STARTING_SCALE_MILLI, STARTING_TITANIUM,
};
use crate::plan::{Build, CoreAction, Plan, TurnAction};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Pos {
    pub x: i32,
    pub y: i32,
}

impl Pos {
    pub const fn new(x: i32, y: i32) -> Self {
        Self { x, y }
    }
    pub const fn dist_sq(self, other: Pos) -> i32 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        dx * dx + dy * dy
    }
    pub const fn add(self, d: Direction) -> Pos {
        let (dx, dy) = d.delta();
        Pos { x: self.x + dx, y: self.y + dy }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Direction {
    North, Northeast, East, Southeast, South, Southwest, West, Northwest,
}

impl Direction {
    pub const fn delta(self) -> (i32, i32) {
        match self {
            Self::North => (0, -1), Self::Northeast => (1, -1), Self::East => (1, 0),
            Self::Southeast => (1, 1), Self::South => (0, 1), Self::Southwest => (-1, 1),
            Self::West => (-1, 0), Self::Northwest => (-1, -1),
        }
    }
    pub const fn opposite(self) -> Direction {
        match self {
            Self::North => Self::South, Self::Northeast => Self::Southwest, Self::East => Self::West,
            Self::Southeast => Self::Northwest, Self::South => Self::North, Self::Southwest => Self::Northeast,
            Self::West => Self::East, Self::Northwest => Self::Southeast,
        }
    }
}

const CARDINALS: [Direction; 4] = [Direction::North, Direction::East, Direction::South, Direction::West];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tile {
    Empty,
    Wall,
    OreTitanium,
    OreAxionite,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Resource {
    Titanium,
    RawAxionite,
    RefinedAxionite,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum BuildKind {
    Conveyor,
    Splitter,
    ArmouredConveyor,
    Bridge,
    Harvester,
    Foundry,
    Road,
    Barrier,
}

impl BuildKind {
    pub const fn base_cost(self) -> (i32, i32) {
        match self {
            Self::Conveyor => CONVEYOR_BASE_COST,
            Self::Splitter => SPLITTER_BASE_COST,
            Self::ArmouredConveyor => ARMOURED_CONVEYOR_BASE_COST,
            Self::Bridge => BRIDGE_BASE_COST,
            Self::Harvester => HARVESTER_BASE_COST,
            Self::Foundry => FOUNDRY_BASE_COST,
            Self::Road => ROAD_BASE_COST,
            Self::Barrier => BARRIER_BASE_COST,
        }
    }
    pub const fn scale_milli(self) -> i32 {
        match self {
            Self::Road => 5,
            Self::Conveyor | Self::Splitter | Self::ArmouredConveyor | Self::Barrier => 10,
            Self::Harvester => 50,
            Self::Bridge => 100,
            Self::Foundry => 500,
        }
    }
    pub const fn is_walkable(self) -> bool {
        matches!(
            self,
            Self::Conveyor | Self::Splitter | Self::ArmouredConveyor | Self::Bridge | Self::Road
        )
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Building {
    pub pos: Pos,
    pub kind: BuildKind,
    pub direction: Option<Direction>,
    pub bridge_target: Option<Pos>,
    pub stored: Option<Resource>,
    pub harvester_resource: Option<Resource>,
    pub harvester_cooldown: i32,
}

impl Building {
    fn output_targets(&self) -> Vec<Pos> {
        match self.kind {
            BuildKind::Conveyor | BuildKind::ArmouredConveyor => {
                vec![self.pos.add(self.direction.expect("conveyor missing dir"))]
            }
            BuildKind::Bridge => vec![self.bridge_target.expect("bridge missing target")],
            BuildKind::Splitter => {
                let excluded = self.direction.expect("splitter missing dir").opposite();
                CARDINALS.iter().filter(|d| **d != excluded).map(|d| self.pos.add(*d)).collect()
            }
            BuildKind::Harvester | BuildKind::Foundry => {
                CARDINALS.iter().map(|d| self.pos.add(*d)).collect()
            }
            _ => Vec::new(),
        }
    }

    fn resource_to_feed(&self) -> Option<Resource> {
        match self.kind {
            BuildKind::Conveyor | BuildKind::Splitter | BuildKind::ArmouredConveyor | BuildKind::Bridge => self.stored,
            BuildKind::Harvester => {
                if self.harvester_cooldown == 0 { self.harvester_resource } else { None }
            }
            BuildKind::Foundry => {
                if self.stored == Some(Resource::RefinedAxionite) { Some(Resource::RefinedAxionite) } else { None }
            }
            _ => None,
        }
    }

    fn can_accept_from(&self, resource: Resource, source_pos: Pos, source_is_bridge: bool) -> bool {
        match self.kind {
            BuildKind::Conveyor | BuildKind::ArmouredConveyor => {
                let dir = self.direction.expect("conveyor missing dir");
                (source_is_bridge || source_pos != self.pos.add(dir)) && self.stored.is_none()
            }
            BuildKind::Splitter => {
                let dir = self.direction.expect("splitter missing dir");
                let input_pos = self.pos.add(dir.opposite());
                if !source_is_bridge && source_pos != input_pos { return false; }
                self.stored.is_none()
            }
            BuildKind::Bridge => self.stored.is_none(),
            BuildKind::Foundry => matches!(
                (resource, self.stored),
                (Resource::Titanium, Some(Resource::RawAxionite) | None)
                    | (Resource::RawAxionite, Some(Resource::Titanium) | None)
            ),
            _ => false,
        }
    }

    fn receive_resource(&mut self, resource: Resource) {
        match self.kind {
            BuildKind::Conveyor | BuildKind::Splitter | BuildKind::ArmouredConveyor | BuildKind::Bridge => {
                self.stored = Some(resource);
            }
            BuildKind::Foundry => match (resource, self.stored) {
                (r @ (Resource::Titanium | Resource::RawAxionite), None) => self.stored = Some(r),
                (Resource::Titanium, Some(Resource::RawAxionite))
                | (Resource::RawAxionite, Some(Resource::Titanium)) => {
                    self.stored = Some(Resource::RefinedAxionite);
                }
                _ => panic!("foundry got unexpected {resource:?} with stored {:?}", self.stored),
            },
            _ => panic!("receive_resource on non-receiver kind {:?}", self.kind),
        }
    }

    fn consume_feed(&mut self) {
        match self.kind {
            BuildKind::Conveyor | BuildKind::Splitter | BuildKind::ArmouredConveyor
            | BuildKind::Bridge | BuildKind::Foundry => self.stored = None,
            BuildKind::Harvester => self.harvester_cooldown = 4,
            _ => panic!("consume_feed on {:?}", self.kind),
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Builder {
    pub id: i32,
    pub pos: Pos,
    pub action_cd: i32,
    pub move_cd: i32,
    pub alive: bool,
}

#[derive(Debug, Clone)]
pub struct Map {
    pub width: i32,
    pub height: i32,
    pub tiles: Vec<Tile>,
    pub core: Pos,
}

impl Map {
    pub fn idx(&self, p: Pos) -> Option<usize> {
        if p.x < 0 || p.y < 0 || p.x >= self.width || p.y >= self.height {
            None
        } else {
            Some((p.y * self.width + p.x) as usize)
        }
    }
    pub fn tile(&self, p: Pos) -> Tile {
        self.idx(p).map_or(Tile::Wall, |i| self.tiles[i])
    }
    pub fn in_bounds(&self, p: Pos) -> bool {
        self.idx(p).is_some()
    }
}

#[derive(Debug)]
pub struct State {
    pub map: Map,
    pub turn: i32,
    pub titanium: i32,
    pub axionite: i32,
    pub titanium_collected: i32,
    pub axionite_collected: i32,
    pub scale_milli: i32,
    pub buildings: FxHashMap<Pos, Building>,
    pub builders: Vec<Builder>,
    pub builder_at: FxHashMap<Pos, usize>,
    pub core_action_cd: i32,
    pub edge_last_used: FxHashMap<(Pos, Pos), i32>,
    pub rng: StdRng,
    pub next_builder_id: i32,
}

impl State {
    pub fn new(map: Map, seed: u64) -> Self {
        Self {
            map,
            turn: 0,
            titanium: STARTING_TITANIUM,
            axionite: STARTING_AXIONITE,
            titanium_collected: 0,
            axionite_collected: 0,
            scale_milli: STARTING_SCALE_MILLI,
            buildings: FxHashMap::default(),
            builders: Vec::new(),
            builder_at: FxHashMap::default(),
            core_action_cd: 0,
            edge_last_used: FxHashMap::default(),
            rng: StdRng::seed_from_u64(seed),
            next_builder_id: 100,
        }
    }

    pub fn scaled_cost(&self, base: (i32, i32)) -> (i32, i32) {
        (base.0 * self.scale_milli / 1000, base.1 * self.scale_milli / 1000)
    }

    /// Place a building without paying cost or scaling. For setup / parity tests
    /// against pong-sim's `place_godmode`.
    pub fn godmode_place(
        &mut self,
        kind: BuildKind,
        pos: Pos,
        direction: Option<Direction>,
        bridge_target: Option<Pos>,
    ) {
        let harvester_resource = if kind == BuildKind::Harvester {
            Some(match self.map.tile(pos) {
                Tile::OreTitanium => Resource::Titanium,
                Tile::OreAxionite => Resource::RawAxionite,
                _ => panic!("harvester not on ore at {:?}", pos),
            })
        } else {
            None
        };
        let bldg = Building {
            pos,
            kind,
            direction,
            bridge_target,
            stored: None,
            harvester_resource,
            harvester_cooldown: 0,
        };
        self.buildings.insert(pos, bldg);
        self.scale_milli += kind.scale_milli();
    }

    pub fn is_core_tile(&self, p: Pos) -> bool {
        let cx = self.map.core.x;
        let cy = self.map.core.y;
        (p.x - cx).abs() <= 1 && (p.y - cy).abs() <= 1
    }

    pub fn is_bot_passable(&self, p: Pos) -> bool {
        if !self.map.in_bounds(p) || self.builder_at.contains_key(&p) {
            return false;
        }
        if let Some(b) = self.buildings.get(&p) {
            b.kind.is_walkable()
        } else {
            self.is_core_tile(p)
        }
    }

    pub fn step(&mut self, plan: &Plan) {
        let t = self.turn as usize;
        if t >= plan.turns as usize {
            return;
        }
        // Core action (spawn) first, mirroring spawn-as-unit-action ordering.
        let core = plan.core[t];
        self.do_core(core);
        // Builders act in id-sorted (i.e. spawn) order.
        let n = self.builders.len().min(plan.builders.len());
        for i in 0..n {
            if !self.builders[i].alive {
                continue;
            }
            self.do_builder(i, plan.builders[i].get(t).copied().unwrap_or(TurnAction::NOOP));
        }
        self.distribute_resources();
        self.update_cooldowns();
        if (self.turn + 1) % PASSIVE_TITANIUM_INTERVAL == 0 {
            self.titanium += PASSIVE_TITANIUM_AMOUNT;
        }
        self.turn += 1;
    }

    fn do_core(&mut self, action: CoreAction) {
        if self.core_action_cd != 0 {
            return;
        }
        let Some(spawn_pos) = action.spawn else { return };
        if !self.is_core_tile(spawn_pos) || self.builder_at.contains_key(&spawn_pos) {
            return;
        }
        let cost = self.scaled_cost(BUILDER_BOT_BASE_COST);
        if self.titanium < cost.0 || self.axionite < cost.1 {
            return;
        }
        self.titanium -= cost.0;
        self.axionite -= cost.1;
        let id = self.next_builder_id;
        self.next_builder_id += 1;
        let idx = self.builders.len();
        self.builders.push(Builder { id, pos: spawn_pos, action_cd: 0, move_cd: 0, alive: true });
        self.builder_at.insert(spawn_pos, idx);
        self.scale_milli += 200;
        self.core_action_cd = 1;
    }

    fn do_builder(&mut self, i: usize, action: TurnAction) {
        if let Some(b) = action.build {
            self.try_build(i, b);
        } else if let Some(p) = action.destroy {
            self.try_destroy(i, p);
        }
        if let Some(d) = action.mv {
            self.try_move(i, d);
        }
    }

    fn try_build(&mut self, i: usize, b: Build) -> bool {
        let bot = self.builders[i];
        if bot.action_cd != 0 || bot.pos.dist_sq(b.pos) > ACTION_RADIUS_SQ {
            return false;
        }
        if !self.map.in_bounds(b.pos) {
            return false;
        }
        if self.buildings.contains_key(&b.pos) {
            return false;
        }
        if self.is_core_tile(b.pos) {
            return false;
        }
        // Tile-specific: harvester must be on ore.
        match b.kind {
            BuildKind::Harvester => {
                let t = self.map.tile(b.pos);
                if !matches!(t, Tile::OreTitanium | Tile::OreAxionite) {
                    return false;
                }
            }
            BuildKind::Foundry | BuildKind::Conveyor | BuildKind::Splitter
            | BuildKind::ArmouredConveyor | BuildKind::Bridge
            | BuildKind::Road | BuildKind::Barrier => {
                if matches!(self.map.tile(b.pos), Tile::Wall) { return false; }
            }
        }
        if b.kind == BuildKind::Bridge {
            let Some(t) = b.bridge_target else { return false };
            if b.pos.dist_sq(t) > BRIDGE_TARGET_RADIUS_SQ { return false; }
        }
        let cost = self.scaled_cost(b.kind.base_cost());
        if self.titanium < cost.0 || self.axionite < cost.1 {
            return false;
        }
        self.titanium -= cost.0;
        self.axionite -= cost.1;
        let harvester_resource = if b.kind == BuildKind::Harvester {
            Some(match self.map.tile(b.pos) {
                Tile::OreTitanium => Resource::Titanium,
                Tile::OreAxionite => Resource::RawAxionite,
                _ => unreachable!(),
            })
        } else {
            None
        };
        let bldg = Building {
            pos: b.pos,
            kind: b.kind,
            direction: b.direction,
            bridge_target: b.bridge_target,
            stored: None,
            harvester_resource,
            harvester_cooldown: 0,
        };
        self.buildings.insert(b.pos, bldg);
        self.scale_milli += b.kind.scale_milli();
        self.builders[i].action_cd = 1;
        true
    }

    fn try_destroy(&mut self, i: usize, p: Pos) -> bool {
        let bot = self.builders[i];
        if bot.pos.dist_sq(p) > ACTION_RADIUS_SQ {
            return false;
        }
        let Some(bldg) = self.buildings.remove(&p) else { return false };
        self.scale_milli -= bldg.kind.scale_milli();
        true
    }

    fn try_move(&mut self, i: usize, d: Direction) -> bool {
        let bot = self.builders[i];
        if bot.move_cd != 0 {
            return false;
        }
        let to = bot.pos.add(d);
        if !self.is_bot_passable(to) {
            return false;
        }
        self.builder_at.remove(&bot.pos);
        self.builder_at.insert(to, i);
        self.builders[i].pos = to;
        self.builders[i].move_cd = 1;
        true
    }

    fn update_cooldowns(&mut self) {
        if self.core_action_cd > 0 {
            self.core_action_cd -= 1;
        }
        for b in &mut self.builders {
            if b.action_cd > 0 { b.action_cd -= 1; }
            if b.move_cd > 0 { b.move_cd -= 1; }
        }
        for b in self.buildings.values_mut() {
            if b.kind == BuildKind::Harvester && b.harvester_cooldown > 0 {
                b.harvester_cooldown -= 1;
            }
        }
    }

    pub fn distribute_resources(&mut self) {
        // Mirrors cambc-libre-engine/src/game/distribute.rs exactly.
        #[derive(Clone, Debug)]
        struct Edge { priority: f64, source: Pos, sink: Pos }
        impl Eq for Edge {}
        impl PartialEq for Edge { fn eq(&self, o: &Self) -> bool { self.priority == o.priority } }
        impl Ord for Edge {
            fn cmp(&self, o: &Self) -> Ordering {
                self.priority.partial_cmp(&o.priority).unwrap_or(Ordering::Equal)
            }
        }
        impl PartialOrd for Edge { fn partial_cmp(&self, o: &Self) -> Option<Ordering> { Some(self.cmp(o)) } }

        let mut incoming: BTreeMap<Pos, Vec<Pos>> = BTreeMap::new();
        let mut outgoing_count: FxHashMap<Pos, usize> = FxHashMap::default();
        let mut processed: FxHashSet<Pos> = FxHashSet::default();

        // Iterate buildings in ROW-MAJOR order (same as engine's tiles iteration).
        let mut all: Vec<(Pos, Building)> = self
            .buildings
            .iter()
            .map(|(p, b)| (*p, *b))
            .collect();
        all.sort_by_key(|(p, _)| (p.y, p.x));

        for (pos, b) in &all {
            let no_output = match b.kind {
                BuildKind::Conveyor | BuildKind::Splitter | BuildKind::ArmouredConveyor | BuildKind::Bridge => b.stored.is_none(),
                BuildKind::Foundry => matches!(b.stored, None | Some(Resource::Titanium) | Some(Resource::RawAxionite)),
                _ => false,
            };
            if no_output {
                processed.insert(*pos);
            }
            let mut count = 0;
            for sink_pos in b.output_targets() {
                if !self.map.in_bounds(sink_pos) {
                    continue;
                }
                if self.has_sink_at(sink_pos) {
                    count += 1;
                    incoming.entry(sink_pos).or_default().push(*pos);
                }
            }
            outgoing_count.insert(*pos, count);
        }

        let edge_priority = |source: Pos, sink: Pos, edge_last_used: &FxHashMap<(Pos, Pos), i32>| -> i32 {
            let src_out = outgoing_count.get(&source).copied().unwrap_or(0);
            let sink_in = incoming.get(&sink).map_or(0, std::vec::Vec::len);
            if src_out == 1 && sink_in == 1 { i32::MAX }
            else { -edge_last_used.get(&(source, sink)).copied().unwrap_or(0) }
        };

        let mut heap: BinaryHeap<Edge> = BinaryHeap::new();
        for (sink_pos, sources) in &incoming {
            for source_pos in sources {
                let resource = match self.buildings.get(source_pos).and_then(Building::resource_to_feed) {
                    Some(r) => r,
                    None => continue,
                };
                let source_is_bridge = matches!(self.buildings.get(source_pos).map(|b| b.kind), Some(BuildKind::Bridge));
                let sink_can_accept = self.sink_can_accept(*sink_pos, resource, *source_pos, source_is_bridge);
                if sink_can_accept {
                    let priority = edge_priority(*source_pos, *sink_pos, &self.edge_last_used);
                    let jitter = self.rng_f64();
                    heap.push(Edge { priority: f64::from(priority) + jitter, source: *source_pos, sink: *sink_pos });
                }
            }
        }

        let mut moves: Vec<(Pos, Pos)> = Vec::new();
        while let Some(edge) = heap.pop() {
            if processed.contains(&edge.source) { continue; }
            let resource = match self.buildings.get(&edge.source).and_then(Building::resource_to_feed) {
                Some(r) => r,
                None => continue,
            };
            let source_is_bridge = matches!(self.buildings.get(&edge.source).map(|b| b.kind), Some(BuildKind::Bridge));
            if !self.sink_can_accept(edge.sink, resource, edge.source, source_is_bridge) {
                continue;
            }
            // Apply transfer.
            self.deliver(edge.sink, resource);
            if let Some(b) = self.buildings.get_mut(&edge.source) {
                b.consume_feed();
            }
            moves.push((edge.source, edge.sink));
            processed.insert(edge.source);

            // Push upstream sources of edge.source back.
            let upstream = incoming.get(&edge.source).cloned().unwrap_or_default();
            for upstream_pos in upstream {
                if processed.contains(&upstream_pos) { continue; }
                let up_resource = match self.buildings.get(&upstream_pos).and_then(Building::resource_to_feed) {
                    Some(r) => r,
                    None => continue,
                };
                let upstream_is_bridge = matches!(self.buildings.get(&upstream_pos).map(|b| b.kind), Some(BuildKind::Bridge));
                if !self.sink_can_accept(edge.source, up_resource, upstream_pos, upstream_is_bridge) {
                    continue;
                }
                let priority = edge_priority(upstream_pos, edge.source, &self.edge_last_used);
                let jitter = self.rng_f64();
                heap.push(Edge { priority: f64::from(priority) + jitter, source: upstream_pos, sink: edge.source });
            }
        }

        for (source, sink) in &moves {
            self.edge_last_used.insert((*source, *sink), self.turn);
        }
    }

    /// True if `pos` is the position of a building (sink target candidate).
    /// Mirrors `if sink_tile.building.is_some()` in the engine.
    fn has_sink_at(&self, pos: Pos) -> bool {
        if self.buildings.contains_key(&pos) { return true; }
        // Core occupies its 3x3.
        self.is_core_tile(pos)
    }

    /// Whether the sink at `sink_pos` can accept `resource` from `source_pos`.
    /// Includes the engine's special case for Core.
    fn sink_can_accept(&self, sink_pos: Pos, resource: Resource, source_pos: Pos, source_is_bridge: bool) -> bool {
        if let Some(b) = self.buildings.get(&sink_pos) {
            return b.can_accept_from(resource, source_pos, source_is_bridge);
        }
        // Core: accepts anything.
        self.is_core_tile(sink_pos)
    }

    fn deliver(&mut self, sink_pos: Pos, resource: Resource) {
        if let Some(b) = self.buildings.get_mut(&sink_pos) {
            b.receive_resource(resource);
            return;
        }
        // Core delivery: increment player resource counters.
        if self.is_core_tile(sink_pos) {
            match resource {
                Resource::Titanium => {
                    self.titanium += 10;
                    self.titanium_collected += 10;
                }
                Resource::RefinedAxionite => {
                    self.axionite += 10;
                    self.axionite_collected += 10;
                }
                Resource::RawAxionite => {
                    // raw ax delivered to core is destroyed
                }
            }
        }
    }

    fn rng_f64(&mut self) -> f64 {
        use rand::RngExt;
        self.rng.random::<f64>()
    }
}
