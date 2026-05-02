use std::collections::{HashMap, HashSet};

use crate::blueprint::{BlueprintEntry, Entity};

const fn is_chain(k: Entity) -> bool {
    matches!(
        k,
        Entity::Conveyor | Entity::ArmouredConveyor | Entity::Splitter | Entity::Bridge
    )
}

const fn is_sink(k: Entity) -> bool {
    matches!(
        k,
        Entity::Gunner | Entity::Sentinel | Entity::Breach | Entity::Launcher | Entity::Foundry
    )
}

fn successors(entry: &BlueprintEntry) -> Vec<(i32, i32)> {
    let (x, y) = entry.pos;
    match entry.kind {
        Entity::Conveyor | Entity::ArmouredConveyor => {
            if let Some(d) = entry.direction {
                let (dx, dy) = d.delta();
                vec![(x + dx, y + dy)]
            } else {
                vec![]
            }
        }
        Entity::Splitter => {
            if let Some(d) = entry.direction {
                let (bx, by) = d.delta();
                let opp = (-bx, -by);
                let mut out = vec![];
                for (dx, dy) in [(0, -1), (1, 0), (0, 1), (-1, 0)] {
                    if (dx, dy) == opp {
                        continue;
                    }
                    out.push((x + dx, y + dy));
                }
                out
            } else {
                vec![]
            }
        }
        Entity::Bridge => entry.bridge_target.map_or(vec![], |bt| vec![bt]),
        _ => vec![],
    }
}

fn core_tiles(core: (i32, i32)) -> HashSet<(i32, i32)> {
    let mut s = HashSet::new();
    for dy in -1..=1 {
        for dx in -1..=1 {
            s.insert((core.0 + dx, core.1 + dy));
        }
    }
    s
}

pub fn unrouted(
    entries: &HashMap<(i32, i32), BlueprintEntry>,
    core: (i32, i32),
) -> HashSet<(i32, i32)> {
    let sinks_pos: HashSet<(i32, i32)> = entries
        .iter()
        .filter_map(|(p, e)| if is_sink(e.kind) { Some(*p) } else { None })
        .collect();
    let core_t = core_tiles(core);
    let sinks: HashSet<(i32, i32)> = sinks_pos
        .iter()
        .copied()
        .chain(core_t.iter().copied())
        .collect();

    let chain_positions: Vec<(i32, i32)> = entries
        .iter()
        .filter_map(|(p, e)| if is_chain(e.kind) { Some(*p) } else { None })
        .collect();

    let mut reach_sink: HashSet<(i32, i32)> = HashSet::new();
    for &start in &chain_positions {
        let mut seen = HashSet::new();
        let mut stack = vec![start];
        let mut hit = false;
        while let Some(cur) = stack.pop() {
            if !seen.insert(cur) {
                continue;
            }
            if sinks.contains(&cur) {
                hit = true;
                break;
            }
            if let Some(e) = entries.get(&cur) {
                for s in successors(e) {
                    stack.push(s);
                }
            }
        }
        if hit {
            reach_sink.insert(start);
        }
    }

    let mut bad: HashSet<(i32, i32)> = chain_positions
        .iter()
        .copied()
        .filter(|p| !reach_sink.contains(p))
        .collect();

    for (pos, e) in entries {
        if e.kind != Entity::Harvester {
            continue;
        }
        let (x, y) = *pos;
        let neighbours = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)];
        let feeds = neighbours
            .iter()
            .any(|n| reach_sink.contains(n) || sinks.contains(n));
        if !feeds {
            bad.insert(*pos);
        }
    }
    bad
}
