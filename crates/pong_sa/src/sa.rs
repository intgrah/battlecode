use rand::SeedableRng;
use rand::rngs::StdRng;

use crate::plan::{Build, CoreAction, Plan, TurnAction};
use crate::sim::{BuildKind, Direction, Map, Pos, State};

const KINDS: [BuildKind; 7] = [
    BuildKind::Conveyor,
    BuildKind::Splitter,
    BuildKind::ArmouredConveyor,
    BuildKind::Bridge,
    BuildKind::Harvester,
    BuildKind::Foundry,
    BuildKind::Road,
];

const DIRS: [Direction; 8] = [
    Direction::North,
    Direction::Northeast,
    Direction::East,
    Direction::Southeast,
    Direction::South,
    Direction::Southwest,
    Direction::West,
    Direction::Northwest,
];

const CARDINALS: [Direction; 4] = [
    Direction::North,
    Direction::East,
    Direction::South,
    Direction::West,
];

#[derive(Debug, Clone)]
pub struct SaConfig {
    pub turns: i32,
    pub n_builders: usize,
    pub iters: u64,
    pub t_start: f64,
    pub t_end: f64,
    pub mutations_per_iter: usize,
    pub seed: u64,
}

impl Default for SaConfig {
    fn default() -> Self {
        Self {
            turns: 2000,
            n_builders: 2,
            iters: 10_000,
            t_start: 1000.0,
            t_end: 1.0,
            mutations_per_iter: 1,
            seed: 1,
        }
    }
}

pub fn evaluate(map: &Map, plan: &Plan, sim_seed: u64) -> i32 {
    let mut state = State::new(map.clone(), sim_seed);
    for _ in 0..plan.turns {
        state.step(plan);
    }
    state.axionite_collected
}

fn pick_dir(rng: &mut StdRng) -> Direction {
    use rand::RngExt;
    DIRS[rng.random::<u32>() as usize % DIRS.len()]
}

fn pick_cardinal(rng: &mut StdRng) -> Direction {
    use rand::RngExt;
    CARDINALS[rng.random::<u32>() as usize % CARDINALS.len()]
}

fn pick_kind(rng: &mut StdRng) -> BuildKind {
    use rand::RngExt;
    KINDS[rng.random::<u32>() as usize % KINDS.len()]
}

fn pick_pos_near(map: &Map, centre: Pos, rng: &mut StdRng) -> Pos {
    use rand::RngExt;
    // Within a r=2 (king) box of centre, on map.
    loop {
        let dx = (rng.random::<u32>() % 5) as i32 - 2;
        let dy = (rng.random::<u32>() % 5) as i32 - 2;
        let p = Pos::new(centre.x + dx, centre.y + dy);
        if map.in_bounds(p) {
            return p;
        }
    }
}

fn random_build(map: &Map, centre: Pos, rng: &mut StdRng) -> Build {
    let kind = pick_kind(rng);
    let pos = pick_pos_near(map, centre, rng);
    let direction = match kind {
        BuildKind::Conveyor | BuildKind::Splitter | BuildKind::ArmouredConveyor => Some(pick_cardinal(rng)),
        _ => None,
    };
    let bridge_target = match kind {
        BuildKind::Bridge => Some(pick_pos_near(map, pos, rng)),
        _ => None,
    };
    Build { kind, pos, direction, bridge_target }
}

pub fn mutate(plan: &mut Plan, map: &Map, rng: &mut StdRng) {
    use rand::RngExt;
    let op = rng.random::<u32>() % 6;
    let turns = plan.turns as usize;
    if turns == 0 || plan.builders.is_empty() {
        return;
    }
    match op {
        // Random build action on a random builder/turn.
        0 => {
            let b = rng.random::<u32>() as usize % plan.builders.len();
            let t = rng.random::<u32>() as usize % turns;
            let build = random_build(map, map.core, rng);
            plan.builders[b][t].build = Some(build);
        }
        // Random move direction.
        1 => {
            let b = rng.random::<u32>() as usize % plan.builders.len();
            let t = rng.random::<u32>() as usize % turns;
            plan.builders[b][t].mv = Some(pick_dir(rng));
        }
        // Clear an action.
        2 => {
            let b = rng.random::<u32>() as usize % plan.builders.len();
            let t = rng.random::<u32>() as usize % turns;
            plan.builders[b][t] = TurnAction::NOOP;
        }
        // Toggle spawn at a random turn.
        3 => {
            let t = rng.random::<u32>() as usize % turns.min(8);
            plan.core[t] = if plan.core[t].spawn.is_some() {
                CoreAction::NOOP
            } else {
                CoreAction { spawn: Some(map.core.add(pick_dir(rng))) }
            };
        }
        // Swap actions between two turns of same builder.
        4 => {
            let b = rng.random::<u32>() as usize % plan.builders.len();
            let t1 = rng.random::<u32>() as usize % turns;
            let t2 = rng.random::<u32>() as usize % turns;
            plan.builders[b].swap(t1, t2);
        }
        // Move action between builders at same turn.
        5 => {
            if plan.builders.len() >= 2 {
                let t = rng.random::<u32>() as usize % turns;
                let a = rng.random::<u32>() as usize % plan.builders.len();
                let mut bb = (a + 1) % plan.builders.len();
                if bb == a {
                    bb = (a + 1) % plan.builders.len();
                }
                let tmp = plan.builders[a][t];
                plan.builders[a][t] = plan.builders[bb][t];
                plan.builders[bb][t] = tmp;
            }
        }
        _ => unreachable!(),
    }
}

pub fn initial_plan(cfg: &SaConfig, map: &Map) -> Plan {
    let mut plan = Plan::new(cfg.turns, cfg.n_builders);
    // Default: spawn 2 builders at T=0,1 next to core.
    if cfg.turns > 0 {
        plan.core[0] = CoreAction { spawn: Some(map.core.add(Direction::North)) };
    }
    if cfg.turns > 1 {
        plan.core[1] = CoreAction { spawn: Some(map.core.add(Direction::Northeast)) };
    }
    plan
}

pub fn anneal(cfg: &SaConfig, map: &Map) -> (Plan, i32) {
    let mut rng = StdRng::seed_from_u64(cfg.seed);
    let mut plan = initial_plan(cfg, map);
    let mut score = evaluate(map, &plan, cfg.seed);
    let mut best_plan = plan.clone();
    let mut best_score = score;

    for k in 0..cfg.iters {
        let frac = k as f64 / cfg.iters.max(1) as f64;
        let temperature = cfg.t_start * (cfg.t_end / cfg.t_start).powf(frac);

        let mut candidate = plan.clone();
        for _ in 0..cfg.mutations_per_iter {
            mutate(&mut candidate, map, &mut rng);
        }
        let new_score = evaluate(map, &candidate, cfg.seed);

        let delta = new_score - score;
        let accept = if delta >= 0 {
            true
        } else {
            use rand::RngExt;
            let p = (delta as f64 / temperature).exp();
            rng.random::<f64>() < p
        };
        if accept {
            plan = candidate;
            score = new_score;
            if score > best_score {
                best_score = score;
                best_plan = plan.clone();
                eprintln!("iter={k:6} T={temperature:>8.2} score={score} (best)");
            }
        }
    }
    (best_plan, best_score)
}

pub fn parallel_tempering(cfg: &SaConfig, map: &Map, k: usize) -> (Plan, i32) {
    use rand::RngExt;
    let mut rng = StdRng::seed_from_u64(cfg.seed);
    let temps: Vec<f64> = (0..k)
        .map(|i| cfg.t_start * (cfg.t_end / cfg.t_start).powf(i as f64 / k.saturating_sub(1).max(1) as f64))
        .collect();
    let mut plans: Vec<Plan> = (0..k).map(|_| initial_plan(cfg, map)).collect();
    let mut scores: Vec<i32> = plans.iter().map(|p| evaluate(map, p, cfg.seed)).collect();
    let mut best = (plans[0].clone(), scores[0]);

    for it in 0..cfg.iters {
        for r in 0..k {
            let mut cand = plans[r].clone();
            for _ in 0..cfg.mutations_per_iter {
                mutate(&mut cand, map, &mut rng);
            }
            let new_score = evaluate(map, &cand, cfg.seed);
            let delta = new_score - scores[r];
            let accept = delta >= 0 || rng.random::<f64>() < (delta as f64 / temps[r]).exp();
            if accept {
                plans[r] = cand;
                scores[r] = new_score;
                if scores[r] > best.1 {
                    best = (plans[r].clone(), scores[r]);
                    eprintln!(
                        "iter={it:6} replica={r} T={t:>8.2} score={s}",
                        t = temps[r],
                        s = scores[r],
                    );
                }
            }
        }
        if it % 10 == 0 && k >= 2 {
            for r in 0..(k - 1) {
                let dscore = f64::from(scores[r + 1] - scores[r]);
                let dbeta = 1.0 / temps[r] - 1.0 / temps[r + 1];
                let p = (dscore * dbeta).exp().min(1.0);
                if rng.random::<f64>() < p {
                    plans.swap(r, r + 1);
                    scores.swap(r, r + 1);
                }
            }
        }
    }
    best
}
