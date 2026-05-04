use std::collections::HashMap;
use std::collections::HashSet;

use libre_engine::common::{Direction, Pos, ResourceType, Team};
use libre_engine::game::Game;
use libre_engine::game_map::Entity;
use libre_engine::replay_diff::GameDiff;

#[derive(Debug, Clone)]
pub struct HarvesterStats {
    pub pos: Pos,
    pub resource: ResourceType,
    pub stacks_emitted: u32,
    pub static_terminals: Vec<(Pos, TerminalKind)>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TerminalKind {
    Foundry,
    Core,
    Turret,
    DeadEnd,
}

#[derive(Debug, Clone)]
pub struct FoundryStats {
    pub pos: Pos,
    pub refined_out: u32,
    pub stacks_in_total: u32,
    pub refined_to_core: u32,
}

#[derive(Debug, Clone)]
pub struct Report {
    pub turns: i32,
    pub harvesters: Vec<HarvesterStats>,
    pub foundries: Vec<FoundryStats>,
    pub stacks_to_core_total: u32,
    pub refined_units_to_core: i32,
    pub ti_units_to_core: i32,
}

pub fn analyze(game: &Game) -> Report {
    let mut pos_to_entity: HashMap<Pos, Entity> = HashMap::new();
    for e in game.entities.values() {
        pos_to_entity.insert(e.position, e.clone());
    }

    let core_positions: HashSet<Pos> = game
        .entities
        .values()
        .filter_map(|e| match e {
            Entity::Core(c) => Some(c.position),
            _ => None,
        })
        .flat_map(|center| {
            (-1i32..=1).flat_map(move |dy| {
                (-1i32..=1).map(move |dx| Pos {
                    x: center.x + dx,
                    y: center.y + dy,
                })
            })
        })
        .collect();

    let foundry_positions: HashSet<Pos> = game
        .entities
        .values()
        .filter_map(|e| match e {
            Entity::Foundry(f) => Some(f.position),
            _ => None,
        })
        .collect();

    let mut moves_from: HashMap<Pos, u32> = HashMap::new();
    let mut moves_to: HashMap<Pos, u32> = HashMap::new();
    let mut stacks_to_core_total: u32 = 0;

    for diffs in game.replay_recorder.turns() {
        for d in diffs {
            let GameDiff::DistributeResources { moves } = d else {
                continue;
            };
            for &(src, sink, _id) in moves {
                *moves_from.entry(src).or_default() += 1;
                *moves_to.entry(sink).or_default() += 1;
                if core_positions.contains(&sink) {
                    stacks_to_core_total += 1;
                }
            }
        }
    }

    let mut harvesters = Vec::new();
    for e in game.entities.values() {
        let Entity::Harvester(h) = e else { continue };
        let emitted = *moves_from.get(&h.position).unwrap_or(&0);
        let terminals = trace_terminals(
            &pos_to_entity,
            &foundry_positions,
            &core_positions,
            h.position,
        );
        harvesters.push(HarvesterStats {
            pos: h.position,
            resource: h.resource_type,
            stacks_emitted: emitted,
            static_terminals: terminals,
        });
    }
    harvesters.sort_by_key(|h| (h.pos.y, h.pos.x));

    let mut foundries = Vec::new();
    for &fp in &foundry_positions {
        let refined_out = *moves_from.get(&fp).unwrap_or(&0);
        let stacks_in = *moves_to.get(&fp).unwrap_or(&0);
        foundries.push(FoundryStats {
            pos: fp,
            refined_out,
            stacks_in_total: stacks_in,
            refined_to_core: 0,
        });
    }
    foundries.sort_by_key(|f| (f.pos.y, f.pos.x));

    let player = &game.players[Team::A.index()];
    Report {
        turns: game.replay_recorder.turns().len() as i32,
        harvesters,
        foundries,
        stacks_to_core_total,
        refined_units_to_core: player.axionite_collected,
        ti_units_to_core: player.titanium_collected,
    }
}

/// Statically follow output edges from `start` (a building tile) through
/// conveyor/splitter/armoured-conveyor/bridge chains and report the set of
/// terminal entities reached.
fn trace_terminals(
    map: &HashMap<Pos, Entity>,
    foundries: &HashSet<Pos>,
    cores: &HashSet<Pos>,
    start: Pos,
) -> Vec<(Pos, TerminalKind)> {
    let mut seen = HashSet::new();
    let mut out: Vec<(Pos, TerminalKind)> = Vec::new();
    let mut stack: Vec<Pos> = output_neighbours(map, start);
    while let Some(p) = stack.pop() {
        if !seen.insert(p) {
            continue;
        }
        if foundries.contains(&p) {
            out.push((p, TerminalKind::Foundry));
            continue;
        }
        if cores.contains(&p) {
            out.push((p, TerminalKind::Core));
            continue;
        }
        match map.get(&p) {
            Some(Entity::Gunner(_) | Entity::Sentinel(_) | Entity::Breach(_)) => {
                out.push((p, TerminalKind::Turret));
            }
            Some(
                Entity::Conveyor(_)
                | Entity::Splitter(_)
                | Entity::ArmouredConveyor(_)
                | Entity::Bridge(_),
            ) => {
                for next in output_neighbours(map, p) {
                    if !seen.contains(&next) {
                        stack.push(next);
                    }
                }
            }
            None | Some(_) => {
                out.push((p, TerminalKind::DeadEnd));
            }
        }
    }
    out
}

fn output_neighbours(map: &HashMap<Pos, Entity>, p: Pos) -> Vec<Pos> {
    let entity = match map.get(&p) {
        Some(e) => e,
        None => return Vec::new(),
    };
    match entity {
        Entity::Conveyor(c) => vec![c.position + c.direction],
        Entity::ArmouredConveyor(c) => vec![c.position + c.direction],
        Entity::Splitter(s) => {
            // Splitter outputs to all 3 non-input cardinal sides.
            let input = s.direction.opposite();
            cardinals()
                .into_iter()
                .filter(|&d| d != input)
                .map(|d| s.position + d)
                .collect()
        }
        Entity::Bridge(b) => vec![b.target],
        Entity::Harvester(h) => cardinals()
            .into_iter()
            .map(|d| h.position + d)
            .filter(|p| map.contains_key(p))
            .collect(),
        Entity::Foundry(f) => cardinals()
            .into_iter()
            .map(|d| f.position + d)
            .filter(|p| map.contains_key(p))
            .collect(),
        _ => Vec::new(),
    }
}

fn cardinals() -> [Direction; 4] {
    [
        Direction::North,
        Direction::East,
        Direction::South,
        Direction::West,
    ]
}

impl Report {
    pub fn print_summary(&self) {
        let turns = self.turns.max(1) as f64;
        println!();
        println!("== Foundries ({}) ==", self.foundries.len());
        for f in &self.foundries {
            println!(
                "  ({:>2},{:>2})  refined_out={:>4}  stacks_in={:>4}  to_core={:>4}  rate_in={:.2}/turn  rate_out={:.2}/turn",
                f.pos.x,
                f.pos.y,
                f.refined_out,
                f.stacks_in_total,
                f.refined_to_core,
                f.stacks_in_total as f64 * 10.0 / turns,
                f.refined_out as f64 * 10.0 / turns,
            );
        }
        println!();
        println!("== Harvesters ({}) ==", self.harvesters.len());
        let mut leak_count = 0;
        for h in &self.harvesters {
            let mut foundry_terms = 0;
            let mut core_terms = 0;
            let mut turret_terms = 0;
            let mut dead_terms = 0;
            for &(_p, k) in &h.static_terminals {
                match k {
                    TerminalKind::Foundry => foundry_terms += 1,
                    TerminalKind::Core => core_terms += 1,
                    TerminalKind::Turret => turret_terms += 1,
                    TerminalKind::DeadEnd => dead_terms += 1,
                }
            }
            let leak = match h.resource {
                ResourceType::Titanium => core_terms + turret_terms,
                ResourceType::RawAxionite => core_terms + turret_terms,
                ResourceType::RefinedAxionite => 0,
            };
            if leak > 0 {
                leak_count += 1;
            }
            let mark = if foundry_terms == 0 {
                " <-- NO FOUNDRY REACHABLE"
            } else if leak > 0 {
                " <-- LEAK to non-foundry"
            } else if dead_terms > 0 {
                " <-- partial dead-end"
            } else {
                ""
            };
            println!(
                "  ({:>2},{:>2}) {:?}  emitted={:>3}  rate={:.2}/turn  reaches: foundries={} cores={} turrets={} dead={}{}",
                h.pos.x,
                h.pos.y,
                h.resource,
                h.stacks_emitted,
                h.stacks_emitted as f64 * 10.0 / turns,
                foundry_terms,
                core_terms,
                turret_terms,
                dead_terms,
                mark,
            );
        }
        println!();
        println!(
            "Stacks delivered to core: {} ({:.2}/turn)",
            self.stacks_to_core_total,
            self.stacks_to_core_total as f64 / turns,
        );
        println!(
            "Refined ax at core: {} units ({:.2}/turn)",
            self.refined_units_to_core,
            self.refined_units_to_core as f64 / turns,
        );
        println!(
            "Titanium at core: {} units ({:.2}/turn)",
            self.ti_units_to_core,
            self.ti_units_to_core as f64 / turns,
        );
        if leak_count > 0 {
            println!("Harvesters with topological leaks: {leak_count}");
        }
    }
}
