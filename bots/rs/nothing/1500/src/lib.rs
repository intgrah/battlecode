//! Resigns at round 1500. Rust port of `bots/nothing/1500/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

pub struct Player;

impl Bot for Player {
    fn new() -> Self {
        Self
    }

    fn run(&mut self, c: &mut Controller<'_>) {
        if pyrust::unwrap!(c.get_current_round()) == 1500 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
