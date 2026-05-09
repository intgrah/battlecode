use cambc_next_sdk::{Bot, Controller, cambc_main};

struct Player;

impl Bot for Player {
    fn new() -> Self { Self }

    fn run(&mut self, c: &mut Controller) {
        if c.round() == 50 {
            c.resign(Some("nothing/50".to_string()));
        }
    }
}

cambc_main!(Player);
