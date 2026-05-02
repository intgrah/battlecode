//! Resigns at round 700. Rust port of `bots/nothing/700/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

pub struct Player;

impl Bot for Player {
    fn new() -> Self {
        Self
    }

    fn run(&mut self, c: &mut Controller<'_>) {
        if c.get_current_round().unwrap() == 700 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
