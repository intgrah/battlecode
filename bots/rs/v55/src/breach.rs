//! Translation of `bots/intgrah/v54.7.9/breach/__init__.py`.

use cambc::Controller;

use crate::unit::{Unit, UnitState, run_default};

#[derive(Default)]
pub struct Breach {
    state: UnitState,
}

impl Unit for Breach {
    fn state(&self) -> &UnitState {
        &self.state
    }

    fn state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        run_default(self, ct);
        unimplemented!("Breach behaviour not implemented");
    }
}
