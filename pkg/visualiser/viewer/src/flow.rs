use std::collections::{HashMap, HashSet};

use crate::proto;
use crate::state::GameState;

const WINDOW: usize = 16;

pub struct TileFlow {
    pub ti: f32,
    pub raw_ax: f32,
    pub refined_ax: f32,
    pub stagnant: bool,
}

pub struct FlowState {
    pub tiles: HashMap<(i32, i32), TileFlow>,
}

/// Per-tile flow history entry: None = empty, Some = (`resource_type`, `stack_id`).
type Slot = Option<(proto::ResourceType, i32)>;

pub fn compute_empirical_flow(game: &GameState, turn: usize) -> FlowState {
    let start = turn.saturating_sub(WINDOW);
    let end = turn.min(game.turns.len().saturating_sub(1));
    let window_len = (end - start + 1).max(1);

    // Build per-tile history: for each turn in the window, what was on each tile.
    let mut histories: HashMap<(i32, i32), Vec<Slot>> = HashMap::new();

    for t in start..=end {
        if t >= game.turns.len() {
            break;
        }
        let turn_state = &game.turns[t];
        // Collect all tiles that have resources this turn
        let mut seen_this_turn: HashSet<(i32, i32)> = HashSet::new();
        for (&pos, &(res, id)) in &turn_state.tile_resources {
            seen_this_turn.insert(pos);
            let hist = histories.entry(pos).or_default();
            // Pad with None for any turns we missed
            while hist.len() < t - start {
                hist.push(None);
            }
            hist.push(Some((res, id)));
        }
        // For tiles we've seen before but are empty this turn, push None
        for hist in histories.values_mut() {
            while hist.len() < t - start + 1 {
                hist.push(None);
            }
        }
    }

    let window_f = window_len as f32;
    let mut tiles = HashMap::new();

    for (pos, hist) in &histories {
        let mut ti_ids: HashSet<i32> = HashSet::new();
        let mut raw_ax_ids: HashSet<i32> = HashSet::new();
        let mut refined_ax_ids: HashSet<i32> = HashSet::new();
        let mut seen_ids: HashMap<i32, usize> = HashMap::new(); // stack_id -> count of turns present

        for (res, id) in hist.iter().flatten() {
            match res {
                proto::ResourceType::ResourceTitanium => {
                    ti_ids.insert(*id);
                }
                proto::ResourceType::ResourceRawAxionite => {
                    raw_ax_ids.insert(*id);
                }
                proto::ResourceType::ResourceRefinedAxionite => {
                    refined_ax_ids.insert(*id);
                }
                proto::ResourceType::ResourceNone => {}
            }
            *seen_ids.entry(*id).or_default() += 1;
        }

        let total_unique = ti_ids.len() + raw_ax_ids.len() + refined_ax_ids.len();
        if total_unique == 0 {
            continue;
        }

        // Stagnant: any stack id was present for more than 1 turn (it sat there)
        let stagnant = seen_ids.values().any(|&count| count > 1);

        tiles.insert(
            *pos,
            TileFlow {
                ti: ti_ids.len() as f32 / window_f,
                raw_ax: raw_ax_ids.len() as f32 / window_f,
                refined_ax: refined_ax_ids.len() as f32 / window_f,
                stagnant,
            },
        );
    }

    FlowState { tiles }
}
