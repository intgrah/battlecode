//! Translation of `bots/intgrah/v54.7.9/breach/__init__.py`.
//!
//! Phase 5 PosInt note: Breach behaviour is unimplemented. No conversion needed.

use cambc::Controller;

use crate::unit::{Unit, UnitState};

#[derive(Default)]
pub struct Breach {
    state: UnitState,
}

impl Breach {
    #[must_use]
    pub fn new() -> Self {
        Self {
            state: UnitState::new(),
        }
    }
}

impl Unit for Breach {
    fn unit_state(&self) -> &UnitState {
        &self.state
    }

    fn unit_state_mut(&mut self) -> &mut UnitState {
        &mut self.state
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        self.state.cache_per_turn_state(ct);
        self.state.check_symmetry_marker(ct);
        unimplemented!("Breach behaviour not implemented");
    }
}
