//! Resigns at round 800. Rust port of `bots/nothing/800/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

pub struct Player;

impl Bot for Player {
    fn new() -> Self {
        Self
    }

    fn run(&mut self, c: &mut Controller<'_>) {
        if pyrust::unwrap!(c.get_current_round()) == 800 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
