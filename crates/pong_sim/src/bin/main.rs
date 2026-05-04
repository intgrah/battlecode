use std::env;
use std::path::PathBuf;
use std::process::ExitCode;

use libre_engine::common::{Environment, Pos, ResourceType, Team};
use pong_sim::analyze;
use pong_sim::blueprint;
use pong_sim::flow;
use pong_sim::sim::Sim;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!(
            "usage: {} BLUEPRINT.bp MAP.map26 [--turns N] [--seed N] [--replay PATH]",
            args.first().map(String::as_str).unwrap_or("pong-sim")
        );
        return ExitCode::from(2);
    }
    let bp = PathBuf::from(&args[1]);
    let map = PathBuf::from(&args[2]);
    let mut turns: i32 = 200;
    let mut seed: u64 = 1;
    let mut replay = PathBuf::from("replay.replay26");
    let mut it = args.iter().skip(3);
    while let Some(flag) = it.next() {
        match flag.as_str() {
            "--turns" => turns = it.next().and_then(|s| s.parse().ok()).unwrap_or(turns),
            "--seed" => seed = it.next().and_then(|s| s.parse().ok()).unwrap_or(seed),
            "--replay" => {
                if let Some(s) = it.next() {
                    replay = PathBuf::from(s);
                }
            }
            other => {
                eprintln!("unknown flag: {other}");
                return ExitCode::from(2);
            }
        }
    }

    let mut sim = match Sim::from_blueprint(&map, &bp, seed) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("error: {e}");
            return ExitCode::from(1);
        }
    };
    sim.run(turns);
    if let Err(e) = sim.write_replay(&replay) {
        eprintln!("write replay failed: {e}");
        return ExitCode::from(1);
    }

    let rax = sim.refined_axionite();
    let ti = sim.titanium_collected();
    println!("turns: {turns}");
    println!(
        "refined axionite collected: {rax} ({:.2}/turn)",
        rax as f64 / turns as f64
    );
    println!(
        "titanium collected: {ti} ({:.2}/turn)",
        ti as f64 / turns as f64
    );
    println!("replay: {}", replay.display());
    let report = analyze::analyze(&sim.game);
    report.print_summary();

    // Static flow analysis.
    if let Err(e) = print_flow_summary(&bp, &map) {
        eprintln!("flow analysis failed: {e}");
    }
    ExitCode::SUCCESS
}

fn print_flow_summary(
    bp_path: &std::path::Path,
    map_path: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let placements = blueprint::load(bp_path)?;
    let (env, cores) = libre_replay::load_map(map_path.to_str().ok_or("non-utf8")?)?;
    let height = env.len() as i32;
    let width = env.first().map(|r| r.len() as i32).unwrap_or(0);
    let team_a_cores: Vec<Pos> = cores
        .iter()
        .filter(|(_, t)| *t == Team::A)
        .map(|(p, _)| *p)
        .collect();
    let mut flow = flow::analyze(&placements, &team_a_cores, width, height);
    flow::assign_harvester_types(&mut flow, |p: Pos| {
        if p.x < 0 || p.y < 0 || p.x >= width || p.y >= height {
            return None;
        }
        match env[p.y as usize][p.x as usize] {
            Environment::OreTitanium => Some(ResourceType::Titanium),
            Environment::OreAxionite => Some(ResourceType::RawAxionite),
            _ => None,
        }
    });

    println!();
    println!("== Flow analysis ==");
    let mut total = 0.0;
    for (pos, rate) in &flow.foundry_rate {
        total += rate;
        println!(
            "  foundry ({:>2},{:>2})  predicted {:.3} cycles/turn  = {:.2} RAx/turn",
            pos.x,
            pos.y,
            rate,
            rate * 10.0
        );
    }
    println!(
        "  total predicted: {:.3} cycles/turn = {:.2} RAx/turn",
        total,
        total * 10.0
    );
    if !flow.contaminated.is_empty() {
        println!("  contaminated tiles ({}):", flow.contaminated.len());
        for p in &flow.contaminated {
            println!("    ({},{})", p.x, p.y);
        }
    }
    Ok(())
}
