//! Resigns at round 600. Rust port of `bots/nothing/600/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

pub struct Player;

impl Bot for Player {
    fn new() -> Self {
        Player
    }

    fn run(&mut self, c: &mut Controller<'_>) {
        if c.get_current_round().unwrap() == 600 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
