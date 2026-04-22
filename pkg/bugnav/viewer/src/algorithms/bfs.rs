use std::collections::{HashMap, VecDeque};

use crate::grid::Grid;
use crate::pathfinder::{Pathfinder, Snapshot, StepStatus};

pub struct Bfs {
    grid_w: i32,
    grid_h: i32,
    walls: Vec<bool>,
    start: (i32, i32),
    goal: (i32, i32),
    queue: VecDeque<(i32, i32)>,
    parent: HashMap<(i32, i32), (i32, i32)>,
    snap: Snapshot,
    status: StepStatus,
}

pub fn build(grid: &Grid, start: (i32, i32), goal: (i32, i32)) -> Box<dyn Pathfinder> {
    let mut queue = VecDeque::new();
    queue.push_back(start);
    let mut snap = Snapshot {
        current: start,
        ..Snapshot::default()
    };
    snap.frontier.insert(start);
    Box::new(Bfs {
        grid_w: grid.w,
        grid_h: grid.h,
        walls: grid.walls.clone(),
        start,
        goal,
        queue,
        parent: HashMap::new(),
        snap,
        status: StepStatus::Running,
    })
}

impl Bfs {
    fn passable(&self, x: i32, y: i32) -> bool {
        if x < 0 || y < 0 || x >= self.grid_w || y >= self.grid_h {
            return false;
        }
        !self.walls[(y * self.grid_w + x) as usize]
    }

    fn reconstruct(&self) -> Vec<(i32, i32)> {
        let mut path = vec![self.goal];
        let mut cur = self.goal;
        while cur != self.start {
            let Some(&p) = self.parent.get(&cur) else {
                break;
            };
            path.push(p);
            cur = p;
        }
        path.reverse();
        path
    }
}

impl Pathfinder for Bfs {
    fn step(&mut self) -> StepStatus {
        if self.status != StepStatus::Running {
            return self.status;
        }
        let Some(pos) = self.queue.pop_front() else {
            self.status = StepStatus::Unreachable;
            return self.status;
        };
        self.snap.frontier.remove(&pos);
        self.snap.visited.insert(pos);
        self.snap.current = pos;

        if pos == self.goal {
            self.snap.path = self.reconstruct();
            self.status = StepStatus::Arrived;
            return self.status;
        }

        for (dx, dy) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
            let nx = pos.0 + dx;
            let ny = pos.1 + dy;
            let np = (nx, ny);
            if !self.passable(nx, ny) {
                continue;
            }
            if self.snap.visited.contains(&np) || self.parent.contains_key(&np) || np == self.start
            {
                continue;
            }
            self.parent.insert(np, pos);
            self.queue.push_back(np);
            self.snap.frontier.insert(np);
        }
        self.status
    }

    fn snapshot(&self) -> &Snapshot {
        &self.snap
    }

    fn summary(&self) -> String {
        format!(
            "visited: {}\nfrontier: {}\nqueue: {}\nstatus: {:?}",
            self.snap.visited.len(),
            self.snap.frontier.len(),
            self.queue.len(),
            self.status,
        )
    }

    fn name(&self) -> &'static str {
        "BFS"
    }
}
