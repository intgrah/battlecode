//! Resigns at round 100. Rust port of `bots/nothing/100/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

pub struct Player;

impl Bot for Player {
    fn new() -> Self {
        Player
    }

    fn run(&mut self, c: &mut Controller<'_>) {
        if c.get_current_round().unwrap() == 100 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
