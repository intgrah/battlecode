use std::collections::VecDeque;

use crate::entity;
use crate::proto;
use crate::state::{EntityKind, TurnState};

const DIR4: [(i32, i32); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];

pub struct FlowState {
    pub w: usize,
    pub ti: Vec<f32>,
    pub ax: Vec<f32>,
    pub rax: Vec<f32>,
    pub excess: Vec<f32>,
}

impl FlowState {
    fn new(n: usize) -> Self {
        Self {
            w: 0,
            ti: vec![0.0; n],
            ax: vec![0.0; n],
            rax: vec![0.0; n],
            excess: vec![0.0; n],
        }
    }
}

#[allow(clippy::too_many_lines, clippy::similar_names)]
pub fn compute_flow(
    state: &TurnState,
    env: &[Vec<proto::Environment>],
    w: usize,
    h: usize,
) -> FlowState {
    let n = w * h;
    let mut flow = FlowState::new(n);
    flow.w = w;

    let mut kind_grid: Vec<Option<&EntityKind>> = vec![None; n];
    for e in state.entities.values() {
        let i = e.pos.1 as usize * w + e.pos.0 as usize;
        if i < n && (kind_grid[i].is_none() || entity::is_flow_receiver(&e.kind)) {
            kind_grid[i] = Some(&e.kind);
        }
    }

    let in_bounds =
        |x: i32, y: i32| -> bool { x >= 0 && (x as usize) < w && y >= 0 && (y as usize) < h };
    let idx = |x: i32, y: i32| -> usize { y as usize * w + x as usize };

    let can_receive = |x: i32, y: i32, from_dx: i32, from_dy: i32| -> bool {
        if !in_bounds(x, y) {
            return false;
        }
        let i = idx(x, y);
        let Some(kind) = kind_grid[i] else {
            return false;
        };
        if !entity::is_flow_receiver(kind) {
            return false;
        }
        entity::delta_to_dir(from_dx, from_dy).is_none_or(|d| entity::accepts_input_from(kind, d))
    };

    let mut in_degree = vec![0_i32; n];
    let mut out_edges: Vec<Vec<usize>> = vec![Vec::new(); n];

    for e in state.entities.values() {
        let (px, py) = (e.pos.0, e.pos.1);
        let si = idx(px, py);
        match &e.kind {
            EntityKind::Conveyor { dir, .. } | EntityKind::ArmouredConveyor { dir, .. } => {
                let (dx, dy) = entity::dir_delta(*dir);
                let (nx, ny) = (px + dx, py + dy);
                if can_receive(nx, ny, dx, dy) {
                    let ti = idx(nx, ny);
                    out_edges[si].push(ti);
                    in_degree[ti] += 1;
                }
            }
            EntityKind::Splitter { dir, .. } => {
                let (dx, dy) = entity::dir_delta(*dir);
                for (odx, ody) in [(dx, dy), (-dy, dx), (dy, -dx)] {
                    let (nx, ny) = (px + odx, py + ody);
                    if can_receive(nx, ny, odx, ody) {
                        let ti = idx(nx, ny);
                        out_edges[si].push(ti);
                        in_degree[ti] += 1;
                    }
                }
            }
            EntityKind::Bridge { target, .. } => {
                if can_receive(target.0, target.1, 0, 0) {
                    let ti = idx(target.0, target.1);
                    out_edges[si].push(ti);
                    in_degree[ti] += 1;
                }
            }
            EntityKind::Foundry { .. } | EntityKind::Harvester { .. } => {
                for (ddx, ddy) in DIR4 {
                    let (nx, ny) = (px + ddx, py + ddy);
                    if can_receive(nx, ny, ddx, ddy) {
                        let ti = idx(nx, ny);
                        out_edges[si].push(ti);
                        in_degree[ti] += 1;
                    }
                }
            }
            _ => {}
        }
    }

    let mut queue: VecDeque<usize> = VecDeque::new();

    for e in state.entities.values() {
        if !matches!(e.kind, EntityKind::Harvester { .. }) {
            continue;
        }
        let (px, py) = (e.pos.0, e.pos.1);
        let si = idx(px, py);
        let ore = env
            .get(py as usize)
            .and_then(|row| row.get(px as usize))
            .copied()
            .unwrap_or(proto::Environment::EnvEmpty);
        let no = out_edges[si].len();
        let denom = no.max(1) as f32;
        let push = 0.25 / denom;
        for oi in out_edges[si].clone() {
            match ore {
                proto::Environment::EnvOreTitanium => flow.ti[oi] += push,
                proto::Environment::EnvOreAxionite => flow.ax[oi] += push,
                _ => {}
            }
            in_degree[oi] -= 1;
            if in_degree[oi] <= 0 {
                queue.push_back(oi);
            }
        }
        queue.push_back(si);
    }

    for i in 0..n {
        if kind_grid[i].is_some_and(|k| entity::is_flow_receiver(k)) && in_degree[i] == 0 && !queue.contains(&i) {
            queue.push_back(i);
        }
    }

    while let Some(ci) = queue.pop_front() {
        let Some(kind) = kind_grid[ci] else {
            continue;
        };

        let ti_in = flow.ti[ci];
        let ax_in = flow.ax[ci];
        let rax_in = flow.rax[ci];
        let edges: Vec<usize> = out_edges[ci].clone();
        let no = edges.len();

        flow.excess[ci] = match kind {
            EntityKind::Core { .. } => 0.0,

            EntityKind::Foundry { .. } => {
                let refined = ti_in.min(ax_in);
                let rax_out = rax_in + refined;
                let push = if no > 0 { rax_out / no as f32 } else { 0.0 };
                for oi in edges {
                    flow.rax[oi] += push;
                    in_degree[oi] -= 1;
                    if in_degree[oi] <= 0 {
                        queue.push_back(oi);
                    }
                }
                (ti_in + ax_in + rax_in) - rax_out
            }
            EntityKind::Conveyor { .. }
            | EntityKind::ArmouredConveyor { .. }
            | EntityKind::Splitter { .. }
            | EntityKind::Bridge { .. } => {
                let divisor = if matches!(kind, EntityKind::Splitter { .. }) && no > 0 {
                    no as f32
                } else {
                    1.0
                };
                let ti_push = ti_in / divisor;
                let ax_push = ax_in / divisor;
                let rax_push = rax_in / divisor;
                let total_push = ti_push + ax_push + rax_push;
                let mut total_out = 0.0;
                for oi in edges {
                    flow.ti[oi] += ti_push;
                    flow.ax[oi] += ax_push;
                    flow.rax[oi] += rax_push;
                    total_out += total_push;
                    in_degree[oi] -= 1;
                    if in_degree[oi] <= 0 {
                        queue.push_back(oi);
                    }
                }
                (ti_in + ax_in + rax_in) - total_out
            }
            _ => ti_in + ax_in + rax_in,
        };
    }

    flow
}
