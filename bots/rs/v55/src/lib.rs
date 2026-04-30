//! Cambridge Battlecode bot — Rust translation of `bots/intgrah/v54.7.9`.
//!
//! `Player` is the entry point that the engine instantiates once and calls
//! `run(ct)` on each turn the unit is alive. `cambc_bot!(Player)` exports the
//! FFI symbols the engine looks for.

pub mod breach;
pub mod builder;
pub mod building;
pub mod config;
pub mod core;
pub mod gunner;
pub mod hardcode;
pub mod launcher;
pub mod marker;
pub mod sentinel;
pub mod unit;
pub mod util;

use cambc::{Controller, ControllerApi, EntityType};

use crate::breach::Breach;
use crate::builder::Builder;
use crate::core::Core;
use crate::gunner::Gunner;
use crate::launcher::Launcher;
use crate::sentinel::Sentinel;
use crate::unit::Unit;
use crate::util::debug::{Scope, flush};

/// Which of the six unit subtypes this `Player` instance resolved to. Cached
/// after the first turn so subsequent turns skip the dispatch + `post_init`.
#[derive(Clone, Copy, Debug)]
enum UnitKind {
    Builder,
    Core,
    Sentinel,
    Gunner,
    Launcher,
    Breach,
}

/// The bot. The engine constructs one `Player` per unit (the FFI entry
/// point) and calls `Bot::run` each turn.
pub struct Player {
    unit: Option<UnitKind>,
    builder: Builder,
    core: Core,
    sentinel: Sentinel,
    gunner: Gunner,
    launcher: Launcher,
    breach: Breach,
}

impl Default for Player {
    fn default() -> Self {
        Self::new()
    }
}

impl Player {
    #[must_use]
    pub fn new() -> Self {
        Self {
            unit: None,
            builder: Builder::default(),
            core: Core::default(),
            sentinel: Sentinel::default(),
            gunner: Gunner::default(),
            launcher: Launcher::default(),
            breach: Breach::default(),
        }
    }

    fn run_turn(&mut self, ct: &mut Controller<'_>) {
        let _turn = Scope::new("turn");
        if self.unit.is_none() {
            let kind = match ct.get_entity_type(None).unwrap() {
                EntityType::BuilderBot => UnitKind::Builder,
                EntityType::Core => UnitKind::Core,
                EntityType::Sentinel => UnitKind::Sentinel,
                EntityType::Gunner => UnitKind::Gunner,
                EntityType::Launcher => UnitKind::Launcher,
                EntityType::Breach => UnitKind::Breach,
                et => panic!("Player::run on unsupported entity type: {et:?}"),
            };
            self.unit = Some(kind);
            let _scope = Scope::new_timed("post_init");
            match kind {
                UnitKind::Builder => self.builder.post_init(ct),
                UnitKind::Core => self.core.post_init(ct),
                UnitKind::Sentinel => self.sentinel.post_init(ct),
                UnitKind::Gunner => self.gunner.post_init(ct),
                UnitKind::Launcher => self.launcher.post_init(ct),
                UnitKind::Breach => self.breach.post_init(ct),
            }
        }
        {
            let _scope = Scope::new_timed("run");
            match self.unit.expect("kind set above") {
                UnitKind::Builder => self.builder.run(ct),
                UnitKind::Core => self.core.run(ct),
                UnitKind::Sentinel => self.sentinel.run(ct),
                UnitKind::Gunner => self.gunner.run(ct),
                UnitKind::Launcher => self.launcher.run(ct),
                UnitKind::Breach => self.breach.run(ct),
            }
        }
        flush();
    }
}

impl cambc::Bot for Player {
    fn run(&mut self, ct: &mut Controller<'_>) {
        self.run_turn(ct);
    }
}

cambc::cambc_bot!(Player);
