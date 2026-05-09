use std::path::Path;
use std::process::ExitCode;

use libre_engine::common::{Direction as LDirection, Environment as LEnv, Pos as LPos};
use pong_sa::sim::{BuildKind, Direction, Map, Pos, State, Tile};
use pong_sim::sim::Sim;
use pong_sim::blueprint::{Kind, load as load_bp};

fn map_dir(d: LDirection) -> Direction {
    match d {
        LDirection::North => Direction::North,
        LDirection::Northeast => Direction::Northeast,
        LDirection::East => Direction::East,
        LDirection::Southeast => Direction::Southeast,
        LDirection::South => Direction::South,
        LDirection::Southwest => Direction::Southwest,
        LDirection::West => Direction::West,
        LDirection::Northwest => Direction::Northwest,
        LDirection::Centre => panic!("unexpected centre direction"),
    }
}

fn map_kind(k: Kind) -> BuildKind {
    match k {
        Kind::Conveyor => BuildKind::Conveyor,
        Kind::Splitter => BuildKind::Splitter,
        Kind::ArmouredConveyor => BuildKind::ArmouredConveyor,
        Kind::Bridge => BuildKind::Bridge,
        Kind::Harvester => BuildKind::Harvester,
        Kind::Foundry => BuildKind::Foundry,
        Kind::Road => BuildKind::Road,
        Kind::Barrier => BuildKind::Barrier,
    }
}

fn build_my_state(map_path: &Path, bp_path: &Path, seed: u64) -> Result<State, Box<dyn std::error::Error>> {
    let map_str = map_path.to_str().ok_or("non-utf8 map path")?;
    let (env, cores) = libre_replay::load_map(map_str)?;
    let h = env.len() as i32;
    let w = env.first().map_or(0, std::vec::Vec::len) as i32;
    let mut tiles = vec![Tile::Empty; (w * h) as usize];
    for y in 0..h {
        for x in 0..w {
            let t = match env[y as usize][x as usize] {
                LEnv::Empty => Tile::Empty,
                LEnv::Wall => Tile::Wall,
                LEnv::OreTitanium => Tile::OreTitanium,
                LEnv::OreAxionite => Tile::OreAxionite,
            };
            tiles[(y * w + x) as usize] = t;
        }
    }
    let core = cores.iter().find(|(_, t)| matches!(t, libre_engine::common::Team::A)).expect("no team A core");
    let map = Map { width: w, height: h, tiles, core: Pos::new(core.0.x, core.0.y) };
    let mut state = State::new(map, seed);
    for p in load_bp(bp_path)? {
        state.godmode_place(
            map_kind(p.kind),
            Pos::new(p.pos.x, p.pos.y),
            p.direction.map(map_dir),
            p.bridge_target.map(|t: LPos| Pos::new(t.x, t.y)),
        );
    }
    Ok(state)
}

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let bp = match args.next() {
        Some(p) => p,
        None => {
            eprintln!("usage: pong-parity BLUEPRINT.bp MAP.map26 [--turns N] [--seed N]");
            return ExitCode::from(2);
        }
    };
    let map = match args.next() {
        Some(p) => p,
        None => {
            eprintln!("usage: pong-parity BLUEPRINT.bp MAP.map26 [--turns N] [--seed N]");
            return ExitCode::from(2);
        }
    };
    let mut turns: i32 = 200;
    let mut seed: u64 = 1;
    let mut it = args;
    while let Some(a) = it.next() {
        match a.as_str() {
            "--turns" => turns = it.next().and_then(|s| s.parse().ok()).unwrap_or(turns),
            "--seed" => seed = it.next().and_then(|s| s.parse().ok()).unwrap_or(seed),
            other => {
                eprintln!("unknown arg {other}");
                return ExitCode::from(2);
            }
        }
    }
    let bp_path = Path::new(&bp);
    let map_path = Path::new(&map);
    let mut libre = match Sim::from_blueprint(map_path, bp_path, seed) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("libre setup error: {e}");
            return ExitCode::from(1);
        }
    };
    let mut mine = match build_my_state(map_path, bp_path, seed) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("my setup error: {e}");
            return ExitCode::from(1);
        }
    };
    let plan = pong_sa::plan::Plan::new(turns, 0);
    let mut all_ok = true;
    for t in 0..turns {
        libre.step();
        mine.step(&plan);
        let p = &libre.game.players[0];
        let l_ti = p.titanium;
        let l_ax = p.axionite_collected;
        let m_ti = mine.titanium;
        let m_ax = mine.axionite_collected;
        if l_ti != m_ti || l_ax != m_ax {
            println!(
                "turn={t:4} libre Ti={l_ti} Ax={l_ax}  mine Ti={m_ti} Ax={m_ax}  DIFF (Ti={dti}, Ax={dax})",
                dti = m_ti - l_ti, dax = m_ax - l_ax,
            );
            all_ok = false;
            if t > 10 {
                break;
            }
        }
    }
    if all_ok {
        let p = &libre.game.players[0];
        println!(
            "PARITY OK over {turns} turns: Ti={ti} Ax_collected={ax}",
            ti = p.titanium,
            ax = p.axionite_collected,
        );
        ExitCode::from(0)
    } else {
        ExitCode::from(1)
    }
}
