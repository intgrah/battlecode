use crate::common::{Environment, Pos, Team};
use crate::game_map::{Entity, PlayerState};

#[derive(Clone, Debug)]
pub enum GameDiff {
    PlaceEntity {
        id: i32,
        entity: Entity,
    },
    MoveBuilderBot {
        id: i32,
        to: Pos,
    },
    RemoveEntity {
        id: i32,
    },
    DistributeResources {
        /// Each entry: (source position, sink position, resource stack id).
        moves: Vec<(Pos, Pos, i32)>,
    },
    UpdateHp {
        id: i32,
        delta: i32,
    },
    UpdatePlayers {
        players: [PlayerState; 2],
    },
    SetActionCooldown {
        id: i32,
        value: i32,
    },
    SetMoveCooldown {
        id: i32,
        value: i32,
    },
    BotOutput {
        id: i32,
        stdout: String,
        exec_time_us: u32,
        tled: bool,
    },
    IndicatorLine {
        id: i32,
        pos_a: Pos,
        pos_b: Pos,
        r: i32,
        g: i32,
        b: i32,
    },
    IndicatorDot {
        id: i32,
        pos: Pos,
        r: i32,
        g: i32,
        b: i32,
    },
    FireTurret {
        from: Pos,
        to: Pos,
    },
    /// Builder bot using its own-tile fire action (`c.fire(my_pos)`).
    /// Visualised separately from `FireTurret` because the source is a unit
    /// (not a turret) and the target is always its own tile.
    BuilderAttack {
        id: i32,
    },
}

#[derive(Clone, Debug)]
pub struct ReplayRecorder {
    environment: Vec<Vec<Environment>>,
    cores: Vec<(Pos, Team)>,
    diffs: Vec<Vec<GameDiff>>,
    suppress_indicators: bool,
}

impl ReplayRecorder {
    #[must_use]
    pub const fn new(
        environment: Vec<Vec<Environment>>,
        cores: Vec<(Pos, Team)>,
        suppress_indicators: bool,
    ) -> Self {
        Self {
            environment,
            cores,
            diffs: vec![],
            suppress_indicators,
        }
    }

    pub fn new_turn(&mut self) {
        self.diffs.push(vec![]);
    }

    pub fn append(&mut self, diff: GameDiff) {
        if self.suppress_indicators
            && matches!(
                diff,
                GameDiff::IndicatorLine { .. } | GameDiff::IndicatorDot { .. }
            )
        {
            return;
        }
        self.diffs
            .last_mut()
            .expect("append called before new_turn")
            .push(if self.suppress_indicators {
                match diff {
                    GameDiff::BotOutput {
                        id,
                        exec_time_us,
                        tled,
                        ..
                    } => GameDiff::BotOutput {
                        id,
                        stdout: String::new(),
                        exec_time_us,
                        tled,
                    },
                    other => other,
                }
            } else {
                diff
            });
    }

    /// Borrowed views for the `libre-replay` crate's protobuf builder.
    #[must_use]
    pub fn environment(&self) -> &[Vec<Environment>] {
        &self.environment
    }
    #[must_use]
    pub fn cores(&self) -> &[(Pos, Team)] {
        &self.cores
    }
    #[must_use]
    pub fn turns(&self) -> &[Vec<GameDiff>] {
        &self.diffs
    }
}
