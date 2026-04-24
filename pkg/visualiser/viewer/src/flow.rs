use std::collections::HashMap;

use crate::proto;
use crate::state::GameState;

const HISTORY_LEN: usize = 17;
const CHANGES_MAX: usize = HISTORY_LEN - 1; // 16
const STAGNANT_RUN: usize = 5;

pub struct TileFlow {
    pub ti: f32,
    pub raw_ax: f32,
    pub refined_ax: f32,
    pub stagnant: bool,
}

pub struct FlowState {
    pub tiles: HashMap<(i32, i32), TileFlow>,
}

/// Per-tile history entry: None = empty, Some = (`resource_type`, `stack_id`).
type Slot = Option<(proto::ResourceType, i32)>;

pub fn compute_empirical_flow(game: &GameState, turn: usize) -> FlowState {
    // Keep HISTORY_LEN observations (inclusive range [turn - 16, turn] → 17 entries).
    let start = turn.saturating_sub(HISTORY_LEN - 1);
    let end = turn.min(game.turns.len().saturating_sub(1));

    let mut histories: HashMap<(i32, i32), Vec<Slot>> = HashMap::new();

    for t in start..=end {
        if t >= game.turns.len() {
            break;
        }
        let turn_state = &game.turns[t];
        for (&pos, &(res, id)) in &turn_state.tile_resources {
            let hist = histories.entry(pos).or_default();
            while hist.len() < t - start {
                hist.push(None);
            }
            hist.push(Some((res, id)));
        }
        for hist in histories.values_mut() {
            while hist.len() < t - start + 1 {
                hist.push(None);
            }
        }
    }

    let changes_f = CHANGES_MAX as f32;
    let mut tiles = HashMap::new();

    for (pos, hist) in &histories {
        if hist.len() < 2 {
            continue;
        }

        // A "change" counts only when a stack ARRIVES on the tile: current
        // slot is Some and differs from the previous slot. Transitions to
        // None (stack leaving) don't count — otherwise a single ore
        // flowing in then out would double-count. Attribute the change to
        // the resource type of the arriving stack.
        let mut ti_changes: u32 = 0;
        let mut raw_ax_changes: u32 = 0;
        let mut refined_ax_changes: u32 = 0;
        for (prev, cur) in hist.iter().zip(hist.iter().skip(1)) {
            if let Some((cur_res, _)) = cur {
                if prev != cur {
                    match cur_res {
                        proto::ResourceType::ResourceTitanium => ti_changes += 1,
                        proto::ResourceType::ResourceRawAxionite => raw_ax_changes += 1,
                        proto::ResourceType::ResourceRefinedAxionite => {
                            refined_ax_changes += 1;
                        }
                        proto::ResourceType::ResourceNone => {}
                    }
                }
            }
        }

        // Stagnant: same stack id present for STAGNANT_RUN consecutive slots.
        let mut max_run: usize = 0;
        let mut cur_run: usize = 0;
        let mut last_id: Option<i32> = None;
        for slot in hist {
            let cur_id = slot.map(|(_, id)| id);
            match cur_id {
                Some(id) if Some(id) == last_id => {
                    cur_run += 1;
                }
                Some(_) => {
                    cur_run = 1;
                }
                None => {
                    cur_run = 0;
                }
            }
            if cur_run > max_run {
                max_run = cur_run;
            }
            last_id = cur_id;
        }
        let stagnant = max_run >= STAGNANT_RUN;

        let total = ti_changes + raw_ax_changes + refined_ax_changes;
        if total == 0 {
            continue;
        }

        tiles.insert(
            *pos,
            TileFlow {
                ti: ti_changes as f32 / changes_f,
                raw_ax: raw_ax_changes as f32 / changes_f,
                refined_ax: refined_ax_changes as f32 / changes_f,
                stagnant,
            },
        );
    }

    FlowState { tiles }
}
