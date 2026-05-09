use std::mem::{size_of, offset_of};
use cambc_libre_engine::game::Game;

fn main() {
    println!("Game           = {}", size_of::<Game>());
    println!("StdRng         = {}", size_of::<rand::rngs::StdRng>());

    println!();
    println!("offset game_map        = {}", offset_of!(Game, game_map));
    println!("offset unit_order      = {}", offset_of!(Game, unit_order));
    println!("offset harvesters      = {}", offset_of!(Game, harvesters));
    println!("offset replay_recorder = {}", offset_of!(Game, replay_recorder));
    println!("offset resign_message  = {}", offset_of!(Game, resign_message));
    println!("offset entities        = {}", offset_of!(Game, entities));
    println!("offset edge_last_used  = {}", offset_of!(Game, edge_last_used));
    println!("offset players         = {}", offset_of!(Game, players));
    println!("offset rng             = {}", offset_of!(Game, rng));
    println!("offset turn            = {}", offset_of!(Game, turn));
    println!("offset next_id         = {}", offset_of!(Game, next_id));
    println!("offset resign_called   = {}", offset_of!(Game, resign_called));
}
