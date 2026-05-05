//! Construction scheduler: produce a per-turn Plan that builds a blueprint.

use std::collections::BTreeMap;

use libre_engine::common::{Direction, Pos};

use crate::blueprint::Kind;

pub type UnitId = i32;
pub type Round = i32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Build {
    pub entity: Kind,
    pub pos: Pos,
    pub facing: Option<Direction>,
    pub bridge_target: Option<Pos>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TurnActions {
    Nothing,
    JustMove(Direction),
    JustBuild(Build),
    JustSpawn(Direction),
    MoveThenBuild(Direction, Build),
    BuildThenMove(Build, Direction),
}

#[derive(Debug, Clone, Default)]
pub struct Plan {
    /// For each unit (core or builder), the action it takes each round
    /// from the round of its first action onward.
    pub actions: BTreeMap<UnitId, Vec<TurnActions>>,
    pub first_round: BTreeMap<UnitId, Round>,
}

impl Plan {
    pub fn record(&mut self, round: Round, unit: UnitId, action: TurnActions) {
        let first = *self.first_round.entry(unit).or_insert(round);
        let v = self.actions.entry(unit).or_default();
        let idx = (round - first) as usize;
        if v.len() < idx {
            v.resize(idx, TurnActions::Nothing);
        }
        if v.len() == idx {
            v.push(action);
        } else {
            v[idx] = action;
        }
    }

    pub fn at(&self, round: Round, unit: UnitId) -> TurnActions {
        let first = *self.first_round.get(&unit).unwrap_or(&i32::MAX);
        if round < first {
            return TurnActions::Nothing;
        }
        self.actions
            .get(&unit)
            .and_then(|v| v.get((round - first) as usize))
            .copied()
            .unwrap_or(TurnActions::Nothing)
    }
}
