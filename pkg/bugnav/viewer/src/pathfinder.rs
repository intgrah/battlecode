use std::collections::{HashMap, HashSet, VecDeque};

use crate::grid::Grid;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StepStatus {
    Running,
    Arrived,
    Unreachable,
}

#[derive(Default)]
pub struct Snapshot {
    pub current: (i32, i32),
    pub visited: HashSet<(i32, i32)>,
    pub frontier: HashSet<(i32, i32)>,
    pub path: Vec<(i32, i32)>,
}

pub trait Pathfinder {
    fn step(&mut self) -> StepStatus;
    fn snapshot(&self) -> &Snapshot;
    fn summary(&self) -> String;
    fn name(&self) -> &'static str;
}

pub struct AlgoSpec {
    pub name: &'static str,
    pub build: fn(&Grid, (i32, i32), (i32, i32)) -> Box<dyn Pathfinder>,
}

/// Run BFS to completion on the 8-connected grid and return the shortest path
/// from `start` to `goal` as a sequence of cells (inclusive at both ends), or
/// `None` if the goal is unreachable.
#[must_use]
pub fn shortest_path(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Option<Vec<(i32, i32)>> {
    const DIRS: [(i32, i32); 8] = [
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    ];
    let mut queue: VecDeque<(i32, i32)> = VecDeque::new();
    let mut parent: HashMap<(i32, i32), (i32, i32)> = HashMap::new();
    let mut visited: HashSet<(i32, i32)> = HashSet::new();
    queue.push_back(start);
    visited.insert(start);
    while let Some(pos) = queue.pop_front() {
        if pos == goal {
            let mut path = vec![goal];
            let mut cur = goal;
            while cur != start {
                let p = parent[&cur];
                path.push(p);
                cur = p;
            }
            path.reverse();
            return Some(path);
        }
        for (dx, dy) in DIRS {
            let np = (pos.0 + dx, pos.1 + dy);
            if !grid.passable(np.0, np.1) || visited.contains(&np) {
                continue;
            }
            visited.insert(np);
            parent.insert(np, pos);
            queue.push_back(np);
        }
    }
    None
}

#[must_use]
pub fn registry() -> &'static [AlgoSpec] {
    &[
        AlgoSpec {
            name: "BFS",
            build: crate::algorithms::bfs::build,
        },
        AlgoSpec {
            name: "Bug0",
            build: crate::algorithms::bug0::build,
        },
        AlgoSpec {
            name: "Bug1",
            build: crate::algorithms::bug1::build,
        },
        AlgoSpec {
            name: "Bug1+LoS",
            build: crate::algorithms::bug1::build_los,
        },
        AlgoSpec {
            name: "Bug2",
            build: crate::algorithms::bug2::build,
        },
        AlgoSpec {
            name: "DistBug",
            build: crate::algorithms::distbug::build,
        },
        AlgoSpec {
            name: "VisBug-21",
            build: crate::algorithms::visbug21::build,
        },
        AlgoSpec {
            name: "VisBug-22",
            build: crate::algorithms::visbug22::build,
        },
        AlgoSpec {
            name: "TangentBug",
            build: crate::algorithms::tangentbug::build,
        },
        AlgoSpec {
            name: "BFS+Bug1",
            build: crate::algorithms::bfsbug::build,
        },
        AlgoSpec {
            name: "Memory+BFS",
            build: crate::algorithms::mem_bfs::build,
        },
        AlgoSpec {
            name: "Memory+A*",
            build: crate::algorithms::mem_astar::build,
        },
        AlgoSpec {
            name: "LookaheadBug",
            build: crate::algorithms::lookahead_bug::build,
        },
        AlgoSpec {
            name: "LookaheadBug+FullMap",
            build: crate::algorithms::lookahead_bug::build_full_map,
        },
    ]
}
