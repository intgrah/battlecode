use std::collections::HashMap;

use crate::constants;
use crate::entity;
use crate::proto;
use crate::vis;

#[derive(Clone, Debug)]
pub struct Entity {
    pub id: i32,
    pub team: proto::Team,
    pub pos: (i32, i32),
    pub hp: i32,
    pub max_hp: i32,
    pub kind: EntityKind,
}

#[derive(Clone, Debug)]
pub enum EntityKind {
    BuilderBot {
        action_cd: i32,
        move_cd: i32,
    },
    Core {
        action_cd: i32,
    },
    Conveyor {
        dir: proto::Direction,
        stored: proto::ResourceType,
    },
    ArmouredConveyor {
        dir: proto::Direction,
        stored: proto::ResourceType,
    },
    Splitter {
        dir: proto::Direction,
        stored: proto::ResourceType,
    },
    Bridge {
        target: (i32, i32),
        stored: proto::ResourceType,
    },
    Harvester {
        cooldown: i32,
        resource_type: proto::ResourceType,
    },
    Foundry {
        stored: proto::ResourceType,
    },
    Road,
    Barrier,
    Marker {
        value: u32,
    },
    Gunner {
        dir: proto::Direction,
        ammo_type: proto::ResourceType,
        ammo: i32,
    },
    Sentinel {
        dir: proto::Direction,
        ammo_type: proto::ResourceType,
        ammo: i32,
    },
    Breach {
        dir: proto::Direction,
        ammo_type: proto::ResourceType,
        ammo: i32,
    },
    Launcher {
        ammo_type: proto::ResourceType,
        #[allow(dead_code)]
        ammo: i32,
    },
    #[allow(dead_code)]
    CoreEdge {
        dx: i32,
        dy: i32,
    },
}

#[derive(Clone, Debug)]
pub struct PlayerState {
    pub titanium: i32,
    pub axionite: i32,
    pub ti_collected: i32,
    pub ax_collected: i32,
}

impl Default for PlayerState {
    fn default() -> Self {
        Self {
            titanium: constants::STARTING_TITANIUM,
            axionite: constants::STARTING_AXIONITE,
            ti_collected: 0,
            ax_collected: 0,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ResourceMoveRecord {
    pub from: (i32, i32),
    pub to: (i32, i32),
    pub resource: proto::ResourceType,
}

#[derive(Clone, Debug)]
pub struct TurnState {
    pub entities: HashMap<i32, Entity>,
    pub players: [PlayerState; 2],
    pub indicators: Vec<Indicator>,
    pub outputs: Vec<(i32, String)>,
    pub cpu_time_us: HashMap<i32, u32>,
    pub fire_events: Vec<((i32, i32), (i32, i32))>,
    pub resource_moves: Vec<ResourceMoveRecord>,
    pub tile_resources: HashMap<(i32, i32), (proto::ResourceType, i32)>,
    pub deaths: Vec<(i32, i32)>,
    pub actions: Vec<(i32, Action)>,
    pub vis_data: HashMap<i32, vis::VisState>,
}

#[derive(Clone, Copy, Debug)]
pub enum BuildingKind {
    Road,
    Barrier,
    Conveyor { dir: proto::Direction },
    ArmouredConveyor { dir: proto::Direction },
    Splitter { dir: proto::Direction },
    Bridge { target: (i32, i32) },
    Harvester,
    Foundry,
    Gunner { dir: proto::Direction },
    Sentinel { dir: proto::Direction },
    Breach { dir: proto::Direction },
    Launcher,
}

#[derive(Clone, Copy, Debug)]
pub enum Action {
    Move { dir: (i32, i32) },
    Spawn { dir: (i32, i32) },
    Build { what: BuildingKind, dir: (i32, i32) },
    PlaceMarker { dir: (i32, i32), value: u32 },
    DestroyBuilding { dir: (i32, i32) },
    DestroyMarker { dir: (i32, i32) },
    Attack { target: (i32, i32) },
}

impl std::fmt::Display for BuildingKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Road => write!(f, "road"),
            Self::Barrier => write!(f, "barrier"),
            Self::Conveyor { dir } => write!(f, "conveyor {}", entity::dir_suffix(*dir)),
            Self::ArmouredConveyor { dir } => {
                write!(f, "armoured conveyor {}", entity::dir_suffix(*dir))
            }
            Self::Splitter { dir } => write!(f, "splitter {}", entity::dir_suffix(*dir)),
            Self::Bridge { target } => write!(f, "bridge ({},{})", target.0, target.1),
            Self::Harvester => write!(f, "harvester"),
            Self::Foundry => write!(f, "foundry"),
            Self::Gunner { dir } => write!(f, "gunner {}", entity::dir_suffix(*dir)),
            Self::Sentinel { dir } => write!(f, "sentinel {}", entity::dir_suffix(*dir)),
            Self::Breach { dir } => write!(f, "breach {}", entity::dir_suffix(*dir)),
            Self::Launcher => write!(f, "launcher"),
        }
    }
}

impl std::fmt::Display for Action {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Move { dir } => write!(f, "Move {}", entity::dir_name(dir.0, dir.1)),
            Self::Spawn { dir } => write!(f, "Spawn builder {}", entity::dir_name(dir.0, dir.1)),
            Self::Build { what, dir } => {
                write!(f, "Build {what} {}", entity::dir_name(dir.0, dir.1))
            }
            Self::PlaceMarker { dir, value } => write!(
                f,
                "Place marker {} {value:#010x}",
                entity::dir_name(dir.0, dir.1)
            ),
            Self::DestroyBuilding { dir } => {
                write!(f, "Destroy building {}", entity::dir_name(dir.0, dir.1))
            }
            Self::DestroyMarker { dir } => {
                write!(f, "Destroy marker {}", entity::dir_name(dir.0, dir.1))
            }
            Self::Attack { target } => write!(f, "Attack ({},{})", target.0, target.1),
        }
    }
}

#[derive(Clone, Debug)]
pub enum Indicator {
    Line {
        id: i32,
        pos_a: (i32, i32),
        pos_b: (i32, i32),
        r: u8,
        g: u8,
        b: u8,
    },
    Dot {
        id: i32,
        pos: (i32, i32),
        r: u8,
        g: u8,
        b: u8,
    },
}

pub struct GameState {
    pub width: i32,
    pub height: i32,
    pub env: Vec<Vec<proto::Environment>>,
    pub turns: Vec<TurnState>,
    pub winner: Option<proto::Team>,
}

impl GameState {
    pub fn from_replay(replay: &proto::Replay) -> Self {
        let map = replay.map.as_ref().expect("replay missing map");
        let width = map.width;
        let height = map.height;

        let env: Vec<Vec<proto::Environment>> = map
            .rows
            .iter()
            .map(|row| {
                row.tiles
                    .iter()
                    .map(|&t| {
                        proto::Environment::try_from(t).unwrap_or(proto::Environment::EnvEmpty)
                    })
                    .collect()
            })
            .collect();

        let mut current = TurnState {
            entities: HashMap::new(),
            players: [PlayerState::default(), PlayerState::default()],
            indicators: Vec::new(),
            outputs: Vec::new(),
            cpu_time_us: HashMap::new(),
            fire_events: Vec::new(),
            resource_moves: Vec::new(),
            tile_resources: HashMap::new(),
            deaths: Vec::new(),
            actions: Vec::new(),
            vis_data: HashMap::new(),
        };

        for core_pos in &map.cores {
            if let Some(pos) = &core_pos.position {
                let team = proto::Team::try_from(core_pos.team).unwrap_or(proto::Team::A);
                current.entities.insert(
                    core_pos.id,
                    Entity {
                        id: core_pos.id,
                        team,
                        pos: (pos.x, pos.y),
                        hp: constants::CORE_MAX_HP,
                        max_hp: constants::CORE_MAX_HP,
                        kind: EntityKind::Core { action_cd: 0 },
                    },
                );
            }
        }

        let mut turns = Vec::with_capacity(replay.turns.len() + 1);
        turns.push(current.clone());

        for turn in &replay.turns {
            current.indicators.clear();
            current.outputs.clear();
            current.cpu_time_us.clear();
            current.fire_events.clear();
            current.resource_moves.clear();
            current.deaths.clear();
            current.actions.clear();
            current.vis_data.clear();

            let mut current_actor: i32 = -1;
            for update in &turn.updates {
                apply_update(&mut current, update, &mut current_actor);
            }
            turns.push(current.clone());
        }


        let winner = replay.winner.and_then(|w| proto::Team::try_from(w).ok());

        Self {
            width,
            height,
            env,
            turns,
            winner,
        }
    }

    pub const fn turn_count(&self) -> usize {
        self.turns.len().saturating_sub(1)
    }

}

const fn to_building_kind(kind: &EntityKind) -> Option<BuildingKind> {
    match kind {
        EntityKind::Road => Some(BuildingKind::Road),
        EntityKind::Barrier => Some(BuildingKind::Barrier),
        EntityKind::Conveyor { dir, .. } => Some(BuildingKind::Conveyor { dir: *dir }),
        EntityKind::ArmouredConveyor { dir, .. } => {
            Some(BuildingKind::ArmouredConveyor { dir: *dir })
        }
        EntityKind::Splitter { dir, .. } => Some(BuildingKind::Splitter { dir: *dir }),
        EntityKind::Bridge { target, .. } => Some(BuildingKind::Bridge { target: *target }),
        EntityKind::Harvester { .. } => Some(BuildingKind::Harvester),
        EntityKind::Foundry { .. } => Some(BuildingKind::Foundry),
        EntityKind::Gunner { dir, .. } => Some(BuildingKind::Gunner { dir: *dir }),
        EntityKind::Sentinel { dir, .. } => Some(BuildingKind::Sentinel { dir: *dir }),
        EntityKind::Breach { dir, .. } => Some(BuildingKind::Breach { dir: *dir }),
        EntityKind::Launcher { .. } => Some(BuildingKind::Launcher),
        _ => None,
    }
}

#[allow(clippy::too_many_lines)]
fn apply_update(state: &mut TurnState, update: &proto::Update, current_actor: &mut i32) {
    use proto::update::Kind;
    let Some(kind) = &update.kind else { return };
    match kind {
        Kind::PlaceEntity(pe) => {
            if let Some(e) = &pe.entity
                && let Some(entity) = parse_entity(e)
            {
                let actor = *current_actor;
                if let Some(actor_e) = state.entities.get(&actor) {
                    let dir = (entity.pos.0 - actor_e.pos.0, entity.pos.1 - actor_e.pos.1);
                    match &entity.kind {
                        EntityKind::BuilderBot { .. } => {
                            state.actions.push((actor, Action::Spawn { dir }));
                        }
                        EntityKind::Marker { value } => {
                            state
                                .actions
                                .push((actor, Action::PlaceMarker { dir, value: *value }));
                        }
                        _ => {
                            if let Some(what) = to_building_kind(&entity.kind) {
                                state.actions.push((actor, Action::Build { what, dir }));
                            }
                        }
                    }
                }
                state.entities.insert(entity.id, entity);
            }
        }
        Kind::MoveBuilderBot(m) => {
            if let Some(to) = &m.to
                && let Some(e) = state.entities.get_mut(&m.id)
            {
                let dx = to.x - e.pos.0;
                let dy = to.y - e.pos.1;
                state.actions.push((m.id, Action::Move { dir: (dx, dy) }));
                e.pos = (to.x, to.y);
            }
        }
        Kind::RemoveEntity(r) => {
            if let Some(e) = state.entities.remove(&r.id) {
                state.deaths.push(e.pos);
                let actor = *current_actor;
                if let Some(actor_e) = state.entities.get(&actor) {
                    let dir = (e.pos.0 - actor_e.pos.0, e.pos.1 - actor_e.pos.1);
                    if matches!(e.kind, EntityKind::Marker { .. }) {
                        state.actions.push((actor, Action::DestroyMarker { dir }));
                    } else {
                        state.actions.push((actor, Action::DestroyBuilding { dir }));
                    }
                }
            }
        }
        Kind::UpdateHp(h) => {
            if let Some(e) = state.entities.get_mut(&h.id) {
                e.hp = (e.hp + h.delta).clamp(0, e.max_hp);
            }
        }
        Kind::UpdatePlayers(up) => {
            if let Some(players) = &up.players {
                if let Some(a) = &players.a {
                    state.players[0] = PlayerState {
                        titanium: a.titanium,
                        axionite: a.axionite,
                        ti_collected: a.titanium_collected,
                        ax_collected: a.axionite_collected,
                    };
                }
                if let Some(b) = &players.b {
                    state.players[1] = PlayerState {
                        titanium: b.titanium,
                        axionite: b.axionite,
                        ti_collected: b.titanium_collected,
                        ax_collected: b.axionite_collected,
                    };
                }
            }
        }
        Kind::SetActionCooldown(c) => {
            *current_actor = c.id;
            if let Some(e) = state.entities.get_mut(&c.id) {
                match &mut e.kind {
                    EntityKind::BuilderBot { action_cd, .. } | EntityKind::Core { action_cd } => {
                        *action_cd = c.value;
                    }
                    _ => {}
                }
            }
        }
        Kind::SetMoveCooldown(c) => {
            if let Some(e) = state.entities.get_mut(&c.id)
                && let EntityKind::BuilderBot { move_cd, .. } = &mut e.kind
            {
                *move_cd = c.value;
            }
        }
        Kind::BotOutput(o) => {
            if !o.stdout.is_empty() {
                const VIS_PREFIX: &str = "##VIS## ";
                let mut regular = Vec::new();
                for line in o.stdout.lines() {
                    if let Some(json) = line.strip_prefix(VIS_PREFIX) {
                        if let Ok(fields) = serde_json::from_str::<vis::VisState>(json) {
                            state.vis_data.entry(o.id).or_default().extend(fields);
                        }
                    } else {
                        regular.push(line);
                    }
                }
                let text = regular.join("\n");
                if !text.is_empty() {
                    state.outputs.push((o.id, text));
                }
            }
            state.cpu_time_us.insert(o.id, o.exec_time_us);
        }
        Kind::IndicatorLine(l) => {
            if let (Some(a), Some(b)) = (&l.pos_a, &l.pos_b) {
                state.indicators.push(Indicator::Line {
                    id: l.id,
                    pos_a: (a.x, a.y),
                    pos_b: (b.x, b.y),
                    r: u8::try_from(l.r).unwrap_or(255),
                    g: u8::try_from(l.g).unwrap_or(255),
                    b: u8::try_from(l.b).unwrap_or(255),
                });
            }
        }
        Kind::IndicatorDot(d) => {
            if let Some(p) = &d.pos {
                state.indicators.push(Indicator::Dot {
                    id: d.id,
                    pos: (p.x, p.y),
                    r: u8::try_from(d.r).unwrap_or(255),
                    g: u8::try_from(d.g).unwrap_or(255),
                    b: u8::try_from(d.b).unwrap_or(255),
                });
            }
        }
        Kind::FireTurret(f) => {
            if let (Some(from), Some(to)) = (&f.from, &f.to) {
                state.fire_events.push(((from.x, from.y), (to.x, to.y)));
                state.actions.push((
                    *current_actor,
                    Action::Attack {
                        target: (to.x, to.y),
                    },
                ));
            }
        }
        Kind::DistributeResources(dr) => {
            for m in &dr.moves {
                let (Some(from), Some(to)) = (&m.from, &m.to) else {
                    continue;
                };
                let from_pos = (from.x, from.y);
                let to_pos = (to.x, to.y);

                // Multiple entities can share a tile (e.g. a builder bot standing
                // on a conveyor). HashMap iteration is non-deterministic, so we
                // must explicitly target the storage entity, not whichever entity
                // `find` happens to return first.
                let resource = state
                    .entities
                    .values()
                    .find(|e| e.pos == from_pos && entity::is_resource_holder(&e.kind))
                    .and_then(|e| entity::stored_resource(&e.kind))
                    .unwrap_or(proto::ResourceType::ResourceNone);

                let stack_id = m.resource_id.unwrap_or(0);

                if resource != proto::ResourceType::ResourceNone {
                    state.resource_moves.push(ResourceMoveRecord {
                        from: from_pos,
                        to: to_pos,
                        resource,
                    });
                }

                state.tile_resources.remove(&from_pos);
                if resource != proto::ResourceType::ResourceNone {
                    state.tile_resources.insert(to_pos, (resource, stack_id));
                }

                if let Some(src) = state
                    .entities
                    .values_mut()
                    .find(|e| e.pos == from_pos && entity::is_resource_holder(&e.kind))
                {
                    set_stored_resource(&mut src.kind, proto::ResourceType::ResourceNone);
                }
                if let Some(dst) = state
                    .entities
                    .values_mut()
                    .find(|e| e.pos == to_pos && entity::is_resource_holder(&e.kind))
                {
                    deliver_stored_resource(&mut dst.kind, resource);
                }
            }
        }
        Kind::BuilderAttack(a) => {
            if let Some(e) = state.entities.get(&a.id) {
                state.actions.push((a.id, Action::Attack { target: e.pos }));
            }
        }
    }
}

// Mirrors engine `Entity::receive_resource` for foundries: Ti + RawAx combine
// into RefinedAxionite in-place. For all other entities (and for foundries
// receiving into an empty slot) this is a plain overwrite.
const fn deliver_stored_resource(kind: &mut EntityKind, res: proto::ResourceType) {
    if let EntityKind::Foundry { stored } = kind {
        match (*stored, res) {
            (proto::ResourceType::ResourceTitanium, proto::ResourceType::ResourceRawAxionite)
            | (proto::ResourceType::ResourceRawAxionite, proto::ResourceType::ResourceTitanium) => {
                *stored = proto::ResourceType::ResourceRefinedAxionite;
                return;
            }
            _ => {}
        }
    }
    set_stored_resource(kind, res);
}

const fn set_stored_resource(kind: &mut EntityKind, res: proto::ResourceType) {
    match kind {
        EntityKind::Conveyor { stored, .. }
        | EntityKind::ArmouredConveyor { stored, .. }
        | EntityKind::Splitter { stored, .. }
        | EntityKind::Bridge { stored, .. }
        | EntityKind::Foundry { stored } => *stored = res,
        EntityKind::Gunner { ammo_type, .. }
        | EntityKind::Sentinel { ammo_type, .. }
        | EntityKind::Breach { ammo_type, .. }
        | EntityKind::Launcher { ammo_type, .. } => *ammo_type = res,
        _ => {}
    }
}

fn parse_entity(e: &proto::Entity) -> Option<Entity> {
    use proto::entity::Kind;
    let pos = e.position.as_ref()?;
    let team = proto::Team::try_from(e.team).unwrap_or(proto::Team::A);
    let kind = match &e.kind {
        Some(Kind::BuilderBot(b)) => EntityKind::BuilderBot {
            action_cd: b.action_cooldown,
            move_cd: b.move_cooldown,
        },
        Some(Kind::Core(c)) => EntityKind::Core {
            action_cd: c.action_cooldown,
        },
        Some(Kind::Conveyor(c)) => EntityKind::Conveyor {
            dir: proto::Direction::try_from(c.direction).unwrap_or(proto::Direction::DirNorth),
            stored: proto::ResourceType::try_from(c.stored)
                .unwrap_or(proto::ResourceType::ResourceNone),
        },
        Some(Kind::ArmouredConveyor(c)) => EntityKind::ArmouredConveyor {
            dir: proto::Direction::try_from(c.direction).unwrap_or(proto::Direction::DirNorth),
            stored: proto::ResourceType::try_from(c.stored)
                .unwrap_or(proto::ResourceType::ResourceNone),
        },
        Some(Kind::Splitter(s)) => EntityKind::Splitter {
            dir: proto::Direction::try_from(s.direction).unwrap_or(proto::Direction::DirNorth),
            stored: proto::ResourceType::try_from(s.stored)
                .unwrap_or(proto::ResourceType::ResourceNone),
        },
        Some(Kind::Bridge(b)) => {
            let target = b.target.as_ref().map_or((0, 0), |t| (t.x, t.y));
            EntityKind::Bridge {
                target,
                stored: proto::ResourceType::try_from(b.stored)
                    .unwrap_or(proto::ResourceType::ResourceNone),
            }
        }
        Some(Kind::Harvester(h)) => EntityKind::Harvester {
            cooldown: h.cooldown,
            resource_type: proto::ResourceType::try_from(h.resource_type)
                .unwrap_or(proto::ResourceType::ResourceNone),
        },
        Some(Kind::Foundry(f)) => EntityKind::Foundry {
            stored: proto::ResourceType::try_from(f.stored)
                .unwrap_or(proto::ResourceType::ResourceNone),
        },
        Some(Kind::Road(_)) => EntityKind::Road,
        Some(Kind::Barrier(_)) => EntityKind::Barrier,
        Some(Kind::Marker(m)) => EntityKind::Marker { value: m.value },
        Some(Kind::Gunner(g)) => EntityKind::Gunner {
            dir: proto::Direction::try_from(g.direction).unwrap_or(proto::Direction::DirNorth),
            ammo_type: proto::ResourceType::try_from(g.ammo_type)
                .unwrap_or(proto::ResourceType::ResourceNone),
            ammo: g.ammo_amount,
        },
        Some(Kind::Sentinel(s)) => EntityKind::Sentinel {
            dir: proto::Direction::try_from(s.direction).unwrap_or(proto::Direction::DirNorth),
            ammo_type: proto::ResourceType::try_from(s.ammo_type)
                .unwrap_or(proto::ResourceType::ResourceNone),
            ammo: s.ammo_amount,
        },
        Some(Kind::Breach(b)) => EntityKind::Breach {
            dir: proto::Direction::try_from(b.direction).unwrap_or(proto::Direction::DirNorth),
            ammo_type: proto::ResourceType::try_from(b.ammo_type)
                .unwrap_or(proto::ResourceType::ResourceNone),
            ammo: b.ammo_amount,
        },
        Some(Kind::Launcher(l)) => EntityKind::Launcher {
            ammo_type: proto::ResourceType::try_from(l.ammo_type)
                .unwrap_or(proto::ResourceType::ResourceNone),
            ammo: l.ammo_amount,
        },
        None => return None,
    };
    Some(Entity {
        id: e.id,
        team,
        pos: (pos.x, pos.y),
        hp: e.hp,
        max_hp: e.max_hp,
        kind,
    })
}
