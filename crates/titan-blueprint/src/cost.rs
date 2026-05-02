use crate::blueprint::{BlueprintEntry, Entity};

const fn base_cost(k: Entity) -> (i32, i32) {
    match k {
        Entity::Conveyor => (3, 0),
        Entity::Splitter => (6, 0),
        Entity::ArmouredConveyor => (5, 5),
        Entity::Bridge => (20, 0),
        Entity::Harvester => (20, 0),
        Entity::Foundry => (40, 0),
        Entity::Gunner => (10, 0),
        Entity::Sentinel => (30, 0),
        Entity::Breach => (15, 10),
        Entity::Launcher => (20, 0),
        Entity::Barrier => (3, 0),
        Entity::Road => (1, 0),
    }
}

const fn scale_pct(k: Entity) -> f32 {
    match k {
        Entity::Road => 0.5,
        Entity::Conveyor
        | Entity::Splitter
        | Entity::ArmouredConveyor
        | Entity::Barrier
        | Entity::Gunner
        | Entity::Launcher
        | Entity::Breach => match k {
            Entity::Gunner | Entity::Launcher | Entity::Breach => 10.0,
            _ => 1.0,
        },
        Entity::Harvester => 5.0,
        Entity::Bridge => 10.0,
        Entity::Sentinel => 20.0,
        Entity::Foundry => 50.0,
    }
}

pub const BUILDER_SCALE_PCT: f32 = 20.0;

pub fn initial_scale(n_builders: i32) -> f32 {
    1.0 + n_builders as f32 * BUILDER_SCALE_PCT / 100.0
}

fn scaled_cost(entry: &BlueprintEntry, scale: f32) -> (i32, i32) {
    let (ti, ax) = base_cost(entry.kind);
    ((scale * ti as f32) as i32, (scale * ax as f32) as i32)
}

fn cumulative_cost(entries: &[&BlueprintEntry], n_builders: i32) -> (i32, i32) {
    let mut scale = initial_scale(n_builders);
    let mut ti_total = 0;
    let mut ax_total = 0;
    for e in entries {
        let (ti, ax) = scaled_cost(e, scale);
        ti_total += ti;
        ax_total += ax;
        scale += scale_pct(e.kind) / 100.0;
    }
    (ti_total, ax_total)
}

pub fn final_scale(entries: &[BlueprintEntry], n_builders: i32) -> f32 {
    let s: f32 = entries.iter().map(|e| scale_pct(e.kind)).sum();
    initial_scale(n_builders) + s / 100.0
}

pub fn cost_range(entries: &[BlueprintEntry], n_builders: i32) -> ((i32, i32), (i32, i32)) {
    let mut asc: Vec<&BlueprintEntry> = entries.iter().collect();
    asc.sort_by(|a, b| {
        scale_pct(a.kind)
            .partial_cmp(&scale_pct(b.kind))
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let desc: Vec<&BlueprintEntry> = asc.iter().rev().copied().collect();
    (
        cumulative_cost(&asc, n_builders),
        cumulative_cost(&desc, n_builders),
    )
}
