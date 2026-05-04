//! Static type-coloured flow analysis on a `.bp` placement.
//!
//! Models the steady-state distribution as a directed graph:
//! - Nodes: tiles with placed entities (+ implicit core tiles).
//! - Edges: source → sink directed by entity rules. Each source distributes
//!   its production equally (LRU rotation) across all valid sink-edges.
//! - Capacities: every edge carries ≤ 1 stack/turn; each conveyor/splitter/
//!   bridge stores ≤ 1 stack/turn out.
//! - Resource types: Titanium, RawAxionite, RefinedAxionite. A conveyor's
//!   carried-type is determined by what flows in. If multiple types arrive,
//!   the conveyor is *contaminated* — its single-slot store rotates between
//!   types and the downstream sink sees mixed stacks (foundries clog,
//!   wrong-type ammo, etc.).
//!
//! This module computes:
//! - `topology`: node and edge sets.
//! - `flow`: per-edge stacks/turn carrying (resource_type, rate).
//! - `contamination`: list of nodes whose effective input mixes types.
//! - `foundry_throughput`: per-foundry refined-ax production rate (= min
//!   of incoming Ti rate and incoming RawAx rate, capped at 1 stack/turn).

use std::collections::BTreeMap;
use std::collections::BTreeSet;
use std::collections::HashMap;

use libre_engine::common::{Direction, Pos, ResourceType};

use crate::blueprint::{Kind, Placement};

/// Cardinal directions, in canonical order for stable iteration.
const CARDINALS: [Direction; 4] = [
    Direction::North,
    Direction::East,
    Direction::South,
    Direction::West,
];

/// Type a tile carries in steady state. `Mixed` = contamination.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum CarriedType {
    Titanium,
    RawAxionite,
    RefinedAxionite,
    /// Conveyor's stored slot rotates between two or more resource types.
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum NodeKind {
    Harvester(ResourceType),
    Foundry,
    Core,
    Conveyor(Direction),
    Splitter(Direction),
    ArmouredConveyor(Direction),
    Bridge(Pos), // target
    Other,       // road, barrier, etc — opaque to flow
}

#[derive(Debug, Clone)]
pub struct Node {
    pub pos: Pos,
    pub kind: NodeKind,
}

#[derive(Debug, Clone)]
pub struct Edge {
    pub from: Pos,
    pub to: Pos,
}

#[derive(Debug, Clone)]
pub struct Topology {
    pub nodes: BTreeMap<Pos, Node>,
    /// Outgoing edges per node.
    pub out_edges: BTreeMap<Pos, Vec<Pos>>,
    /// Incoming edges per node.
    pub in_edges: BTreeMap<Pos, Vec<Pos>>,
}

#[derive(Debug, Clone)]
pub struct FlowResult {
    pub topology: Topology,
    /// Stacks/turn flowing on each edge, by resource type. Multiple types
    /// per edge ⇒ contamination at the destination.
    pub edge_flow: HashMap<(Pos, Pos), HashMap<CarriedType, f64>>,
    /// Per-tile carried type in steady state.
    pub tile_carries: HashMap<Pos, CarriedType>,
    /// Conveyor/splitter/bridge tiles with mixed-type input.
    pub contaminated: BTreeSet<Pos>,
    /// Per-foundry refined-ax production rate (stacks/turn, capped at 1.0).
    pub foundry_rate: BTreeMap<Pos, f64>,
}

/// Build the topology + propagate flow for a placement on a 50x35 map.
/// `cores` is the list of core *centre* tiles for team A.
pub fn analyze(
    placements: &[Placement],
    cores: &[Pos],
    width: i32,
    height: i32,
) -> FlowResult {
    let topology = build_topology(placements, cores, width, height);
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

fn build_topology(
    placements: &[Placement],
    cores: &[Pos],
    width: i32,
    height: i32,
) -> Topology {
    let mut nodes: BTreeMap<Pos, Node> = BTreeMap::new();
    for p in placements {
        let kind = match p.kind {
            Kind::Harvester => {
                // Resource type derives from the underlying ore (caller must
                // have validated this); but blueprints are placed on ore
                // tiles, so we'll resolve below in propagate. For now, mark
                // as Other and let a later pass tag the resource. Simpler:
                // require the caller to pass map env, but to keep this
                // module pure, store `Other` and fix at sim integration.
                // — Here we cheat: harvester resource will be filled in by
                // a separate pass that consults the map. For now stash as
                // Harvester(Titanium) and let `analyze_with_map` overwrite.
                NodeKind::Harvester(ResourceType::Titanium)
            }
            Kind::Foundry => NodeKind::Foundry,
            Kind::Conveyor => NodeKind::Conveyor(p.direction.unwrap()),
            Kind::ArmouredConveyor => NodeKind::ArmouredConveyor(p.direction.unwrap()),
            Kind::Splitter => NodeKind::Splitter(p.direction.unwrap()),
            Kind::Bridge => NodeKind::Bridge(p.bridge_target.unwrap()),
            Kind::Road | Kind::Barrier => NodeKind::Other,
        };
        nodes.insert(p.pos, Node { pos: p.pos, kind });
    }
    // Add core 3x3 tiles as Core nodes.
    for c in cores {
        for dy in -1..=1 {
            for dx in -1..=1 {
                let pos = Pos {
                    x: c.x + dx,
                    y: c.y + dy,
                };
                nodes.insert(pos, Node { pos, kind: NodeKind::Core });
            }
        }
    }

    let in_bounds = |p: Pos| p.x >= 0 && p.y >= 0 && p.x < width && p.y < height;

    let mut out_edges: BTreeMap<Pos, Vec<Pos>> = BTreeMap::new();
    let mut in_edges: BTreeMap<Pos, Vec<Pos>> = BTreeMap::new();

    for (pos, node) in &nodes {
        let outs = compute_outputs(node, &nodes, in_bounds);
        for &dst in &outs {
            // Verify dst can accept from this src direction.
            if !accepts_from(&nodes, dst, *pos) {
                continue;
            }
            out_edges.entry(*pos).or_default().push(dst);
            in_edges.entry(dst).or_default().push(*pos);
        }
    }

    Topology {
        nodes,
        out_edges,
        in_edges,
    }
}

/// Compute the set of positions a node can output to (geometric only).
fn compute_outputs(
    node: &Node,
    nodes: &BTreeMap<Pos, Node>,
    in_bounds: impl Fn(Pos) -> bool,
) -> Vec<Pos> {
    match node.kind {
        NodeKind::Conveyor(d) | NodeKind::ArmouredConveyor(d) => {
            let p = node.pos + d;
            if in_bounds(p) && nodes.contains_key(&p) {
                vec![p]
            } else {
                vec![]
            }
        }
        NodeKind::Splitter(d) => {
            // Outputs to 3 cardinals excluding input dir = d.opposite()
            let input = d.opposite();
            CARDINALS
                .iter()
                .copied()
                .filter(|&c| c != input)
                .map(|c| node.pos + c)
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
        NodeKind::Harvester(_) => CARDINALS
            .iter()
            .copied()
            .map(|c| node.pos + c)
            .filter(|p| in_bounds(*p) && nodes.contains_key(p))
            .collect(),
        NodeKind::Foundry => CARDINALS
            .iter()
            .copied()
            .map(|c| node.pos + c)
            .filter(|p| in_bounds(*p) && nodes.contains_key(p))
            .collect(),
        NodeKind::Core | NodeKind::Other => vec![],
    }
}

/// Whether `dst` accepts a stack arriving from `src`.
fn accepts_from(nodes: &BTreeMap<Pos, Node>, dst: Pos, src: Pos) -> bool {
    let Some(node) = nodes.get(&dst) else {
        return false;
    };
    let from_dir = if let Some(d) = direction_from(src, dst) {
        d
    } else {
        // Non-cardinal source ⇒ must be a bridge (teleport, accepts always).
        return matches!(
            node.kind,
            NodeKind::Bridge(_)
                | NodeKind::Foundry
                | NodeKind::Core
                | NodeKind::Conveyor(_)
                | NodeKind::ArmouredConveyor(_)
                | NodeKind::Splitter(_)
        );
    };
    match node.kind {
        NodeKind::Conveyor(d) | NodeKind::ArmouredConveyor(d) => from_dir != d,
        NodeKind::Splitter(d) => from_dir == d.opposite(),
        NodeKind::Bridge(_) | NodeKind::Foundry | NodeKind::Core => true,
        NodeKind::Harvester(_) | NodeKind::Other => false,
    }
}

fn direction_from(src: Pos, dst: Pos) -> Option<Direction> {
    let dx = dst.x - src.x;
    let dy = dst.y - src.y;
    match (dx, dy) {
        (0, -1) => Some(Direction::South),  // src is south of dst → arrives from south
        (0, 1) => Some(Direction::North),   // src is north of dst → arrives from north
        (-1, 0) => Some(Direction::East),
        (1, 0) => Some(Direction::West),
        _ => None,
    }
}

/// Propagate flows through the topology. Returns per-edge flow by type,
/// per-tile carried type, and contaminated tile set.
///
/// Algorithm: fixed-point iteration on per-edge resource type/rate.
/// At each iteration, for each source node (harvester / bridge / conveyor /
/// splitter), recompute outgoing flow distribution based on current input.
fn propagate_flow(
    topology: &Topology,
) -> (
    HashMap<(Pos, Pos), HashMap<CarriedType, f64>>,
    HashMap<Pos, CarriedType>,
    BTreeSet<Pos>,
) {
    let mut edge_flow: HashMap<(Pos, Pos), HashMap<CarriedType, f64>> = HashMap::new();
    // Initialise: harvester outputs distributed equally among out-neighbours.
    // Harvester per-turn output: 0.25 stacks (1 stack / 4 turns).
    for (pos, node) in &topology.nodes {
        let NodeKind::Harvester(rt) = node.kind else {
            continue;
        };
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

    // Now propagate through conveyors / splitters / bridges. A node's
    // outgoing rate equals min(sum of incoming, 1.0) (storage cap), split
    // among valid outputs by their distribution rule.
    //
    // Iterate until stable.
    let mut tile_carries: HashMap<Pos, CarriedType> = HashMap::new();
    for _iter in 0..200 {
        let mut next_flow: HashMap<(Pos, Pos), HashMap<CarriedType, f64>> = HashMap::new();
        // Re-add harvester edges (sources don't change).
        for ((src, dst), m) in &edge_flow {
            if matches!(
                topology.nodes.get(src).map(|n| n.kind),
                Some(NodeKind::Harvester(_))
            ) {
                next_flow.insert((*src, *dst), m.clone());
            }
        }
        for (pos, node) in &topology.nodes {
            let outs = topology.out_edges.get(pos).cloned().unwrap_or_default();
            if outs.is_empty() {
                continue;
            }
            // Aggregate inputs by type from edge_flow.
            let mut incoming: HashMap<CarriedType, f64> = HashMap::new();
            for src in topology.in_edges.get(pos).cloned().unwrap_or_default() {
                if let Some(m) = edge_flow.get(&(src, *pos)) {
                    for (t, v) in m {
                        *incoming.entry(*t).or_default() += v;
                    }
                }
            }
            // Cap total at 1 stack/turn (storage capacity).
            let total: f64 = incoming.values().sum();
            let scale = if total > 1.0 { 1.0 / total } else { 1.0 };
            let capped: HashMap<CarriedType, f64> = incoming
                .iter()
                .map(|(t, v)| (*t, v * scale))
                .collect();
            tile_carries.insert(*pos, dominant_type(&capped));

            match node.kind {
                NodeKind::Conveyor(_) | NodeKind::ArmouredConveyor(_) => {
                    // Conveyor: 1 output direction. All capped throughput goes there.
                    let dst = outs[0];
                    next_flow.insert((*pos, dst), capped);
                }
                NodeKind::Splitter(_) => {
                    // Splitter: capped throughput split equally among out-edges.
                    let n = outs.len() as f64;
                    if n > 0.0 {
                        let per: HashMap<CarriedType, f64> =
                            capped.iter().map(|(t, v)| (*t, v / n)).collect();
                        for dst in outs {
                            next_flow.insert((*pos, dst), per.clone());
                        }
                    }
                }
                NodeKind::Bridge(_) => {
                    // Bridge: teleports to single target. All capped goes there.
                    let dst = outs[0];
                    next_flow.insert((*pos, dst), capped);
                }
                NodeKind::Foundry => {
                    // Foundry combines incoming Ti + RawAx into RefAx, and
                    // outputs RefAx. Incoming RefAx passes through (rare).
                    let ti = capped.get(&CarriedType::Titanium).copied().unwrap_or(0.0);
                    let raw = capped.get(&CarriedType::RawAxionite).copied().unwrap_or(0.0);
                    let combine = ti.min(raw).min(1.0);
                    let pre = capped
                        .get(&CarriedType::RefinedAxionite)
                        .copied()
                        .unwrap_or(0.0);
                    let total_ref = (combine + pre).min(1.0);
                    if total_ref > 0.0 {
                        // Output to all valid outs (LRU split).
                        let n = outs.len() as f64;
                        let per = total_ref / n;
                        for dst in outs {
                            next_flow
                                .entry((*pos, dst))
                                .or_default()
                                .insert(CarriedType::RefinedAxionite, per);
                        }
                    }
                }
                NodeKind::Harvester(_) | NodeKind::Core | NodeKind::Other => {}
            }
        }
        // Convergence check.
        if flows_equal(&edge_flow, &next_flow) {
            edge_flow = next_flow;
            break;
        }
        edge_flow = next_flow;
    }

    let mut contaminated: BTreeSet<Pos> = BTreeSet::new();
    for (pos, node) in &topology.nodes {
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
        // Foundries legitimately receive both Ti and RawAx; that's not contamination.
        let is_foundry = matches!(node.kind, NodeKind::Foundry);
        if is_foundry {
            // Contamination only if RefinedAx arrives back into foundry input
            // (foundries don't accept refined ax — actually they do per spec
            // but it just sits). Or other anomalies. For now, skip foundries.
            continue;
        }
        // Conveyor / splitter / bridge with multiple input types → contaminated.
        let is_pipe = matches!(
            node.kind,
            NodeKind::Conveyor(_)
                | NodeKind::ArmouredConveyor(_)
                | NodeKind::Splitter(_)
                | NodeKind::Bridge(_)
        );
        if is_pipe && types_seen.len() > 1 {
            contaminated.insert(*pos);
        }
    }

    (edge_flow, tile_carries, contaminated)
}

fn dominant_type(m: &HashMap<CarriedType, f64>) -> CarriedType {
    if m.len() > 1 {
        return CarriedType::Mixed;
    }
    m.iter()
        .next()
        .map(|(t, _)| *t)
        .unwrap_or(CarriedType::Mixed)
}

fn flows_equal(
    a: &HashMap<(Pos, Pos), HashMap<CarriedType, f64>>,
    b: &HashMap<(Pos, Pos), HashMap<CarriedType, f64>>,
) -> bool {
    if a.len() != b.len() {
        return false;
    }
    for (k, va) in a {
        let Some(vb) = b.get(k) else {
            return false;
        };
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
    edge_flow: &HashMap<(Pos, Pos), HashMap<CarriedType, f64>>,
) -> BTreeMap<Pos, f64> {
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
        let rate = ti.min(raw).min(1.0);
        out.insert(*pos, rate);
    }
    out
}

/// After analyze, fix Harvester resource types using the map's ore data.
/// Caller passes a function that, given a tile, returns Some(ResourceType)
/// if the tile is an ore (Titanium or RawAxionite from ore), else None.
pub fn assign_harvester_types(
    flow: &mut FlowResult,
    ore_at: impl Fn(Pos) -> Option<ResourceType>,
) {
    // First, fix the node kinds.
    for (pos, node) in flow.topology.nodes.iter_mut() {
        if let NodeKind::Harvester(_) = node.kind
            && let Some(rt) = ore_at(*pos)
        {
            node.kind = NodeKind::Harvester(rt);
        }
    }
    // Then re-propagate.
    let (edge_flow, tile_carries, contaminated) = propagate_flow(&flow.topology);
    flow.foundry_rate = compute_foundry_rates(&flow.topology, &edge_flow);
    flow.edge_flow = edge_flow;
    flow.tile_carries = tile_carries;
    flow.contaminated = contaminated;
}
