use std::collections::HashSet;

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
    ]
}
