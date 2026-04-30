use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Instant;

use titan_bugnav::grid::Grid;
use titan_bugnav::pathfinder::{StepStatus, registry, shortest_path};

const DEFAULT_PAIRS: usize = 100;
const DEFAULT_MAX_ITERS: u32 = 1000;
const SEED: u64 = 0xBC26_BEEF;

/// Minimal LCG — no external rand dep, fully reproducible.
struct Lcg(u64);
impl Lcg {
    const fn new(seed: u64) -> Self {
        Self(seed)
    }
    const fn next(&mut self) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        self.0
    }
    fn range(&mut self, lo: usize, hi: usize) -> usize {
        lo + (self.next() as usize) % (hi - lo)
    }
}

#[derive(Clone, Copy, Debug)]
enum Outcome {
    Reached { path_len: usize },
    Unreachable,
    Tle,
}

#[derive(Clone)]
struct Trial {
    map: String,
    start: (i32, i32),
    goal: (i32, i32),
    bfs_len: Option<usize>,
    outcome: Outcome,
}

fn find_maps_dir() -> Option<PathBuf> {
    let candidates = [
        Path::new("maps").to_path_buf(),
        Path::new("../maps").to_path_buf(),
        Path::new("../../maps").to_path_buf(),
        Path::new("../../../maps").to_path_buf(),
    ];
    candidates.iter().find(|p| p.is_dir()).cloned()
}

fn collect_maps(dir: &Path) -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = std::fs::read_dir(dir)
        .ok()
        .into_iter()
        .flat_map(std::iter::Iterator::flatten)
        .map(|e| e.path())
        .filter(|p| p.is_file() && p.extension().and_then(|s| s.to_str()) == Some("map26"))
        .collect();
    out.sort();
    out
}

fn all_passable(grid: &Grid) -> Vec<(i32, i32)> {
    (0..grid.h)
        .flat_map(|y| (0..grid.w).map(move |x| (x, y)))
        .filter(|&(x, y)| grid.passable(x, y))
        .collect()
}

fn run_one(
    grid: &Grid,
    algo: &titan_bugnav::pathfinder::AlgoSpec,
    start: (i32, i32),
    goal: (i32, i32),
    max_iters: u32,
    step_times_ns: &mut Vec<u64>,
    build_times_ns: &mut Vec<u64>,
) -> Outcome {
    // Report build() cost and step() cost separately: in a real bot the
    // pathfinder is created once per path (or reused across paths via a
    // cached object), so build cost is amortised; step() cost is what fires
    // every turn.
    let t0 = Instant::now();
    let mut finder = (algo.build)(grid, start, goal);
    build_times_ns.push(t0.elapsed().as_nanos() as u64);

    for _ in 0..max_iters {
        let t = Instant::now();
        let status = finder.step();
        step_times_ns.push(t.elapsed().as_nanos() as u64);
        match status {
            StepStatus::Running => {}
            StepStatus::Arrived => {
                return Outcome::Reached {
                    path_len: finder.snapshot().path.len().saturating_sub(1),
                };
            }
            StepStatus::Unreachable => return Outcome::Unreachable,
        }
    }
    Outcome::Tle
}

#[derive(Default)]
struct AlgoStats {
    total: usize,
    reachable: usize,
    reached: usize,
    false_unreach: usize,
    tle_when_reach: usize,
    correct_unreach: usize,
    tle_when_unreach: usize,
    ratios: Vec<f64>,
    /// For reached trials, keep (ratio, trial) so we can print worst cases.
    trials: Vec<(f64, Trial)>,
    /// Per-step wall time. One entry per `step()` call, excluding build cost.
    times_ns: Vec<u64>,
    /// Per-trial `build()` cost (one entry per trial).
    build_times_ns: Vec<u64>,
}

impl AlgoStats {
    fn record(&mut self, t: &Trial) {
        self.total += 1;
        let bfs_reachable = t.bfs_len.is_some();
        if bfs_reachable {
            self.reachable += 1;
        }
        match (t.outcome, t.bfs_len) {
            (Outcome::Reached { path_len }, Some(bfs_len)) if bfs_len > 0 => {
                self.reached += 1;
                let r = path_len as f64 / bfs_len as f64;
                self.ratios.push(r);
                self.trials.push((r, t.clone()));
            }
            (Outcome::Reached { .. }, Some(_)) => {
                self.reached += 1;
            }
            (Outcome::Reached { .. }, None) => {
                // BFS says unreachable but algo found a path — impossible;
                // indicates a BFS-vs-algo passability mismatch. Count as reached.
                self.reached += 1;
            }
            (Outcome::Unreachable, Some(_)) => {
                self.false_unreach += 1;
            }
            (Outcome::Unreachable, None) => {
                self.correct_unreach += 1;
            }
            (Outcome::Tle, Some(_)) => {
                self.tle_when_reach += 1;
            }
            (Outcome::Tle, None) => {
                self.tle_when_unreach += 1;
            }
        }
    }
}

fn percentile(sorted: &[f64], p: f64) -> f64 {
    if sorted.is_empty() {
        return f64::NAN;
    }
    let idx = ((sorted.len() - 1) as f64 * p).round() as usize;
    sorted[idx.min(sorted.len() - 1)]
}

fn print_summary(algos: &[&str], by_algo: &std::collections::BTreeMap<&'static str, AlgoStats>) {
    println!();
    println!(
        "{:<22} {:>6} {:>7} {:>7} {:>7} {:>8} {:>8} {:>8} {:>9}",
        "algo", "n", "conv%", "p99", "p100", "s_med/μs", "s_p99/μs", "s_max/μs", "build_max",
    );
    println!("{}", "-".repeat(100));
    for name in algos {
        let s = &by_algo[*name];
        let convergence = if s.reachable > 0 {
            100.0 * s.reached as f64 / s.reachable as f64
        } else {
            f64::NAN
        };
        let mut sorted = s.ratios.clone();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let p99 = percentile(&sorted, 0.99);
        let p100 = sorted.last().copied().unwrap_or(f64::NAN);

        let mut times = s.times_ns.clone();
        times.sort_unstable();
        let s_med = if times.is_empty() {
            0.0
        } else {
            times[times.len() / 2] as f64 / 1000.0
        };
        let s_p99 = if times.is_empty() {
            0.0
        } else {
            times[((times.len() - 1) as f64 * 0.99).round() as usize] as f64 / 1000.0
        };
        let s_max = times.last().copied().unwrap_or(0) as f64 / 1000.0;

        let build_max = s.build_times_ns.iter().copied().max().unwrap_or(0) as f64 / 1000.0;

        println!(
            "{:<22} {:>6} {:>7.1} {:>7.2} {:>7.2} {:>8.2} {:>8.1} {:>8.1} {:>9.1}",
            name, s.total, convergence, p99, p100, s_med, s_p99, s_max, build_max,
        );
    }
    println!();
    println!("columns:");
    println!("  n          total trials");
    println!("  reach      algorithm reached goal");
    println!("  conv%      reached / (reachable-per-BFS) as percent");
    println!("  p50..p100  path-length ratio (algo / BFS) quantiles over reached trials");
    println!("  s_med/μs   step() wall time (build NOT included), median");
    println!("  s_p99/μs   same, 99th percentile");
    println!("  s_max/μs   same, max — the real per-turn budget target");
    println!("  build_max  max build() cost across trials — paid once per path");
}

struct Args {
    n_pairs: usize,
    max_iters: u32,
    /// If set, print the N worst-ratio (map, start, goal) trials for each
    /// specified algorithm at the end of the run. Empty = don't print.
    worst_algos: Vec<String>,
    worst_n: usize,
}

fn parse_args() -> Args {
    let mut n_pairs = DEFAULT_PAIRS;
    let mut max_iters = DEFAULT_MAX_ITERS;
    let mut worst_algos: Vec<String> = Vec::new();
    let mut worst_n: usize = 10;
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--pairs" | "-n" => {
                n_pairs = args
                    .next()
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(DEFAULT_PAIRS);
            }
            "--iters" | "-i" => {
                max_iters = args
                    .next()
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(DEFAULT_MAX_ITERS);
            }
            "--worst" => {
                if let Some(s) = args.next() {
                    worst_algos.extend(s.split(',').map(str::to_string));
                }
            }
            "--worst-n" => {
                worst_n = args.next().and_then(|s| s.parse().ok()).unwrap_or(10);
            }
            _ => eprintln!("unknown arg: {a}"),
        }
    }
    Args {
        n_pairs,
        max_iters,
        worst_algos,
        worst_n,
    }
}

fn print_worst(algo: &str, stats: &AlgoStats, n: usize) {
    let mut worst = stats.trials.clone();
    worst.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    worst.truncate(n);
    println!();
    println!("Worst {n} (ratio, map, start, goal, bfs_len, found_len) for {algo}:");
    for (ratio, t) in &worst {
        let bfs_len = t.bfs_len.unwrap_or(0);
        let found_len = match t.outcome {
            Outcome::Reached { path_len } => path_len,
            _ => 0,
        };
        println!(
            "  {:>7.2}x  {:<25}  ({:>3}, {:>3}) -> ({:>3}, {:>3})   bfs={:<4}  found={}",
            ratio, t.map, t.start.0, t.start.1, t.goal.0, t.goal.1, bfs_len, found_len,
        );
    }
}

fn main() {
    let args = parse_args();
    let (n_pairs, max_iters) = (args.n_pairs, args.max_iters);

    let maps_dir = find_maps_dir().unwrap_or_else(|| {
        eprintln!("cannot find maps/ directory");
        std::process::exit(1);
    });
    let map_paths = collect_maps(&maps_dir);
    if map_paths.is_empty() {
        eprintln!("no .map26 files in {}", maps_dir.display());
        std::process::exit(1);
    }

    eprintln!(
        "maps: {}, pairs/map: {}, iter cap: {}, seed: 0x{:X}",
        map_paths.len(),
        n_pairs,
        max_iters,
        SEED
    );

    let algos: Vec<&titan_bugnav::pathfinder::AlgoSpec> = registry().iter().collect();
    let algo_names: Vec<&'static str> = algos.iter().map(|a| a.name).collect();
    let mut by_algo: std::collections::BTreeMap<&'static str, AlgoStats> = algo_names
        .iter()
        .map(|&n| (n, AlgoStats::default()))
        .collect();

    let mut rng = Lcg::new(SEED);
    let t_start = Instant::now();
    let total_maps = map_paths.len();

    for (map_idx, map_path) in map_paths.iter().enumerate() {
        let grid = match Grid::load(map_path) {
            Ok(g) => g,
            Err(e) => {
                eprintln!("skip {}: {e}", map_path.display());
                continue;
            }
        };
        let passable = all_passable(&grid);
        if passable.len() < 2 {
            continue;
        }

        for _ in 0..n_pairs {
            let start = passable[rng.range(0, passable.len())];
            let mut goal = passable[rng.range(0, passable.len())];
            let mut attempts = 0;
            while goal == start && attempts < 8 {
                goal = passable[rng.range(0, passable.len())];
                attempts += 1;
            }
            if goal == start {
                continue;
            }

            let bfs_len = shortest_path(&grid, start, goal).map(|p| p.len().saturating_sub(1));

            for algo in &algos {
                let stats = by_algo.get_mut(algo.name).unwrap();
                let outcome = run_one(
                    &grid,
                    algo,
                    start,
                    goal,
                    max_iters,
                    &mut stats.times_ns,
                    &mut stats.build_times_ns,
                );
                let trial = Trial {
                    map: grid.name.clone(),
                    start,
                    goal,
                    bfs_len,
                    outcome,
                };
                stats.record(&trial);
            }
        }

        let done = map_idx + 1;
        let elapsed = t_start.elapsed().as_secs_f64();
        let eta = if done > 0 {
            elapsed * (total_maps - done) as f64 / done as f64
        } else {
            0.0
        };
        let pct = 100.0 * done as f64 / total_maps as f64;
        eprint!(
            "\r[{:>3}/{:<3}] {:>5.1}%  elapsed {:>5.1}s  eta {:>5.1}s  {:<30}",
            done, total_maps, pct, elapsed, eta, grid.name,
        );
        let _ = std::io::stderr().flush();
    }
    eprintln!();

    print_summary(&algo_names, &by_algo);

    for algo in &args.worst_algos {
        if let Some(stats) = by_algo.get(algo.as_str()) {
            print_worst(algo, stats, args.worst_n);
        } else {
            eprintln!("--worst: unknown algo '{algo}' (known: {algo_names:?})");
        }
    }
}
