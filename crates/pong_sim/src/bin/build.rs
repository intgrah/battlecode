//! pong-build: construct a blueprint by calling the solver.
//!
//! For now: hand-specifies foundry positions + ax/ti harvester assignments,
//! delegates conveyor routing to solver::route, writes .bp.

use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

use cambc_libre_engine::common::Pos;
use pong_sim::solver::{
    Map, Network, place_foundry, place_harvester_with_route, render_bp, route_foundry_to_core,
};

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!(
            "usage: {} MAP.map26 OUT.bp",
            args.first().map(String::as_str).unwrap_or("pong-build")
        );
        return ExitCode::from(2);
    }
    let map_path = PathBuf::from(&args[1]);
    let out_path = PathBuf::from(&args[2]);

    let map = match Map::load(&map_path) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("load map: {e}");
            return ExitCode::from(1);
        }
    };

    let mut net = Network::default();

    // Lower foundry F1 at (3,16) with 4 ax + 4 ti.
    if let Err(e) = build_foundry_with_assignments(
        &map,
        &mut net,
        Pos { x: 3, y: 16 },
        &[
            Pos { x: 1, y: 16 },
            Pos { x: 5, y: 16 },
            Pos { x: 2, y: 17 },
            Pos { x: 4, y: 17 },
        ],
        &[
            Pos { x: 1, y: 20 },
            Pos { x: 3, y: 20 },
            Pos { x: 5, y: 20 },
            Pos { x: 4, y: 21 },
        ],
    ) {
        eprintln!("F1 build: {e}");
    }

    let bp_text = render_bp(&net);
    if let Err(e) = fs::write(&out_path, &bp_text) {
        eprintln!("write {}: {e}", out_path.display());
        return ExitCode::from(1);
    }
    println!("wrote {} placements to {}", net.placements.len(), out_path.display());
    ExitCode::SUCCESS
}

/// Place foundry + 4 ax harvesters (with routes) + 4 ti harvesters (with routes).
fn build_foundry_with_assignments(
    map: &Map,
    net: &mut Network,
    foundry: Pos,
    ax: &[Pos],
    ti: &[Pos],
) -> Result<(), String> {
    place_foundry(net, foundry)?;
    // Route refined-ax output FIRST (needs free cardinal toward core).
    route_foundry_to_core(map, net, foundry)?;
    for &a in ax {
        place_harvester_with_route(map, net, a, foundry)?;
    }
    for &t in ti {
        place_harvester_with_route(map, net, t, foundry)?;
    }
    Ok(())
}
