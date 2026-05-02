//! Translation of `bots/intgrah/v54.7.9/builder/update/`.

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
use crate::config::DEBUG_INVARIANTS;
use crate::util::debug::Scope;

pub fn update(builder: &mut Builder, ct: &mut Controller<'_>) {
    let _g = Scope::new_timed("update");
    {
        let _g = Scope::new_timed("income");
        builder.update_income();
    }
    {
        let _g = Scope::new_timed("prune");
        prune::prune_stale(builder, ct);
    }
    {
        let _g = Scope::new_timed("vision");
        vision::update_vision(builder, ct);
    }
    {
        let _g = Scope::new_timed("reflect");
        reflect::update_reflect(builder);
    }
    {
        let _g = Scope::new_timed("reachability");
        builder.update_reachability();
    }
    {
        let _g = Scope::new_timed("ore_deny");
        turrets::update_ore_denial(builder);
    }
    {
        let _g = Scope::new_timed("turrets");
        turrets::update_enemy_turrets(builder);
    }
    {
        let _g = Scope::new_timed("threat");
        threat::apply_threat_overlay(builder);
    }
    {
        let _g = Scope::new_timed("role");
        role::update_role(builder);
    }
    {
        let _g = Scope::new_timed("econ");
        econ::update_map_econ(builder, ct);
    }
    {
        let _g = Scope::new_timed("econ_reach");
        econ::update_economy_reachability(builder);
    }
    {
        let _g = Scope::new_timed("junctions");
        econ::update_junctions(builder);
    }
    {
        let _g = Scope::new_timed("dangling");
        {
            let _g = Scope::new_timed("dangling");
            econ::update_unreachable_dangling(builder);
        }
        {
            let _g = Scope::new_timed("dangling");
            econ::update_dangling(builder);
        }
    }
    {
        let _g = Scope::new_timed("ore_target");
        {
            let _g = Scope::new_timed("update_ti_ore_target");
            econ::update_ti_ore_target(builder);
        }
        {
            let _g = Scope::new_timed("update_ax_ore_target");
            econ::update_ax_ore_target(builder);
        }
        {
            let _g = Scope::new_timed("update_offensive_ore_target");
            econ::update_offensive_ore_target(builder);
        }
    }
    {
        let _g = Scope::new_timed("foundry_target");
        econ::update_foundry_target(builder);
    }
    {
        let _g = Scope::new_timed("ti_sink");
        econ::update_ti_sink(builder);
    }
    {
        let _g = Scope::new_timed("patrol");
        patrol::update_patrol(builder);
    }
    if DEBUG_INVARIANTS {
        let _g = Scope::new_timed("invariants");
        econ::check_invariants(builder);
    }
}
