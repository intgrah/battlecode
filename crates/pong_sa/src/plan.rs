use crate::sim::{BuildKind, Direction, Pos};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Build {
    pub kind: BuildKind,
    pub pos: Pos,
    pub direction: Option<Direction>,
    pub bridge_target: Option<Pos>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TurnAction {
    pub build: Option<Build>,
    pub destroy: Option<Pos>,
    pub mv: Option<Direction>,
}

impl TurnAction {
    pub const NOOP: TurnAction = TurnAction {
        build: None,
        destroy: None,
        mv: None,
    };
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CoreAction {
    pub spawn: Option<Pos>,
}

impl CoreAction {
    pub const NOOP: CoreAction = CoreAction { spawn: None };
}

#[derive(Debug, Clone)]
pub struct Plan {
    pub turns: i32,
    pub builders: Vec<Vec<TurnAction>>,
    pub core: Vec<CoreAction>,
}

impl Plan {
    pub fn new(turns: i32, n_builders: usize) -> Self {
        Self {
            turns,
            builders: vec![vec![TurnAction::NOOP; turns as usize]; n_builders],
            core: vec![CoreAction::NOOP; turns as usize],
        }
    }
}
