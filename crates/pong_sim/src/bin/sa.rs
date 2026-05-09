use std::path::Path;
use std::process::ExitCode;

use cambc_libre_engine::common::{Environment as LEnv, Team};
use pong_sa::sa::{SaConfig, anneal, parallel_tempering};
use pong_sa::sim::{Map, Pos, Tile};

fn build_map(map_path: &Path) -> Result<Map, Box<dyn std::error::Error>> {
    let map_str = map_path.to_str().ok_or("non-utf8 map path")?;
    let (env, cores) = cambc_libre_replay::load_map(map_str)?;
    let h = env.len() as i32;
    let w = env.first().map_or(0, std::vec::Vec::len) as i32;
    let mut tiles = vec![Tile::Empty; (w * h) as usize];
    for y in 0..h {
        for x in 0..w {
            tiles[(y * w + x) as usize] = match env[y as usize][x as usize] {
                LEnv::Empty => Tile::Empty,
                LEnv::Wall => Tile::Wall,
                LEnv::OreTitanium => Tile::OreTitanium,
                LEnv::OreAxionite => Tile::OreAxionite,
            };
        }
    }
    let core = cores
        .iter()
        .find(|(_, t)| matches!(t, Team::A))
        .ok_or("no team A core")?;
    Ok(Map { width: w, height: h, tiles, core: Pos::new(core.0.x, core.0.y) })
}

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let map = match args.next() {
        Some(p) => p,
        None => {
            eprintln!("usage: pong-sa MAP.map26 [--turns N] [--iters N] [--seed N] [--t-start F] [--t-end F]");
            return ExitCode::from(2);
        }
    };
    let mut cfg = SaConfig::default();
    let mut replicas: usize = 1;
    while let Some(a) = args.next() {
        match a.as_str() {
            "--turns" => cfg.turns = args.next().and_then(|s| s.parse().ok()).unwrap_or(cfg.turns),
            "--iters" => cfg.iters = args.next().and_then(|s| s.parse().ok()).unwrap_or(cfg.iters),
            "--seed" => cfg.seed = args.next().and_then(|s| s.parse().ok()).unwrap_or(cfg.seed),
            "--t-start" => cfg.t_start = args.next().and_then(|s| s.parse().ok()).unwrap_or(cfg.t_start),
            "--t-end" => cfg.t_end = args.next().and_then(|s| s.parse().ok()).unwrap_or(cfg.t_end),
            "--builders" => {
                cfg.n_builders = args
                    .next()
                    .and_then(|s| s.parse().ok())
                    .unwrap_or(cfg.n_builders);
            }
            "--replicas" => {
                replicas = args.next().and_then(|s| s.parse().ok()).unwrap_or(replicas);
            }
            o => {
                eprintln!("unknown arg {o}");
                return ExitCode::from(2);
            }
        }
    }
    let map_path = Path::new(&map);
    let m = match build_map(map_path) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("map load: {e}");
            return ExitCode::from(1);
        }
    };
    eprintln!(
        "SA: turns={} iters={} builders={} replicas={} seed={} t={}..{}",
        cfg.turns, cfg.iters, cfg.n_builders, replicas, cfg.seed, cfg.t_start, cfg.t_end
    );
    let (best, score) = if replicas <= 1 {
        anneal(&cfg, &m)
    } else {
        parallel_tempering(&cfg, &m, replicas)
    };
    println!("best score (Ax_collected): {score}");
    let n_actions: usize = best
        .builders
        .iter()
        .flat_map(|v| v.iter())
        .filter(|a| a.build.is_some() || a.destroy.is_some() || a.mv.is_some())
        .count();
    println!("plan non-NOOP actions: {n_actions}");
    ExitCode::from(0)
}
