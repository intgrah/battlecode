use std::path::Path;
use std::process::ExitCode;

use libre_engine::common::{Direction as LDir, Environment as LEnv, Pos as LPos, Team};
use libre_engine::game::Game;
use libre_engine::game_map::Entity;
use pong_sa::plan::{Build, CoreAction, Plan, TurnAction};
use pong_sa::sim::{BuildKind, Direction, Map, Pos, State, Tile};

fn build_my_state(map_path: &Path, seed: u64, turns: i32, n_builders: usize) -> Result<(State, Plan), Box<dyn std::error::Error>> {
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
    let core = cores.iter().find(|(_, t)| matches!(t, Team::A)).expect("no team A core");
    let map = Map { width: w, height: h, tiles, core: Pos::new(core.0.x, core.0.y) };
    Ok((State::new(map, seed), Plan::new(turns, n_builders)))
}

fn build_libre(map_path: &Path, seed: u64) -> Result<Game, Box<dyn std::error::Error>> {
    let map_str = map_path.to_str().ok_or("non-utf8 map path")?;
    let (env, cores) = libre_replay::load_map(map_str)?;
    let mut game = Game::new(env, cores, seed, true);
    game.new_turn();
    Ok(game)
}

fn libre_team_a_core_id(game: &Game) -> i32 {
    for (id, e) in &game.entities {
        if let Entity::Core(c) = e {
            if c.team == Team::A {
                return *id;
            }
        }
    }
    panic!("no team A core");
}

fn dir_to_libre(d: Direction) -> LDir {
    match d {
        Direction::North => LDir::North,
        Direction::Northeast => LDir::Northeast,
        Direction::East => LDir::East,
        Direction::Southeast => LDir::Southeast,
        Direction::South => LDir::South,
        Direction::Southwest => LDir::Southwest,
        Direction::West => LDir::West,
        Direction::Northwest => LDir::Northwest,
    }
}

fn pos_to_libre(p: Pos) -> LPos {
    LPos { x: p.x, y: p.y }
}

fn apply_libre_turn(
    game: &mut Game,
    core_id: i32,
    builder_ids: &mut Vec<i32>,
    plan: &Plan,
    turn: i32,
) {
    let t = turn as usize;
    if t >= plan.turns as usize {
        return;
    }
    // Core spawn first.
    let core = plan.core[t];
    if let Some(sp) = core.spawn {
        let core_e = game.entities.get(&core_id).expect("core missing");
        if let Entity::Core(c) = core_e {
            if c.action_cooldown == 0 {
                let cost = game.scaled_cost(Team::A, libre_engine::common::game_constants::BUILDER_BOT_BASE_COST);
                let p = &game.players[Team::A.index()];
                if p.titanium >= cost.0 && p.axionite >= cost.1 {
                    let id = game.spawn_builder(core_id, pos_to_libre(sp));
                    builder_ids.push(id);
                }
            }
        }
    }
    // Builders in spawn (id) order, matching my sim.
    let bids = builder_ids.clone();
    for (idx, bot_id) in bids.iter().enumerate() {
        let action = plan.builders[idx].get(t).copied().unwrap_or(TurnAction::NOOP);
        // BUILD or DESTROY first, then MOVE.
        if let Some(b) = action.build {
            apply_libre_build(game, *bot_id, b);
        } else if let Some(p) = action.destroy {
            apply_libre_destroy(game, *bot_id, p);
        }
        if let Some(d) = action.mv {
            apply_libre_move(game, *bot_id, d);
        }
    }
}

fn apply_libre_build(game: &mut Game, bot_id: i32, b: Build) {
    let bot = game.entity(bot_id).expect("bot missing");
    let Entity::BuilderBot(bb) = bot else { return };
    if bb.action_cooldown != 0 {
        return;
    }
    let bot_pos = bb.position;
    let target = pos_to_libre(b.pos);
    let dx = (target.x - bot_pos.x).pow(2) + (target.y - bot_pos.y).pow(2);
    if dx > 2 {
        return;
    }
    if !game.game_map.in_bounds(target) {
        return;
    }
    let tile = game.game_map.tile(target);
    if tile.building.is_some() {
        return;
    }
    let cost = game.scaled_cost(Team::A, base_cost(b.kind));
    let p = &game.players[Team::A.index()];
    if p.titanium < cost.0 || p.axionite < cost.1 {
        return;
    }
    match b.kind {
        BuildKind::Conveyor => {
            let dir = dir_to_libre(b.direction.expect("conveyor missing dir"));
            game.build_conveyor(bot_id, target, dir);
        }
        BuildKind::Splitter => {
            let dir = dir_to_libre(b.direction.expect("splitter missing dir"));
            game.build_splitter(bot_id, target, dir);
        }
        BuildKind::ArmouredConveyor => {
            let dir = dir_to_libre(b.direction.expect("ac missing dir"));
            game.build_armoured_conveyor(bot_id, target, dir);
        }
        BuildKind::Bridge => {
            let bt = pos_to_libre(b.bridge_target.expect("bridge missing target"));
            game.build_bridge(bot_id, target, bt);
        }
        BuildKind::Harvester => { game.build_harvester(bot_id, target); }
        BuildKind::Foundry => { game.build_foundry(bot_id, target); }
        BuildKind::Road => { game.build_road(bot_id, target); }
        BuildKind::Barrier => { game.build_barrier(bot_id, target); }
    }
}

fn base_cost(k: BuildKind) -> (i32, i32) {
    use libre_engine::common::game_constants::*;
    match k {
        BuildKind::Conveyor => CONVEYOR_BASE_COST,
        BuildKind::Splitter => SPLITTER_BASE_COST,
        BuildKind::ArmouredConveyor => ARMOURED_CONVEYOR_BASE_COST,
        BuildKind::Bridge => BRIDGE_BASE_COST,
        BuildKind::Harvester => HARVESTER_BASE_COST,
        BuildKind::Foundry => FOUNDRY_BASE_COST,
        BuildKind::Road => ROAD_BASE_COST,
        BuildKind::Barrier => BARRIER_BASE_COST,
    }
}

fn apply_libre_destroy(game: &mut Game, bot_id: i32, p: Pos) {
    let bot = game.entity(bot_id).expect("bot missing");
    let Entity::BuilderBot(bb) = bot else { return };
    let bot_pos = bb.position;
    let tp = pos_to_libre(p);
    let dx = (tp.x - bot_pos.x).pow(2) + (tp.y - bot_pos.y).pow(2);
    if dx > 2 {
        return;
    }
    let tile = game.game_map.tile(tp);
    let Some(bid) = tile.building else { return };
    game.destroy_entity(bid);
}

fn apply_libre_move(game: &mut Game, bot_id: i32, d: Direction) {
    let bot = game.entity(bot_id).expect("bot missing");
    let Entity::BuilderBot(bb) = bot else { return };
    if bb.move_cooldown != 0 {
        return;
    }
    let from = bb.position;
    let to = LPos { x: from.x + d.delta().0, y: from.y + d.delta().1 };
    if !game.is_tile_bot_passable(to, Team::A) {
        return;
    }
    game.move_builder_bot(bot_id, to);
}

fn step_libre(game: &mut Game) {
    game.distribute_resources();
    game.update_cooldowns();
    use libre_engine::common::game_constants::{PASSIVE_TITANIUM_AMOUNT, PASSIVE_TITANIUM_INTERVAL};
    if (game.turn + 1) % PASSIVE_TITANIUM_INTERVAL == 0 {
        for p in &mut game.players {
            p.titanium += PASSIVE_TITANIUM_AMOUNT;
        }
    }
    game.turn += 1;
    game.new_turn();
}

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let map = match args.next() {
        Some(p) => p,
        None => {
            eprintln!("usage: pong-parity-exec MAP.map26 [--turns N] [--seed N]");
            return ExitCode::from(2);
        }
    };
    let mut turns: i32 = 50;
    let mut seed: u64 = 1;
    while let Some(a) = args.next() {
        match a.as_str() {
            "--turns" => turns = args.next().and_then(|s| s.parse().ok()).unwrap_or(turns),
            "--seed" => seed = args.next().and_then(|s| s.parse().ok()).unwrap_or(seed),
            o => {
                eprintln!("unknown arg {o}");
                return ExitCode::from(2);
            }
        }
    }
    let map_path = Path::new(&map);

    let mut libre = match build_libre(map_path, seed) {
        Ok(g) => g,
        Err(e) => { eprintln!("libre setup: {e}"); return ExitCode::from(1); }
    };
    let core_id = libre_team_a_core_id(&libre);
    let mut builder_ids: Vec<i32> = Vec::new();

    let (mut mine, mut plan) = match build_my_state(map_path, seed, turns, 1) {
        Ok(p) => p,
        Err(e) => { eprintln!("my setup: {e}"); return ExitCode::from(1); }
    };

    // Hand-crafted exec plan: spawn one builder at (8,7), build foundry at (8,6), idle.
    plan.core[0] = CoreAction { spawn: Some(Pos::new(8, 7)) };
    plan.builders[0][1] = TurnAction {
        build: Some(Build {
            kind: BuildKind::Foundry,
            pos: Pos::new(8, 6),
            direction: None,
            bridge_target: None,
        }),
        destroy: None,
        mv: Some(Direction::South),
    };
    // T=2: builder at (8,8) — middle of core. Move south to (8,9). Action CD still 1 from foundry.
    plan.builders[0][2] = TurnAction {
        build: None,
        destroy: None,
        mv: Some(Direction::South),
    };
    // T=3: action CD now 0. builder at (8,9). Build harvester? Need ore. Check pong map: no ore at action radius 2 of (8,9). Skip — leave noop.
    // Just verify parity with idle-after-move continues.

    let mut all_ok = true;
    for t in 0..turns {
        apply_libre_turn(&mut libre, core_id, &mut builder_ids, &plan, t);
        step_libre(&mut libre);

        mine.step(&plan);

        let p = &libre.players[Team::A.index()];
        let l_ti = p.titanium;
        let l_ax = p.axionite_collected;
        let l_scale = p.scale_milli;
        let m_ti = mine.titanium;
        let m_ax = mine.axionite_collected;
        let m_scale = mine.scale_milli;
        if l_ti != m_ti || l_ax != m_ax || l_scale != m_scale {
            println!(
                "turn={t:3} libre Ti={l_ti} Ax={l_ax} scale={l_scale}  mine Ti={m_ti} Ax={m_ax} scale={m_scale}",
            );
            all_ok = false;
            if t > 5 {
                break;
            }
        }
    }
    let p = &libre.players[Team::A.index()];
    println!(
        "final: Ti={ti} Ax_collected={ax} scale={s}  builders={n}",
        ti = p.titanium, ax = p.axionite_collected, s = p.scale_milli, n = builder_ids.len(),
    );
    if all_ok { ExitCode::from(0) } else { ExitCode::from(1) }
}
