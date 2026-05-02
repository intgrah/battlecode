//! Translation of `bots/intgrah/v54.7.9/builder/update/`.

pub mod budget;
pub mod econ;
pub mod markers;
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
use crate::util::posint::idx_of;
use crate::util::trace;

pub fn update(builder: &mut Builder, ct: &mut Controller<'_>) {
    let _g = Scope::new_timed("update");
    {
        // Repopulate vision_mask before prune. Zero last turn's PosInts,
        // set 1 for current nearby_tiles. Lets prune + vision + tasks
        // skip ct.is_in_vision FFI in favour of an O(1) array read.
        let _g = Scope::new_timed("vision_mask");
        for &p in &builder.last_vision {
            builder.vision_mask[p as usize] = 0;
        }
        let mut cur: Vec<i32> = pyrust::vec::new!();
        for &pos in &builder.state.nearby_tiles {
            let pi = idx_of(pos);
            builder.vision_mask[pi as usize] = 1;
            pyrust::vec::push!(cur, pi);
        }
        builder.last_vision = cur;
    }
    {
        let _g = Scope::new_timed("prune");
        trace::enter(ct, "prune");
        prune::prune_stale(builder, ct);
        trace::exit(ct, "prune");
    }
    {
        let _g = Scope::new_timed("vision");
        trace::enter(ct, "vision");
        vision::update_vision(builder, ct);
        trace::exit(ct, "vision");
    }
    // BFS pre-pass disabled in `bugnav_step` — skip the per-turn
    // passability mirror that fed it (was ~5.5% of bot time).
    {
        let _g = Scope::new_timed("markers");
        trace::enter(ct, "markers");
        markers::update_markers(builder, ct);
        trace::exit(ct, "markers");
    }
    {
        let _g = Scope::new_timed("reflect");
        trace::enter(ct, "reflect");
        reflect::update_reflect(builder);
        trace::exit(ct, "reflect");
    }
    {
        let _g = Scope::new_timed("reachability");
        trace::enter(ct, "reachability");
        builder.update_reachability();
        trace::exit(ct, "reachability");
    }
    {
        let _g = Scope::new_timed("ore_deny");
        trace::enter(ct, "ore_deny");
        turrets::update_ore_denial(builder);
        trace::exit(ct, "ore_deny");
    }
    {
        let _g = Scope::new_timed("turrets");
        trace::enter(ct, "turrets");
        turrets::update_enemy_turrets(builder);
        trace::exit(ct, "turrets");
    }
    {
        let _g = Scope::new_timed("threat");
        trace::enter(ct, "threat");
        threat::apply_threat_overlay(builder);
        trace::exit(ct, "threat");
    }
    {
        let _g = Scope::new_timed("alert");
        crate::builder::patrol::update_alert(builder);
    }
    {
        let _g = Scope::new_timed("econ_explore_radius");
        crate::builder::patrol::update_econ_explore_radius(builder);
    }
    {
        let _g = Scope::new_timed("role");
        trace::enter(ct, "role");
        role::update_role(builder);
        trace::exit(ct, "role");
    }
    {
        let _g = Scope::new_timed("econ");
        trace::enter(ct, "econ");
        econ::update_map_econ(builder, ct);
        trace::exit(ct, "econ");
    }
    {
        let _g = Scope::new_timed("econ_reach");
        trace::enter(ct, "econ_reach");
        econ::update_economy_reachability(builder);
        trace::exit(ct, "econ_reach");
    }
    {
        let _g = Scope::new_timed("junctions");
        trace::enter(ct, "junctions");
        econ::update_junctions(builder);
        trace::exit(ct, "junctions");
    }
    {
        let _g = Scope::new_timed("dangling");
        trace::enter(ct, "dangling");
        econ::update_unreachable_dangling(builder);
        econ::update_dangling(builder);
        trace::exit(ct, "dangling");
    }
    {
        let _g = Scope::new_timed("ore");
        trace::enter(ct, "ore");
        econ::update_ore_target(builder);
        econ::update_ax_ore_target(builder);
        econ::update_offensive_ore_target(builder);
        trace::exit(ct, "ore");
    }
    {
        let _g = Scope::new_timed("foundry_target");
        trace::enter(ct, "foundry_target");
        econ::update_foundry_target(builder);
        trace::exit(ct, "foundry_target");
    }
    {
        let _g = Scope::new_timed("ti_sink");
        trace::enter(ct, "ti_sink");
        econ::update_ti_sink(builder);
        trace::exit(ct, "ti_sink");
    }
    {
        let _g = Scope::new_timed("patrol");
        trace::enter(ct, "patrol");
        patrol::update_patrol(builder);
        trace::exit(ct, "patrol");
    }
    if DEBUG_INVARIANTS {
        let _g = Scope::new_timed("invariants");
        econ::check_invariants(builder);
    }
}
