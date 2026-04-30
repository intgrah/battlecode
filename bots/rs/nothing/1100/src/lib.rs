//! Resigns at round 1100. Rust port of `bots/nothing/1100/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

#[derive(Default)]
pub struct Player;

impl Bot for Player {
    fn run(&mut self, c: &mut Controller<'_>) {
        if c.get_current_round().unwrap() == 1100 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
