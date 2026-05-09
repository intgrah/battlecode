use std::path::Path;

use cambc_libre_engine::common::Team;
use cambc_libre_engine::common::game_constants::{PASSIVE_TITANIUM_AMOUNT, PASSIVE_TITANIUM_INTERVAL};
use cambc_libre_engine::game::Game;
use cambc_libre_engine::game_map::Entity;
use cambc_libre_engine::replay_diff::GameDiff;

use crate::blueprint::{self, Kind, Placement};

pub const TEAM: Team = Team::A;

pub struct Sim {
    pub game: Game,
}

impl Sim {
    pub fn from_blueprint(
        map_path: &Path,
        bp_path: &Path,
        seed: u64,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let map_str = map_path.to_str().ok_or("non-utf8 map path")?;
        let (env, cores) = cambc_libre_replay::load_map(map_str)?;
        let mut game = Game::new(env, cores, seed, true);
        game.new_turn();

        for p in blueprint::load(bp_path)? {
            place_godmode(&mut game, &p)?;
        }

        let players = game.players.clone();
        game.replay_recorder
            .append(GameDiff::UpdatePlayers { players });
        Ok(Self { game })
    }

    pub fn step(&mut self) {
        self.game.new_turn();
        self.game.distribute_resources();
        self.game.update_cooldowns();
        self.game.turn += 1;
        if self.game.turn % PASSIVE_TITANIUM_INTERVAL == 0 {
            for p in &mut self.game.players {
                p.titanium += PASSIVE_TITANIUM_AMOUNT;
                p.titanium_collected += PASSIVE_TITANIUM_AMOUNT;
            }
        }
        let players = self.game.players.clone();
        self.game
            .replay_recorder
            .append(GameDiff::UpdatePlayers { players });
    }

    pub fn run(&mut self, turns: i32) {
        for _ in 0..turns {
            self.step();
        }
    }

    pub fn write_replay(&self, path: &Path) -> std::io::Result<()> {
        let s = path
            .to_str()
            .ok_or_else(|| std::io::Error::other("non-utf8 replay path"))?;
        cambc_libre_replay::write_replay(&self.game.replay_recorder, s, None)
    }

    pub fn refined_axionite(&self) -> i32 {
        self.game.players[TEAM.index()].axionite_collected
    }

    pub fn titanium_collected(&self) -> i32 {
        self.game.players[TEAM.index()].titanium_collected
    }
}

fn place_godmode(game: &mut Game, p: &Placement) -> Result<(), String> {
    let id = game.new_id();
    let entity = match p.kind {
        Kind::Conveyor => {
            let dir = p
                .direction
                .ok_or_else(|| "conveyor missing dir".to_string())?;
            Entity::Conveyor(game.game_map.build_conveyor(id, TEAM, p.pos, dir))
        }
        Kind::Splitter => {
            let dir = p
                .direction
                .ok_or_else(|| "splitter missing dir".to_string())?;
            Entity::Splitter(game.game_map.build_splitter(id, TEAM, p.pos, dir))
        }
        Kind::ArmouredConveyor => {
            let dir = p
                .direction
                .ok_or_else(|| "armoured conveyor missing dir".to_string())?;
            Entity::ArmouredConveyor(game.game_map.build_armoured_conveyor(id, TEAM, p.pos, dir))
        }
        Kind::Bridge => {
            let target = p
                .bridge_target
                .ok_or_else(|| "bridge missing target".to_string())?;
            Entity::Bridge(game.game_map.build_bridge(id, TEAM, p.pos, target))
        }
        Kind::Harvester => Entity::Harvester(game.game_map.build_harvester(id, TEAM, p.pos)),
        Kind::Foundry => Entity::Foundry(game.game_map.build_foundry(id, TEAM, p.pos)),
        Kind::Road => Entity::Road(game.game_map.build_road(id, TEAM, p.pos)),
        Kind::Barrier => Entity::Barrier(game.game_map.build_barrier(id, TEAM, p.pos)),
    };
    game.players[TEAM.index()].scale_milli += entity.scale_contribution();
    if matches!(&entity, Entity::Harvester(_)) {
        game.harvesters.push(id);
    }
    game.entities.insert(id, entity.clone());
    game.replay_recorder
        .append(GameDiff::PlaceEntity { id, entity });
    Ok(())
}
