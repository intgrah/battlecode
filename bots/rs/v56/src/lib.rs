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

use cambc::{Bot, Controller, ControllerApi, EntityType};

use crate::breach::Breach;
use crate::builder::Builder;
use crate::core::Core;
use crate::gunner::Gunner;
use crate::launcher::Launcher;
use crate::sentinel::Sentinel;
use crate::unit::Unit;
use crate::util::debug::{Scope, flush, set_current_bot};

pub struct Player {
    unit: Option<EntityType>,
    builder: Builder,
    core: Core,
    sentinel: Sentinel,
    gunner: Gunner,
    launcher: Launcher,
    breach: Breach,
}

impl Bot for Player {
    fn new() -> Self {
        Self {
            unit: None,
            builder: Builder::new(),
            core: Core::new(),
            sentinel: Sentinel::new(),
            gunner: Gunner::new(),
            launcher: Launcher::new(),
            breach: Breach::new(),
        }
    }

    fn run(&mut self, ct: &mut Controller<'_>) {
        set_current_bot(pyrust::unwrap!(ct.get_id()));
        pyrust::with!(Scope::new("turn"), {
            if pyrust::is_none!(self.unit) {
                let kind = pyrust::unwrap!(ct.get_entity_type(None));
                self.unit = Some(kind);
                pyrust::with!(Scope::new_timed("post_init"), {
                    match kind {
                        EntityType::BuilderBot => self.builder.post_init(ct),
                        EntityType::Core => self.core.post_init(ct),
                        EntityType::Sentinel => self.sentinel.post_init(ct),
                        EntityType::Gunner => self.gunner.post_init(ct),
                        EntityType::Launcher => self.launcher.post_init(ct),
                        EntityType::Breach => self.breach.post_init(ct),
                        et => panic!("Player::run on unsupported entity type: {et:?}"),
                    }
                });
            }
            pyrust::with!(Scope::new_timed("run"), {
                match pyrust::expect!(self.unit, "kind set above") {
                    EntityType::BuilderBot => self.builder.run(ct),
                    EntityType::Core => self.core.run(ct),
                    EntityType::Sentinel => self.sentinel.run(ct),
                    EntityType::Gunner => self.gunner.run(ct),
                    EntityType::Launcher => self.launcher.run(ct),
                    EntityType::Breach => self.breach.run(ct),
                    _ => {}
                }
            });
            flush();
        });
    }
}

cambc::cambc_bot!(Player);
