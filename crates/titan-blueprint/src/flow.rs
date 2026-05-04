//! Static flow analysis on a blueprint placement.
//!
//! Builds a directed graph from the placed entities and propagates
//! resource flow rates by fixed-point iteration. Closed-form, no
//! simulation. Use to drive an editor overlay (per-edge thickness/colour,
//! per-tile contamination, per-foundry rate).

use std::collections::BTreeMap;
use std::collections::BTreeSet;
use std::collections::HashMap;

use crate::blueprint::{BlueprintEntry, CARDINALS, Direction, Entity};
use crate::map::{MapData, Tile};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResourceType {
    Titanium,
    RawAxionite,
    RefinedAxionite,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum CarriedType {
    Titanium,
    RawAxionite,
    RefinedAxionite,
    /// Tile's storage rotates between two or more resource types.
    Mixed,
}

impl From<ResourceType> for CarriedType {
    fn from(r: ResourceType) -> Self {
        match r {
            ResourceType::Titanium => Self::Titanium,
            ResourceType::RawAxionite => Self::RawAxionite,
            ResourceType::RefinedAxionite => Self::RefinedAxionite,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NodeKind {
    Harvester(ResourceType),
    Foundry,
    Core,
    Conveyor(Direction),
    Splitter(Direction),
    ArmouredConveyor(Direction),
    Bridge((i32, i32)),
    Other,
}

#[derive(Debug, Clone)]
pub struct Node {
    pub pos: (i32, i32),
    pub kind: NodeKind,
}

#[derive(Debug, Clone)]
pub struct Topology {
    pub nodes: BTreeMap<(i32, i32), Node>,
    pub out_edges: BTreeMap<(i32, i32), Vec<(i32, i32)>>,
    pub in_edges: BTreeMap<(i32, i32), Vec<(i32, i32)>>,
}

#[derive(Debug, Clone)]
pub struct FlowResult {
    pub topology: Topology,
    pub edge_flow: HashMap<((i32, i32), (i32, i32)), HashMap<CarriedType, f64>>,
    pub tile_carries: HashMap<(i32, i32), CarriedType>,
    pub contaminated: BTreeSet<(i32, i32)>,
    pub foundry_rate: BTreeMap<(i32, i32), f64>,
}

pub fn analyze(entries: &[BlueprintEntry], map: &MapData) -> FlowResult {
    let topology = build_topology(entries, map);
    let (edge_flow, tile_carries, contaminated) = propagate_flow(&topology);
    let foundry_rate = compute_foundry_rates(&topology, &edge_flow);
    FlowResult {
        topology,
        edge_flow,
        tile_carries,
        contaminated,
        foundry_rate,
    }
}

fn add(p: (i32, i32), d: Direction) -> (i32, i32) {
    let (dx, dy) = d.delta();
    (p.0 + dx, p.1 + dy)
}

fn build_topology(entries: &[BlueprintEntry], map: &MapData) -> Topology {
    let mut nodes: BTreeMap<(i32, i32), Node> = BTreeMap::new();
    for e in entries {
        let kind = match e.kind {
            Entity::Harvester => {
                let rt = match map.tile(e.pos.0, e.pos.1) {
                    Tile::OreTitanium => ResourceType::Titanium,
                    Tile::OreAxionite => ResourceType::RawAxionite,
                    _ => continue, // harvester not on ore — invalid
                };
                NodeKind::Harvester(rt)
            }
            Entity::Foundry => NodeKind::Foundry,
            Entity::Conveyor => NodeKind::Conveyor(e.direction.unwrap_or(Direction::North)),
            Entity::ArmouredConveyor => {
                NodeKind::ArmouredConveyor(e.direction.unwrap_or(Direction::North))
            }
            Entity::Splitter => NodeKind::Splitter(e.direction.unwrap_or(Direction::North)),
            Entity::Bridge => NodeKind::Bridge(e.bridge_target.unwrap_or(e.pos)),
            // Roads, barriers, turrets are flow-opaque.
            Entity::Road
            | Entity::Barrier
            | Entity::Gunner
            | Entity::Sentinel
            | Entity::Breach
            | Entity::Launcher => NodeKind::Other,
        };
        nodes.insert(e.pos, Node { pos: e.pos, kind });
    }
    // Add core 3x3 tiles.
    for c in [map.core_a, map.core_b] {
        for dy in -1..=1 {
            for dx in -1..=1 {
                let p = (c.0 + dx, c.1 + dy);
                nodes.insert(p, Node { pos: p, kind: NodeKind::Core });
            }
        }
    }

    let in_bounds = |p: (i32, i32)| p.0 >= 0 && p.1 >= 0 && p.0 < map.w && p.1 < map.h;

    let mut out_edges: BTreeMap<(i32, i32), Vec<(i32, i32)>> = BTreeMap::new();
    let mut in_edges: BTreeMap<(i32, i32), Vec<(i32, i32)>> = BTreeMap::new();

    for (pos, node) in &nodes {
        let outs = compute_outputs(node, &nodes, in_bounds);
        for &dst in &outs {
            if !accepts_from(&nodes, dst, *pos) {
                continue;
            }
            out_edges.entry(*pos).or_default().push(dst);
            in_edges.entry(dst).or_default().push(*pos);
        }
    }

    Topology { nodes, out_edges, in_edges }
}

fn compute_outputs(
    node: &Node,
    nodes: &BTreeMap<(i32, i32), Node>,
    in_bounds: impl Fn((i32, i32)) -> bool,
) -> Vec<(i32, i32)> {
    match node.kind {
        NodeKind::Conveyor(d) | NodeKind::ArmouredConveyor(d) => {
            let p = add(node.pos, d);
            if in_bounds(p) && nodes.contains_key(&p) {
                vec![p]
            } else {
                vec![]
            }
        }
        NodeKind::Splitter(d) => {
            let input = d.opposite();
            CARDINALS
                .iter()
                .copied()
                .filter(|&c| c != input)
                .map(|c| add(node.pos, c))
                .filter(|p| in_bounds(*p) && nodes.contains_key(p))
                .collect()
        }
        NodeKind::Bridge(target) => {
            if in_bounds(target) && nodes.contains_key(&target) {
                vec![target]
            } else {
                vec![]
            }
        }
        NodeKind::Harvester(_) | NodeKind::Foundry => CARDINALS
            .iter()
            .copied()
            .map(|c| add(node.pos, c))
            .filter(|p| in_bounds(*p) && nodes.contains_key(p))
            .collect(),
        NodeKind::Core | NodeKind::Other => vec![],
    }
}

fn accepts_from(nodes: &BTreeMap<(i32, i32), Node>, dst: (i32, i32), src: (i32, i32)) -> bool {
    let Some(node) = nodes.get(&dst) else {
        return false;
    };
    let from_dir = direction_from(src, dst);
    if from_dir.is_none() {
        // Non-cardinal source = bridge teleport.
        return matches!(
            node.kind,
            NodeKind::Bridge(_)
                | NodeKind::Foundry
                | NodeKind::Core
                | NodeKind::Conveyor(_)
                | NodeKind::ArmouredConveyor(_)
                | NodeKind::Splitter(_)
        );
    }
    let from = from_dir.unwrap();
    match node.kind {
        NodeKind::Conveyor(d) | NodeKind::ArmouredConveyor(d) => from != d,
        NodeKind::Splitter(d) => from == d.opposite(),
        NodeKind::Bridge(_) | NodeKind::Foundry | NodeKind::Core => true,
        NodeKind::Harvester(_) | NodeKind::Other => false,
    }
}

impl Direction {
    pub const fn opposite(self) -> Self {
        match self {
            Self::North => Self::South,
            Self::NorthEast => Self::SouthWest,
            Self::East => Self::West,
            Self::SouthEast => Self::NorthWest,
            Self::South => Self::North,
            Self::SouthWest => Self::NorthEast,
            Self::West => Self::East,
            Self::NorthWest => Self::SouthEast,
        }
    }
}

fn direction_from(src: (i32, i32), dst: (i32, i32)) -> Option<Direction> {
    let dx = dst.0 - src.0;
    let dy = dst.1 - src.1;
    Direction::from_delta(-dx, -dy)
}

fn propagate_flow(
    topology: &Topology,
) -> (
    HashMap<((i32, i32), (i32, i32)), HashMap<CarriedType, f64>>,
    HashMap<(i32, i32), CarriedType>,
    BTreeSet<(i32, i32)>,
) {
    let mut edge_flow: HashMap<((i32, i32), (i32, i32)), HashMap<CarriedType, f64>> = HashMap::new();
    for (pos, node) in &topology.nodes {
        let NodeKind::Harvester(rt) = node.kind else { continue };
        let outs = topology.out_edges.get(pos).cloned().unwrap_or_default();
        if outs.is_empty() {
            continue;
        }
        let per = 0.25 / outs.len() as f64;
        for dst in outs {
            edge_flow
                .entry((*pos, dst))
                .or_default()
                .entry(rt.into())
                .and_modify(|v| *v += per)
                .or_insert(per);
        }
    }

    let mut tile_carries: HashMap<(i32, i32), CarriedType> = HashMap::new();
    for _ in 0..200 {
        let mut next: HashMap<((i32, i32), (i32, i32)), HashMap<CarriedType, f64>> =
            HashMap::new();
        for ((src, dst), m) in &edge_flow {
            if matches!(
                topology.nodes.get(src).map(|n| n.kind),
                Some(NodeKind::Harvester(_))
            ) {
                next.insert((*src, *dst), m.clone());
            }
        }
        for (pos, node) in &topology.nodes {
            let outs = topology.out_edges.get(pos).cloned().unwrap_or_default();
            if outs.is_empty() {
                continue;
            }
            let mut incoming: HashMap<CarriedType, f64> = HashMap::new();
            for src in topology.in_edges.get(pos).cloned().unwrap_or_default() {
                if let Some(m) = edge_flow.get(&(src, *pos)) {
                    for (t, v) in m {
                        *incoming.entry(*t).or_default() += v;
                    }
                }
            }
            let total: f64 = incoming.values().sum();
            let scale = if total > 1.0 { 1.0 / total } else { 1.0 };
            let capped: HashMap<CarriedType, f64> =
                incoming.iter().map(|(t, v)| (*t, v * scale)).collect();
            tile_carries.insert(*pos, dominant_type(&capped));

            match node.kind {
                NodeKind::Conveyor(_)
                | NodeKind::ArmouredConveyor(_)
                | NodeKind::Bridge(_) => {
                    let dst = outs[0];
                    next.insert((*pos, dst), capped);
                }
                NodeKind::Splitter(_) => {
                    let n = outs.len() as f64;
                    if n > 0.0 {
                        let per: HashMap<CarriedType, f64> =
                            capped.iter().map(|(t, v)| (*t, v / n)).collect();
                        for dst in outs {
                            next.insert((*pos, dst), per.clone());
                        }
                    }
                }
                NodeKind::Foundry => {
                    let ti = capped.get(&CarriedType::Titanium).copied().unwrap_or(0.0);
                    let raw = capped.get(&CarriedType::RawAxionite).copied().unwrap_or(0.0);
                    let combine = ti.min(raw).min(1.0);
                    let pre = capped
                        .get(&CarriedType::RefinedAxionite)
                        .copied()
                        .unwrap_or(0.0);
                    let total_ref = (combine + pre).min(1.0);
                    if total_ref > 0.0 {
                        let n = outs.len() as f64;
                        let per = total_ref / n;
                        for dst in outs {
                            next.entry((*pos, dst))
                                .or_default()
                                .insert(CarriedType::RefinedAxionite, per);
                        }
                    }
                }
                NodeKind::Harvester(_) | NodeKind::Core | NodeKind::Other => {}
            }
        }
        if flows_equal(&edge_flow, &next) {
            edge_flow = next;
            break;
        }
        edge_flow = next;
    }

    let mut contaminated: BTreeSet<(i32, i32)> = BTreeSet::new();
    for (pos, node) in &topology.nodes {
        if matches!(node.kind, NodeKind::Foundry | NodeKind::Core) {
            continue;
        }
        let is_pipe = matches!(
            node.kind,
            NodeKind::Conveyor(_)
                | NodeKind::ArmouredConveyor(_)
                | NodeKind::Splitter(_)
                | NodeKind::Bridge(_)
        );
        if !is_pipe {
            continue;
        }
        let mut types_seen: BTreeSet<CarriedType> = BTreeSet::new();
        for src in topology.in_edges.get(pos).cloned().unwrap_or_default() {
            if let Some(m) = edge_flow.get(&(src, *pos)) {
                for t in m.keys() {
                    if *t != CarriedType::Mixed {
                        types_seen.insert(*t);
                    }
                }
            }
        }
        if types_seen.len() > 1 {
            contaminated.insert(*pos);
        }
    }
    (edge_flow, tile_carries, contaminated)
}

fn dominant_type(m: &HashMap<CarriedType, f64>) -> CarriedType {
    if m.len() > 1 {
        return CarriedType::Mixed;
    }
    m.iter().next().map(|(t, _)| *t).unwrap_or(CarriedType::Mixed)
}

fn flows_equal(
    a: &HashMap<((i32, i32), (i32, i32)), HashMap<CarriedType, f64>>,
    b: &HashMap<((i32, i32), (i32, i32)), HashMap<CarriedType, f64>>,
) -> bool {
    if a.len() != b.len() {
        return false;
    }
    for (k, va) in a {
        let Some(vb) = b.get(k) else { return false };
        if va.len() != vb.len() {
            return false;
        }
        for (t, v) in va {
            let bv = vb.get(t).copied().unwrap_or(0.0);
            if (v - bv).abs() > 1e-6 {
                return false;
            }
        }
    }
    true
}

fn compute_foundry_rates(
    topology: &Topology,
    edge_flow: &HashMap<((i32, i32), (i32, i32)), HashMap<CarriedType, f64>>,
) -> BTreeMap<(i32, i32), f64> {
    let mut out = BTreeMap::new();
    for (pos, node) in &topology.nodes {
        if !matches!(node.kind, NodeKind::Foundry) {
            continue;
        }
        let mut ti = 0.0;
        let mut raw = 0.0;
        for src in topology.in_edges.get(pos).cloned().unwrap_or_default() {
            if let Some(m) = edge_flow.get(&(src, *pos)) {
                ti += m.get(&CarriedType::Titanium).copied().unwrap_or(0.0);
                raw += m.get(&CarriedType::RawAxionite).copied().unwrap_or(0.0);
            }
        }
        out.insert(*pos, ti.min(raw).min(1.0));
    }
    out
}
