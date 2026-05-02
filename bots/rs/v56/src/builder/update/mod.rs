pub mod econ;
pub mod patrol;
pub mod prune;
pub mod reflect;
pub mod role;
pub mod threat;
pub mod turrets;
pub mod vision;

use cambc::Controller;

use crate::builder::Builder;
use crate::builder::helpers::build_ore_friendlies;
use crate::builder::patrol::{update_alert, update_econ_explore_radius};
use crate::config::DEBUG_INVARIANTS;
use crate::util::debug::Scope;

pub fn update(builder: &mut Builder, ct: &mut Controller<'_>) {
    pyrust::with!(Scope::new_timed("update"), {
        pyrust::with!(Scope::new_timed("income"), {
            builder.update_income();
        });
        pyrust::with!(Scope::new_timed("prune"), {
            prune::prune_stale(builder, ct);
        });
        pyrust::with!(Scope::new_timed("vision"), {
            vision::update_vision(builder, ct);
        });
        pyrust::with!(Scope::new_timed("reflect"), {
            reflect::update_reflect(builder);
        });
        pyrust::with!(Scope::new_timed("reachability"), {
            builder.update_reachability();
        });
        pyrust::with!(Scope::new_timed("turrets"), {
            turrets::update_enemy_turrets(builder);
        });
        pyrust::with!(Scope::new_timed("threat"), {
            threat::apply_threat_overlay(builder);
        });
        pyrust::with!(Scope::new_timed("role"), {
            role::update_role(builder);
        });
        pyrust::with!(Scope::new_timed("alert"), {
            update_alert(builder);
        });
        pyrust::with!(Scope::new_timed("econ_explore_radius"), {
            update_econ_explore_radius(builder);
        });
        pyrust::with!(Scope::new_timed("econ"), {
            econ::update_map_econ(builder, ct);
        });
        pyrust::with!(Scope::new_timed("dangling"), {
            econ::update_dangling(builder);
        });
        pyrust::with!(Scope::new_timed("ore_target"), {
            let friendlies = build_ore_friendlies(builder);
            pyrust::with!(Scope::new_timed("update_ti_ore_target"), {
                econ::update_ti_ore_target(builder, &friendlies);
            });
            pyrust::with!(Scope::new_timed("update_ax_ore_target"), {
                econ::update_ax_ore_target(builder, &friendlies);
            });
            pyrust::with!(Scope::new_timed("update_offensive_ore_target"), {
                econ::update_offensive_ore_target(builder, &friendlies);
            });
        });
        pyrust::with!(Scope::new_timed("foundry_target"), {
            econ::update_foundry_target(builder);
        });
        pyrust::with!(Scope::new_timed("ti_sink"), {
            econ::update_ti_sink(builder);
        });
        pyrust::with!(Scope::new_timed("patrol"), {
            patrol::update_patrol(builder);
        });
        if DEBUG_INVARIANTS {
            pyrust::with!(Scope::new_timed("invariants"), {
                econ::check_invariants(builder);
            });
        }
    });
}
