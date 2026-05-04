//! Blueprint solver: build a Vec<Placement> programmatically by routing
//! conveyors on the map grid.
//!
//! Three layers:
//! 1. `Map`: parsed .map26 — walls, ore tiles, core position.
//! 2. `Network`: incrementally built tile claims (which tile = which
//!    entity, carrying which resource type, with which direction).
//! 3. `route()`: A*-style path search that places conveyors satisfying
//!    geometric and type constraints.

use std::collections::BinaryHeap;
use std::collections::HashMap;
use std::collections::HashSet;
use std::path::Path;

use libre_engine::common::{Direction, Environment, Pos, ResourceType, Team};

use crate::blueprint::{Kind, Placement};
use crate::flow::CarriedType;

const CARDINALS: [Direction; 4] = [
    Direction::North,
    Direction::East,
    Direction::South,
    Direction::West,
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Cell {
    Empty,
    Wall,
    Ti,
    Ax,
}

#[derive(Debug, Clone)]
pub struct Map {
    pub width: i32,
    pub height: i32,
    pub cells: Vec<Cell>,
    pub core_a: Pos,   // centre of team A core
    pub core_b: Pos,   // centre of team B core (used as wall avoidance)
}

impl Map {
    pub fn load(path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        let s = path.to_str().ok_or("non-utf8 map path")?;
        let (env, cores) = libre_replay::load_map(s)?;
        let height = env.len() as i32;
        let width = env.first().map(|r| r.len() as i32).unwrap_or(0);
        let mut cells = Vec::with_capacity((width * height) as usize);
        for row in &env {
            for &t in row {
                cells.push(match t {
                    Environment::Empty => Cell::Empty,
                    Environment::Wall => Cell::Wall,
                    Environment::OreTitanium => Cell::Ti,
                    Environment::OreAxionite => Cell::Ax,
                });
            }
        }
        let core_a = cores
            .iter()
            .find(|(_, t)| *t == Team::A)
            .map(|(p, _)| *p)
            .ok_or("no team A core")?;
        let core_b = cores
            .iter()
            .find(|(_, t)| *t == Team::B)
            .map(|(p, _)| *p)
            .ok_or("no team B core")?;
        Ok(Map {
            width,
            height,
            cells,
            core_a,
            core_b,
        })
    }

    pub fn cell(&self, p: Pos) -> Cell {
        if !self.in_bounds(p) {
            return Cell::Wall;
        }
        self.cells[(p.y * self.width + p.x) as usize]
    }

    pub fn in_bounds(&self, p: Pos) -> bool {
        p.x >= 0 && p.y >= 0 && p.x < self.width && p.y < self.height
    }

    /// True if `p` is on this team's core (3x3 around `core_a`).
    pub fn is_core(&self, p: Pos) -> bool {
        (p.x - self.core_a.x).abs() <= 1 && (p.y - self.core_a.y).abs() <= 1
    }

    /// True if `p` is on the enemy core (avoid).
    pub fn is_enemy_core(&self, p: Pos) -> bool {
        (p.x - self.core_b.x).abs() <= 1 && (p.y - self.core_b.y).abs() <= 1
    }

    pub fn ore_at(&self, p: Pos) -> Option<ResourceType> {
        match self.cell(p) {
            Cell::Ti => Some(ResourceType::Titanium),
            Cell::Ax => Some(ResourceType::RawAxionite),
            _ => None,
        }
    }

    pub fn all_ax(&self) -> Vec<Pos> {
        let mut v = Vec::new();
        for y in 0..self.height {
            for x in 0..self.width {
                let p = Pos { x, y };
                if matches!(self.cell(p), Cell::Ax) {
                    v.push(p);
                }
            }
        }
        v
    }

    pub fn all_ti(&self) -> Vec<Pos> {
        let mut v = Vec::new();
        for y in 0..self.height {
            for x in 0..self.width {
                let p = Pos { x, y };
                if matches!(self.cell(p), Cell::Ti) {
                    v.push(p);
                }
            }
        }
        v
    }
}

/// Incremental network state. Tracks which tile is claimed by which
/// (entity, carried resource type). Used to detect collisions and
/// contamination during routing.
#[derive(Debug, Clone, Default)]
pub struct Network {
    pub placements: Vec<Placement>,
    pub tile_owner: HashMap<Pos, TileOwner>,
}

#[derive(Debug, Clone, Copy)]
pub struct TileOwner {
    pub kind: Kind,
    pub direction: Option<Direction>,
    pub bridge_target: Option<Pos>,
    /// Resource type this tile is committed to carrying.
    pub carries: Option<CarriedType>,
}

impl Network {
    pub fn place(&mut self, p: Placement, carries: Option<CarriedType>) -> Result<(), String> {
        if self.tile_owner.contains_key(&p.pos) {
            return Err(format!("tile {:?} already claimed", p.pos));
        }
        self.tile_owner.insert(
            p.pos,
            TileOwner {
                kind: p.kind,
                direction: p.direction,
                bridge_target: p.bridge_target,
                carries,
            },
        );
        self.placements.push(p);
        Ok(())
    }

    pub fn occupied(&self, p: Pos) -> bool {
        self.tile_owner.contains_key(&p)
    }

    pub fn owner(&self, p: Pos) -> Option<&TileOwner> {
        self.tile_owner.get(&p)
    }
}

/// A routed path from `src` to `sink`: list of (tile, direction) pairs for
/// the conveyors to place. The harvester at `src` outputs to the first tile;
/// each conveyor outputs in its direction; the last conveyor outputs to `sink`.
#[derive(Debug, Clone)]
pub struct Route {
    pub conveyors: Vec<(Pos, Direction)>,
}

/// Find a conveyor route from `src` to `sink` for resource `rt`, given the
/// current `network` state and `map` constraints.
///
/// Constraints:
/// - Path tiles must be Empty (not ore, not wall, not enemy core).
/// - Path tiles must not be already claimed (or must be claimed for the
///   same resource type as a compatible conveyor).
/// - At each path tile, the conveyor's 3 input sides (non-output) must not
///   touch any other-type carrier (would contaminate).
/// - First tile must be cardinal-adjacent to `src` (harvester's neighbour).
/// - Last tile must be cardinal-adjacent to `sink` and face toward `sink`.
///
/// Returns None if no path found.
pub fn route(
    map: &Map,
    network: &Network,
    src: Pos,
    sink: Pos,
    rt: CarriedType,
) -> Option<Route> {
    // BFS / A* over (tile, incoming_direction) state. incoming_direction
    // is the direction stack arrives at this tile from (= source side).
    // Conveyor at tile with output direction d_out must have d_out != incoming.
    // Each step: from tile T with incoming I, try to step to T+d_out where
    // d_out is one of CARDINALS \ {I.opposite()}. Wait — conveyor accepts
    // from 3 sides; its output is one direction. We choose output direction
    // when placing, so flexibility is high.
    //
    // Simpler model: BFS on tiles (no direction state). At each tile, check
    // (1) tile passable, (2) no contamination from neighbours.

    let manhattan = |a: Pos, b: Pos| -> i32 { (a.x - b.x).abs() + (a.y - b.y).abs() };

    // Candidate sink-adjacent first conveyor placement. The conveyor must
    // face toward sink. So we enumerate (sink_neighbour_pos, direction) pairs.
    let sink_adj: Vec<(Pos, Direction)> = CARDINALS
        .iter()
        .filter_map(|&d| {
            let np = sink + d.opposite(); // tile that, with direction d, outputs to sink-side
            // Actually: we want a tile T such that T + d_out = sink. So T = sink + d_inv where d_inv = -d_out.
            // Let d_out = D. T = sink + D.opposite(). Direction = D.
            let t = sink + d.opposite();
            if !map.in_bounds(t) {
                return None;
            }
            if !is_routable_tile(map, network, t) {
                return None;
            }
            Some((t, d))
        })
        .collect();
    let sink_set: HashSet<Pos> = sink_adj.iter().map(|(t, _)| *t).collect();

    // First step from src: a cardinal neighbour with passable tile.
    let src_adj: Vec<Pos> = CARDINALS
        .iter()
        .map(|&d| src + d)
        .filter(|p| map.in_bounds(*p) && is_routable_tile(map, network, *p))
        .collect();

    // BFS from src_adj to any sink_adj tile.
    #[derive(Debug, Clone)]
    struct Node {
        f: i32,
        g: i32,
        pos: Pos,
        parent: Option<Pos>,
    }
    impl Eq for Node {}
    impl PartialEq for Node {
        fn eq(&self, o: &Self) -> bool {
            self.f == o.f
        }
    }
    impl Ord for Node {
        fn cmp(&self, o: &Self) -> std::cmp::Ordering {
            o.f.cmp(&self.f)
        }
    }
    impl PartialOrd for Node {
        fn partial_cmp(&self, o: &Self) -> Option<std::cmp::Ordering> {
            Some(self.cmp(o))
        }
    }

    let mut heap: BinaryHeap<Node> = BinaryHeap::new();
    let mut came_from: HashMap<Pos, Pos> = HashMap::new();
    let mut g_score: HashMap<Pos, i32> = HashMap::new();
    for s in &src_adj {
        let g = 0;
        let f = manhattan(*s, sink);
        heap.push(Node {
            f,
            g,
            pos: *s,
            parent: None,
        });
        g_score.insert(*s, g);
    }

    let mut found_target: Option<Pos> = None;
    while let Some(node) = heap.pop() {
        if sink_set.contains(&node.pos) {
            found_target = Some(node.pos);
            if let Some(p) = node.parent {
                came_from.insert(node.pos, p);
            }
            break;
        }
        if let Some(p) = node.parent {
            came_from.entry(node.pos).or_insert(p);
        }
        for &d in &CARDINALS {
            let next = node.pos + d;
            if !map.in_bounds(next) {
                continue;
            }
            if next == sink {
                continue; // sink is not a path tile (it's the foundry)
            }
            if !is_routable_tile(map, network, next) {
                continue;
            }
            // Contamination check: this tile's neighbours (other than
            // the path predecessor) must not carry a different type.
            if would_contaminate(map, network, next, rt) {
                continue;
            }
            let tentative_g = node.g + 1;
            if tentative_g < *g_score.get(&next).unwrap_or(&i32::MAX) {
                g_score.insert(next, tentative_g);
                heap.push(Node {
                    f: tentative_g + manhattan(next, sink),
                    g: tentative_g,
                    pos: next,
                    parent: Some(node.pos),
                });
            }
        }
    }

    let target = found_target?;
    // Reconstruct path.
    let mut path: Vec<Pos> = vec![target];
    let mut cur = target;
    while let Some(&prev) = came_from.get(&cur) {
        path.push(prev);
        cur = prev;
    }
    path.reverse();

    // Convert path to (tile, direction) pairs.
    let mut conveyors: Vec<(Pos, Direction)> = Vec::with_capacity(path.len());
    for i in 0..path.len() {
        let here = path[i];
        let next = if i + 1 < path.len() {
            path[i + 1]
        } else {
            sink
        };
        let d = direction_between(here, next)?;
        conveyors.push((here, d));
    }
    Some(Route { conveyors })
}

/// True if `t` is empty/passable and not already claimed by network.
fn is_routable_tile(map: &Map, network: &Network, t: Pos) -> bool {
    if !matches!(map.cell(t), Cell::Empty) {
        return false;
    }
    if map.is_core(t) || map.is_enemy_core(t) {
        return false;
    }
    if network.occupied(t) {
        return false;
    }
    true
}

/// True if placing a `rt`-carrying conveyor at `t` would be contaminated by
/// neighbours. A neighbour contaminates if it's a harvester / conveyor /
/// bridge / splitter carrying a different type AND it can output to `t`.
fn would_contaminate(map: &Map, network: &Network, t: Pos, rt: CarriedType) -> bool {
    for &d in &CARDINALS {
        let n = t + d;
        if !map.in_bounds(n) {
            continue;
        }
        // Check existing network entity at n.
        let Some(owner) = network.owner(n) else {
            // Empty neighbour: check if it's a different-type ore tile (would
            // become a different-type harvester later — caller's responsibility).
            // For now, ignore.
            continue;
        };
        match owner.kind {
            Kind::Harvester => {
                // Harvester at n outputs to all valid cardinals including t (if t is passable).
                // Check the harvester's resource type (from map ore).
                if let Some(harv_rt) = map.ore_at(n) {
                    let harv_carried: CarriedType = harv_rt.into();
                    if harv_carried != rt {
                        return true;
                    }
                }
            }
            Kind::Conveyor | Kind::ArmouredConveyor => {
                // Conveyor at n with direction d_out. Outputs to n + d_out.
                // If n + d_out == t, this conveyor outputs INTO t.
                // If conveyor's type != rt, contamination.
                if let Some(d_out) = owner.direction
                    && n + d_out == t
                    && let Some(neighbour_carries) = owner.carries
                    && neighbour_carries != rt
                {
                    return true;
                }
            }
            Kind::Splitter => {
                // Splitter at n with direction d. Outputs to 3 non-input cardinals.
                if let Some(d_in_dir) = owner.direction {
                    let input_dir = d_in_dir.opposite();
                    for &od in &CARDINALS {
                        if od == input_dir {
                            continue;
                        }
                        if n + od == t
                            && let Some(neighbour_carries) = owner.carries
                            && neighbour_carries != rt
                        {
                            return true;
                        }
                    }
                }
            }
            Kind::Bridge => {
                // Bridge at n teleports to bridge_target. Doesn't output to neighbours.
                // No contamination from bridges.
            }
            _ => {}
        }
    }
    false
}

fn direction_between(from: Pos, to: Pos) -> Option<Direction> {
    let dx = to.x - from.x;
    let dy = to.y - from.y;
    match (dx, dy) {
        (0, -1) => Some(Direction::North),
        (1, 0) => Some(Direction::East),
        (0, 1) => Some(Direction::South),
        (-1, 0) => Some(Direction::West),
        _ => None,
    }
}

/// Place a harvester at `pos` (must be ore) and route conveyors from there
/// to `sink_foundry`. Adds all placements to `network`. Returns Err on
/// failure (e.g., no route found).
pub fn place_harvester_with_route(
    map: &Map,
    network: &mut Network,
    pos: Pos,
    sink: Pos,
) -> Result<(), String> {
    let rt: CarriedType = map
        .ore_at(pos)
        .ok_or_else(|| format!("{pos:?} is not an ore tile"))?
        .into();
    // Fast path: if a cardinal neighbour is already a conveyor/foundry that
    // accepts our resource and ultimately reaches `sink`, just place the
    // harvester — the existing chain delivers it.
    if has_compatible_neighbour(map, network, pos, sink, rt) {
        return network.place(
            Placement {
                pos,
                kind: Kind::Harvester,
                direction: None,
                bridge_target: None,
                line: 0,
            },
            Some(rt),
        );
    }
    let route = route(map, network, pos, sink, rt)
        .ok_or_else(|| format!("no route from {pos:?} to {sink:?} for {rt:?}"))?;
    network.place(
        Placement {
            pos,
            kind: Kind::Harvester,
            direction: None,
            bridge_target: None,
            line: 0,
        },
        Some(rt),
    )?;
    for (tile, dir) in route.conveyors {
        network.place(
            Placement {
                pos: tile,
                kind: Kind::Conveyor,
                direction: Some(dir),
                bridge_target: None,
                line: 0,
            },
            Some(rt),
        )?;
    }
    Ok(())
}

/// Check if a harvester at `pos` has any cardinal neighbour that's either
/// (a) the sink foundry directly, or (b) a same-type conveyor whose chain
/// terminates at sink.
fn has_compatible_neighbour(
    map: &Map,
    network: &Network,
    pos: Pos,
    sink: Pos,
    rt: CarriedType,
) -> bool {
    for &d in &CARDINALS {
        let n = pos + d;
        if !map.in_bounds(n) {
            continue;
        }
        if n == sink {
            return true;
        }
        let Some(owner) = network.owner(n) else {
            continue;
        };
        // Conveyor at n: accepts from cardinal d.opposite() iff its output
        // direction != d.opposite(). And its carries must match rt.
        if matches!(owner.kind, Kind::Conveyor | Kind::ArmouredConveyor) {
            let Some(conv_dir) = owner.direction else {
                continue;
            };
            // Does this conveyor accept from `pos` (which is `d.opposite()` of n)?
            let from_dir = d.opposite();
            if from_dir == conv_dir {
                continue; // Output side, won't accept
            }
            if owner.carries != Some(rt) {
                continue; // wrong type
            }
            if chain_reaches_sink(network, n, sink) {
                return true;
            }
        }
    }
    false
}

/// Follow the conveyor chain starting at `start` (assumed to be a placed
/// conveyor) — does it terminate at `sink`?
fn chain_reaches_sink(network: &Network, start: Pos, sink: Pos) -> bool {
    let mut cur = start;
    let mut seen = HashSet::new();
    loop {
        if cur == sink {
            return true;
        }
        if !seen.insert(cur) {
            return false; // cycle
        }
        let Some(owner) = network.owner(cur) else {
            return false;
        };
        match owner.kind {
            Kind::Conveyor | Kind::ArmouredConveyor => {
                let Some(d) = owner.direction else {
                    return false;
                };
                cur = cur + d;
            }
            Kind::Bridge => {
                let Some(t) = owner.bridge_target else {
                    return false;
                };
                cur = t;
            }
            Kind::Foundry => return cur == sink,
            _ => return false,
        }
    }
}

/// Place a foundry at `pos`. The foundry tile must be empty and not core.
pub fn place_foundry(network: &mut Network, pos: Pos) -> Result<(), String> {
    network.place(
        Placement {
            pos,
            kind: Kind::Foundry,
            direction: None,
            bridge_target: None,
            line: 0,
        },
        None,
    )
}

/// Route refined ax from `foundry` to a tile cardinal-adjacent to `core_centre`.
/// The route enters the core 3x3 footprint at any side.
pub fn route_foundry_to_core(
    map: &Map,
    network: &mut Network,
    foundry: Pos,
) -> Result<(), String> {
    let core = map.core_a;
    // The "sink set" is any tile of the 3x3 core. We need a conveyor that
    // outputs INTO a core tile. So target = empty tile cardinal-adjacent to
    // core 3x3, and route from foundry.
    let rt = CarriedType::RefinedAxionite;
    // BFS from foundry's neighbours to any core-adjacent empty tile.
    // We treat the foundry itself as the source: outputs to all 4 cardinals.
    let route = route_to_core(map, network, foundry, rt)
        .ok_or_else(|| format!("no refined-ax route from {foundry:?} to core"))?;
    for (tile, dir) in route.conveyors {
        network.place(
            Placement {
                pos: tile,
                kind: Kind::Conveyor,
                direction: Some(dir),
                bridge_target: None,
                line: 0,
            },
            Some(rt),
        )?;
    }
    Ok(())
}

fn route_to_core(map: &Map, network: &Network, src: Pos, rt: CarriedType) -> Option<Route> {
    let manhattan = |a: Pos, b: Pos| -> i32 { (a.x - b.x).abs() + (a.y - b.y).abs() };

    // Sink: any empty tile cardinal-adjacent to a core tile, where placing
    // a conveyor facing toward the core would deliver.
    let mut sink_tiles: Vec<(Pos, Direction)> = Vec::new();
    for cy in -1..=1 {
        for cx in -1..=1 {
            let ct = Pos {
                x: map.core_a.x + cx,
                y: map.core_a.y + cy,
            };
            for &d in &CARDINALS {
                let t = ct + d.opposite();
                if map.is_core(t) {
                    continue;
                }
                if !map.in_bounds(t) {
                    continue;
                }
                if !is_routable_tile(map, network, t) {
                    continue;
                }
                sink_tiles.push((t, d));
            }
        }
    }
    let sink_set: HashSet<Pos> = sink_tiles.iter().map(|(t, _)| *t).collect();

    // Start from cardinal neighbours of `src`.
    let starts: Vec<Pos> = CARDINALS
        .iter()
        .map(|&d| src + d)
        .filter(|p| map.in_bounds(*p) && is_routable_tile(map, network, *p))
        .collect();

    #[derive(Clone)]
    struct Node {
        f: i32,
        g: i32,
        pos: Pos,
    }
    impl Eq for Node {}
    impl PartialEq for Node {
        fn eq(&self, o: &Self) -> bool {
            self.f == o.f
        }
    }
    impl Ord for Node {
        fn cmp(&self, o: &Self) -> std::cmp::Ordering {
            o.f.cmp(&self.f)
        }
    }
    impl PartialOrd for Node {
        fn partial_cmp(&self, o: &Self) -> Option<std::cmp::Ordering> {
            Some(self.cmp(o))
        }
    }

    let mut heap: BinaryHeap<Node> = BinaryHeap::new();
    let mut came_from: HashMap<Pos, Pos> = HashMap::new();
    let mut g_score: HashMap<Pos, i32> = HashMap::new();
    for s in &starts {
        let f = manhattan(*s, map.core_a);
        heap.push(Node { f, g: 0, pos: *s });
        g_score.insert(*s, 0);
    }

    let mut found: Option<Pos> = None;
    while let Some(node) = heap.pop() {
        if sink_set.contains(&node.pos) {
            found = Some(node.pos);
            break;
        }
        for &d in &CARDINALS {
            let next = node.pos + d;
            if !map.in_bounds(next) {
                continue;
            }
            if !is_routable_tile(map, network, next) {
                continue;
            }
            if would_contaminate(map, network, next, rt) {
                continue;
            }
            let tg = node.g + 1;
            if tg < *g_score.get(&next).unwrap_or(&i32::MAX) {
                g_score.insert(next, tg);
                came_from.insert(next, node.pos);
                let f = tg + manhattan(next, map.core_a);
                heap.push(Node { f, g: tg, pos: next });
            }
        }
    }

    let target = found?;
    let mut path: Vec<Pos> = vec![target];
    let mut cur = target;
    while let Some(&prev) = came_from.get(&cur) {
        path.push(prev);
        cur = prev;
    }
    path.reverse();

    // Convert path to (tile, direction). First tile's direction points away
    // from src toward path[1] (or core if path has just 1 element).
    let mut conveyors: Vec<(Pos, Direction)> = Vec::with_capacity(path.len());
    for i in 0..path.len() {
        let here = path[i];
        let next = if i + 1 < path.len() {
            path[i + 1]
        } else {
            // Last tile: face toward core (the entry tile of the core 3x3).
            // Find which core tile is cardinal-adjacent.
            let mut next_dir = None;
            for &d in &CARDINALS {
                let nt = here + d;
                if map.is_core(nt) {
                    next_dir = Some(d);
                    break;
                }
            }
            return Some(Route {
                conveyors: {
                    conveyors.push((here, next_dir.unwrap()));
                    conveyors
                },
            });
        };
        let d = direction_between(here, next)?;
        conveyors.push((here, d));
    }
    Some(Route { conveyors })
}

/// Render the network's placements to a `.bp` text format string.
pub fn render_bp(network: &Network) -> String {
    let mut out = String::new();
    for p in &network.placements {
        let kind_str = match p.kind {
            Kind::Conveyor => "CONVEYOR",
            Kind::Splitter => "SPLITTER",
            Kind::ArmouredConveyor => "ARMOURED_CONVEYOR",
            Kind::Bridge => "BRIDGE",
            Kind::Harvester => "HARVESTER",
            Kind::Foundry => "FOUNDRY",
            Kind::Road => "ROAD",
            Kind::Barrier => "BARRIER",
        };
        out.push_str(&format!("{} {} {}", p.pos.x, p.pos.y, kind_str));
        if let Some(d) = p.direction {
            let ds = match d {
                Direction::North => "NORTH",
                Direction::East => "EAST",
                Direction::South => "SOUTH",
                Direction::West => "WEST",
                Direction::Northeast => "NORTHEAST",
                Direction::Southeast => "SOUTHEAST",
                Direction::Southwest => "SOUTHWEST",
                Direction::Northwest => "NORTHWEST",
                Direction::Centre => "CENTRE",
            };
            out.push_str(&format!(" dir={}", ds));
        }
        if let Some(bt) = p.bridge_target {
            out.push_str(&format!(" bridge={},{}", bt.x, bt.y));
        }
        out.push('\n');
    }
    out
}
