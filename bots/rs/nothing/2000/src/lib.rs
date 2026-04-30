//! Resigns at round 2000. Rust port of `bots/nothing/2000/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

#[derive(Default)]
pub struct Player;

impl Bot for Player {
    fn run(&mut self, c: &mut Controller<'_>) {
        if c.get_current_round().unwrap() == 2000 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
