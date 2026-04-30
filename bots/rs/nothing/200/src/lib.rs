use cambc::*;

#[derive(Default)]
pub struct Player;

impl Bot for Player {
    fn run(&mut self, c: &mut Controller<'_>) {
        if c.get_current_round().unwrap() == 200 {
            c.resign(None).ok();
        }
    }
}

cambc_bot!(Player);
