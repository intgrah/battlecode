//! Resigns at round 1200. Rust port of `bots/nothing/1200/main.py`.

use cambc::{Bot, Controller, ControllerApi, cambc_bot};

pub struct Player;

impl Bot for Player {
    fn new() -> Self {
        Self
    }

    fn run(&mut self, c: &mut Controller<'_>) {
        if pyrust::unwrap!(c.get_current_round()) == 1200 {
            let _ = c.resign(None);
        }
    }
}

cambc_bot!(Player);
